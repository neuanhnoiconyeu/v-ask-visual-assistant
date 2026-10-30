"""Loopback-only API used by the V-Ask VS Code extension.

The service is intentionally small: it exposes the existing V-Ask business logic,
never executes project code, and requires an extension-created bearer token.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from developer_modes import MODE_INSTRUCTIONS
from llm_client import answer, request_change_proposal
from memory import (add_message, get_messages, get_or_create_mode_conversation,
                    initialize, new_conversation)
from patch_applier import (ChangeProposal, apply_proposal,
                           build_change_proposal, context_file_paths, reject_proposal)
from workspace_context import build_workspace_context
from workspace_reader import WorkspaceError, WorkspaceIndex, index_workspace, resolve_workspace

API_VERSION = "v1"
MAX_REQUEST_BYTES = 512 * 1024
MAX_MESSAGE_CHARS = 50_000
MAX_PROPOSAL_PREVIEW_CHARS = 1_000_000


class ApiError(ValueError):
    def __init__(self, code: str, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.code, self.status = code, status


class VaskService:
    def __init__(self) -> None:
        self.indexes: dict[str, WorkspaceIndex] = {}
        self.proposals: dict[str, ChangeProposal] = {}
        initialize()

    @staticmethod
    def _mode(value: Any) -> str:
        if not isinstance(value, str) or value not in MODE_INSTRUCTIONS:
            raise ApiError("invalid_mode", "Choose one of the supported V-Ask modes.")
        return value

    @staticmethod
    def _text(value: Any, field: str, *, required: bool = True) -> str:
        if not isinstance(value, str):
            raise ApiError("invalid_request", f"{field} must be text.")
        result = value.strip()
        if required and not result:
            raise ApiError("invalid_request", f"{field} is required.")
        if len(result) > MAX_MESSAGE_CHARS:
            raise ApiError("request_too_large", f"{field} exceeds the request limit.")
        return result

    def _index(self, root: Any, *, refresh: bool = False) -> WorkspaceIndex:
        try:
            canonical = resolve_workspace(self._text(root, "workspace root"))
        except WorkspaceError as exc:
            raise ApiError("invalid_workspace", str(exc)) from None
        key = str(canonical)
        if refresh or key not in self.indexes:
            try:
                self.indexes[key] = index_workspace(canonical)
            except WorkspaceError as exc:
                raise ApiError("workspace_index_failed", str(exc)) from None
        return self.indexes[key]

    @staticmethod
    def _selected_paths(value: Any) -> set[str]:
        if value is None:
            return set()
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ApiError("invalid_request", "selectedFiles must be a list of relative file paths.")
        return set(value[:200])

    def health(self) -> dict[str, Any]:
        return {"apiVersion": API_VERSION, "status": "ok", "indexedWorkspaces": len(self.indexes)}

    def index(self, payload: dict[str, Any]) -> dict[str, Any]:
        index = self._index(payload.get("workspaceRoot"), refresh=bool(payload.get("refresh")))
        return {
            "root": str(index.root), "fileCount": index.file_count,
            "totalBytes": index.total_bytes, "skippedFiles": index.skipped_files,
            "skippedBytes": index.skipped_bytes, "truncated": index.truncated,
            "files": [file.relative_path for file in index.files],
        }

    def new_conversation(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = self._mode(payload.get("mode"))
        conversation_id = new_conversation(mode) if payload.get("fresh") else get_or_create_mode_conversation(mode)
        return {"conversationId": conversation_id}

    def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = self._mode(payload.get("mode"))
        prompt = self._text(payload.get("message"), "message")
        conversation_id = payload.get("conversationId")
        if not isinstance(conversation_id, str) or not conversation_id:
            conversation_id = new_conversation(mode)
        workspace_context = ""
        context_meta: dict[str, Any] = {"includedFiles": [], "retrievedFiles": [], "omittedFiles": []}
        if payload.get("workspaceRoot"):
            index = self._index(payload.get("workspaceRoot"))
            context = build_workspace_context(index, prompt, self._selected_paths(payload.get("selectedFiles")))
            workspace_context = context.content
            context_meta = {
                "includedFiles": list(context.included_files), "retrievedFiles": list(context.retrieved_files),
                "omittedFiles": [asdict(item) for item in context.omitted_files],
            }
        add_message(conversation_id, "user", prompt)
        try:
            reply = answer(get_messages(conversation_id)[-20:], mode=mode, workspace_context=workspace_context)
        except RuntimeError as exc:
            raise ApiError("provider_not_configured", str(exc), HTTPStatus.SERVICE_UNAVAILABLE) from None
        except Exception:
            raise ApiError("provider_request_failed", "The AI provider request failed. Check connection and configuration.", HTTPStatus.BAD_GATEWAY) from None
        add_message(conversation_id, "assistant", reply)
        return {"conversationId": conversation_id, "reply": reply, "context": context_meta}

    def proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = self._text(payload.get("request"), "request")
        index = self._index(payload.get("workspaceRoot"))
        context = build_workspace_context(index, request, self._selected_paths(payload.get("selectedFiles")))
        paths = context_file_paths(context.content)
        if not paths:
            raise ApiError("insufficient_context", "No relevant indexed source files were found.")
        indexed = {file.relative_path: file.text for file in index.files}
        hashes = {path: hashlib.sha256(indexed[path].encode()).hexdigest() for path in paths if path in indexed}
        try:
            raw = request_change_proposal(request, context.content, hashes)
        except RuntimeError as exc:
            raise ApiError("provider_not_configured", str(exc), HTTPStatus.SERVICE_UNAVAILABLE) from None
        except Exception:
            raise ApiError("provider_request_failed", "The AI provider request failed. Check connection and configuration.", HTTPStatus.BAD_GATEWAY) from None
        try:
            proposal = build_change_proposal(index, request, raw, set(hashes))
        except (ValueError, WorkspaceError) as exc:
            raise ApiError("proposal_invalid", str(exc)) from None
        self.proposals[proposal.proposal_id] = proposal
        return self._proposal_payload(proposal)

    def proposal_action(self, proposal_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ApiError("proposal_not_found", "This proposal is no longer available. Generate it again.", HTTPStatus.NOT_FOUND)
        if action == "reject":
            reject_proposal(proposal)
        elif action == "apply":
            try:
                active_workspace = resolve_workspace(self._text((payload or {}).get("workspaceRoot"), "workspace root"))
                apply_proposal(proposal, active_workspace)
            except (ValueError, WorkspaceError) as exc:
                raise ApiError("proposal_apply_failed", str(exc)) from None
        else:
            raise ApiError("invalid_request", "Unsupported proposal action.")
        return self._proposal_payload(proposal)

    @staticmethod
    def _proposal_payload(proposal: ChangeProposal) -> dict[str, Any]:
        remaining_preview = MAX_PROPOSAL_PREVIEW_CHARS
        files: list[dict[str, Any]] = []
        for item in proposal.files:
            preview_size = len(item.original_content) + len(item.new_content)
            preview_available = preview_size <= remaining_preview
            if preview_available:
                remaining_preview -= preview_size
            files.append({
                "path": item.path, "operation": item.operation, "reason": item.reason, "diff": item.diff,
                "previewAvailable": preview_available,
                "originalContent": item.original_content if preview_available else None,
                "proposedContent": item.new_content if preview_available else None,
            })
        return {
            "proposalId": proposal.proposal_id, "state": proposal.state.value,
            "explanation": proposal.explanation, "workspaceRoot": proposal.workspace_root,
            "results": proposal.results,
            "files": files,
        }


class Handler(BaseHTTPRequestHandler):
    service: VaskService
    token: str

    def log_message(self, _format: str, *_args: Any) -> None:
        return  # Never log request bodies or auth headers.

    def _json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Vask-Token", ""), self.token)

    def _payload(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ApiError("invalid_request", "Content-Length must be a valid number.") from None
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ApiError("request_too_large", "Request body is missing or exceeds the limit.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError("invalid_json", "Request body must be valid JSON.") from None
        if not isinstance(value, dict):
            raise ApiError("invalid_json", "Request body must be an object.")
        return value

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": {"code": "unauthorized", "message": "Unauthorized local client."}})
            return
        if self.path == f"/{API_VERSION}/health":
            self._json(HTTPStatus.OK, self.service.health())
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": {"code": "not_found", "message": "Unknown endpoint."}})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": {"code": "unauthorized", "message": "Unauthorized local client."}})
            return
        try:
            payload = self._payload()
            if self.path == f"/{API_VERSION}/index": result = self.service.index(payload)
            elif self.path == f"/{API_VERSION}/conversations": result = self.service.new_conversation(payload)
            elif self.path == f"/{API_VERSION}/chat": result = self.service.chat(payload)
            elif self.path == f"/{API_VERSION}/proposals": result = self.service.proposal(payload)
            elif self.path.startswith(f"/{API_VERSION}/proposals/"):
                parts = self.path.split("/")
                if len(parts) != 5:
                    raise ApiError("not_found", "Unknown endpoint.", HTTPStatus.NOT_FOUND)
                proposal_id, action = parts[-2], parts[-1]
                result = self.service.proposal_action(proposal_id, action, payload)
            else: raise ApiError("not_found", "Unknown endpoint.", HTTPStatus.NOT_FOUND)
            self._json(HTTPStatus.OK, result)
        except ApiError as exc:
            self._json(exc.status, {"error": {"code": exc.code, "message": str(exc)}})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": {"code": "internal_error", "message": "The local V-Ask service could not complete this request."}})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    if len(args.token) < 24:
        raise SystemExit("A sufficiently long local service token is required.")
    Handler.service, Handler.token = VaskService(), args.token
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"VASK_SERVICE_PORT={server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
