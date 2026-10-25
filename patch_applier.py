"""Validated, reviewable project change proposals and guarded patch application."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import stat
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath

from workspace_reader import (
    MAX_FILE_BYTES,
    WorkspaceError,
    WorkspaceIndex,
    _contains_secret,
    resolve_workspace,
    validate_workspace_target,
)

MAX_PROPOSAL_FILES = 5
MAX_PATCH_CHARS = 100_000
MAX_CHANGED_BYTES = 256 * 1024
MAX_RESULT_FILE_BYTES = MAX_FILE_BYTES
MAX_PROPOSAL_RESPONSE_CHARS = 600_000


class ProposalState(str, Enum):
    DRAFT = "Draft"
    READY = "Ready for review"
    APPLIED = "Applied"
    PARTIAL = "Partially applied"
    REJECTED = "Rejected"
    CONFLICT = "Conflict"
    FAILED = "Failed"


@dataclass
class ProposedFile:
    path: str
    operation: str
    reason: str
    expected_hash: str | None
    original_content: str
    new_content: str
    diff: str
    patch: str


@dataclass
class ChangeProposal:
    proposal_id: str
    workspace_root: str
    request: str
    explanation: str
    files: list[ProposedFile]
    state: ProposalState = ProposalState.READY
    results: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[tuple[str, str], ...]


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)$")
_CONTEXT_FILE = re.compile(r"(?m)^File: (.+?) \(lines \d+-\d+\)")
_WRITE_LOCKS: dict[str, threading.Lock] = {}
_WRITE_LOCKS_GUARD = threading.Lock()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def context_file_paths(context: str) -> set[str]:
    """Extract file names from the Workspace Reader's documented excerpt headers."""
    return {match.group(1) for match in _CONTEXT_FILE.finditer(context)}


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("The model returned duplicate JSON fields.")
        result[key] = value
    return result


def _get_write_lock(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path))
    with _WRITE_LOCKS_GUARD:
        return _WRITE_LOCKS.setdefault(key, threading.Lock())


def _read_target_baseline(root: Path, path: Path) -> tuple[bytes, os.stat_result]:
    """Read a bounded regular file through a descriptor and recheck its path identity."""
    relative = path.relative_to(root).as_posix()
    validate_workspace_target(root, relative)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_RESULT_FILE_BYTES:
            raise ValueError("The target is not a supported regular file or exceeds the file-size limit.")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_RESULT_FILE_BYTES + 1)
        after = path.stat()
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        if len(data) > MAX_RESULT_FILE_BYTES or not os.path.samestat(opened, after):
            raise ValueError("The target changed while it was being read.")
        validate_workspace_target(root, relative)
        return data, opened
    finally:
        os.close(descriptor)


def parse_unified_hunks(patch: str) -> list[Hunk]:
    """Parse a strict unified-hunk-only patch (file names live in the JSON schema)."""
    if not isinstance(patch, str) or not patch.strip() or len(patch) > MAX_PATCH_CHARS:
        raise ValueError("The proposed patch is empty or exceeds the size limit.")
    if "\x00" in patch:
        raise ValueError("The proposed patch contains invalid binary data.")
    lines = patch.splitlines()
    hunks: list[Hunk] = []
    position = 0
    while position < len(lines):
        if lines[position].startswith("\\ No newline at end of file") and hunks:
            position += 1
            continue
        match = _HUNK_HEADER.fullmatch(lines[position])
        if not match:
            raise ValueError("The proposed patch is malformed. Expected unified diff hunks.")
        old_start, old_count, new_start, new_count = match.groups()
        old_count_value = int(old_count) if old_count is not None else 1
        new_count_value = int(new_count) if new_count is not None else 1
        position += 1
        hunk_lines: list[tuple[str, str]] = []
        while position < len(lines) and not lines[position].startswith("@@ "):
            line = lines[position]
            if line.startswith("\\ No newline at end of file"):
                position += 1
                continue
            if not line or line[0] not in " +-":
                raise ValueError("The proposed patch contains an invalid diff line.")
            hunk_lines.append((line[0], line[1:]))
            position += 1
        actual_old = sum(kind in {" ", "-"} for kind, _ in hunk_lines)
        actual_new = sum(kind in {" ", "+"} for kind, _ in hunk_lines)
        if actual_old != old_count_value or actual_new != new_count_value:
            raise ValueError("The proposed patch has inconsistent hunk line counts.")
        hunks.append(Hunk(
            int(old_start), old_count_value, int(new_start), new_count_value, tuple(hunk_lines)
        ))
    if not hunks:
        raise ValueError("The proposed patch has no changes.")
    return hunks


def apply_unified_patch(original: str, patch: str, *, creating: bool = False) -> str:
    """Apply hunk lines only when all context exactly matches the supplied baseline."""
    hunks = parse_unified_hunks(patch)
    source = original.splitlines()
    output: list[str] = []
    cursor = 0
    for hunk in hunks:
        offset = hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1
        if (
            offset < cursor or offset > len(source)
            or (hunk.old_count and offset + hunk.old_count > len(source))
        ):
            raise ValueError("The proposed patch has invalid or overlapping hunk ranges.")
        output.extend(source[cursor:offset])
        expected_new_start = len(output) if hunk.new_count == 0 else len(output) + 1
        if hunk.new_start != expected_new_start:
            raise ValueError("The proposed patch has invalid new-file hunk ranges.")
        source_index = offset
        for kind, value in hunk.lines:
            if kind == " ":
                if source_index >= len(source) or source[source_index] != value:
                    raise ValueError("The patch context does not match the current file content.")
                output.append(value)
                source_index += 1
            elif kind == "-":
                if source_index >= len(source) or source[source_index] != value:
                    raise ValueError("The patch removal does not match the current file content.")
                source_index += 1
            else:
                output.append(value)
        cursor = source_index
    output.extend(source[cursor:])
    newline = "\r\n" if "\r\n" in original else "\n"
    final_newline = original.endswith(("\n", "\r")) if original else creating
    result = newline.join(output) + (newline if final_newline and output else "")
    if len(result.encode("utf-8")) > MAX_RESULT_FILE_BYTES:
        raise ValueError("The proposed result exceeds the per-file size limit.")
    if _contains_secret(result):
        raise ValueError("The proposed result contains a pattern that may be a secret.")
    return result


def _unified_diff(path: str, original: str, updated: str) -> str:
    before = [line + "\n" for line in original.splitlines()]
    after = [line + "\n" for line in updated.splitlines()]
    return "".join(difflib.unified_diff(
        before, after, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="\n"
    ))


def build_change_proposal(
    index: WorkspaceIndex,
    request: str,
    response_text: str,
    allowed_paths: set[str],
) -> ChangeProposal:
    """Validate strict JSON model output and build immutable-baseline preview entries."""
    if not isinstance(response_text, str) or len(response_text) > MAX_PROPOSAL_RESPONSE_CHARS:
        raise ValueError("The model proposal is empty or exceeds the response-size limit.")
    try:
        payload = json.loads(response_text, object_pairs_hook=_unique_json_object)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("The model returned invalid proposal JSON. Regenerate the proposal.") from exc
    except ValueError:
        raise
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "explanation", "files"}:
        raise ValueError("The proposal does not match the required schema.")
    if payload["schema_version"] != 1 or not isinstance(payload["explanation"], str):
        raise ValueError("The proposal schema version or explanation is invalid.")
    entries = payload["files"]
    if not isinstance(entries, list) or not entries or len(entries) > MAX_PROPOSAL_FILES:
        raise ValueError(f"A proposal must contain between 1 and {MAX_PROPOSAL_FILES} files.")
    indexed = {file.relative_path: file.text for file in index.files}
    seen: set[str] = set()
    proposed: list[ProposedFile] = []
    total_changed = 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "reason", "patch"}:
            raise ValueError("A proposed file entry does not match the required schema.")
        path, reason, patch = entry["path"], entry["reason"], entry["patch"]
        if not all(isinstance(value, str) and value.strip() for value in (path, reason, patch)):
            raise ValueError("Each proposed file needs a path, reason, and patch.")
        normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
        if normalized in seen:
            raise ValueError("The proposal contains duplicate target paths.")
        seen.add(normalized)
        if len(patch) > MAX_PATCH_CHARS:
            raise ValueError("A proposed patch exceeds the per-file size limit.")
        try:
            target, exists = validate_workspace_target(
                index.root, normalized, allow_create=True
            )
        except WorkspaceError as exc:
            raise ValueError(str(exc)) from exc
        if exists and normalized not in allowed_paths:
            raise ValueError("A proposed edit targets a file outside the retrieved code context.")
        if exists and normalized not in indexed:
            raise ValueError("The target file is not present in the active workspace index. Refresh and retry.")
        if not exists and normalized in indexed:
            raise ValueError("The target file changed during proposal generation. Refresh and retry.")
        original = indexed.get(normalized, "")
        try:
            current, _ = _read_target_baseline(index.root, target) if exists else (b"", None)
        except (OSError, ValueError, WorkspaceError) as exc:
            raise ValueError("A target file could not be read. Refresh the workspace and retry.") from exc
        expected = current if exists else b""
        if expected != original.encode("utf-8"):
            raise ValueError("A target file changed since indexing. Refresh the workspace and regenerate.")
        if len(current) > MAX_RESULT_FILE_BYTES:
            raise ValueError("A target file exceeds the supported size limit.")
        updated = apply_unified_patch(original, patch, creating=not exists)
        if updated == original:
            raise ValueError("The proposal contains a patch with no effective changes.")
        changed = sum(
            len(line[1:].encode("utf-8"))
            for line in patch.splitlines()
            if line.startswith(("+", "-"))
        )
        total_changed += changed
        if total_changed > MAX_CHANGED_BYTES:
            raise ValueError("The proposal exceeds the total changed-content limit.")
        proposed.append(ProposedFile(
            path=normalized,
            operation="modify" if exists else "create",
            reason=reason.strip(),
            expected_hash=_digest(current) if exists else None,
            original_content=original,
            new_content=updated,
            diff=_unified_diff(normalized, original, updated),
            patch=patch,
        ))
    return ChangeProposal(
        proposal_id=uuid.uuid4().hex,
        workspace_root=str(resolve_workspace(index.root)),
        request=request.strip(),
        explanation=payload["explanation"].strip(),
        files=proposed,
    )


def reject_proposal(proposal: ChangeProposal) -> None:
    if proposal.state != ProposalState.READY:
        raise ValueError("This proposal is no longer awaiting review.")
    proposal.state = ProposalState.REJECTED


def _read_current(root: Path, path: Path, expected_hash: str | None) -> tuple[bytes, os.stat_result]:
    data, opened = _read_target_baseline(root, path)
    if _digest(data) != expected_hash:
        raise ValueError("The file changed after this proposal was generated.")
    return data, opened


def _apply_one(root: Path, item: ProposedFile) -> str:
    target, exists = validate_workspace_target(
        root, item.path, allow_create=item.operation == "create"
    )
    if item.operation == "modify" and not exists:
        raise ValueError("The target file was deleted after proposal generation.")
    if item.operation == "create" and exists:
        raise ValueError("A file with this path already exists.")
    if exists:
        _, initial_stat = _read_current(root, target, item.expected_hash)
        mode = stat.S_IMODE(initial_stat.st_mode)
    else:
        mode = 0o666
    encoded = item.new_content.encode("utf-8")
    if len(encoded) > MAX_RESULT_FILE_BYTES:
        raise ValueError("The proposed result exceeds the per-file size limit.")
    try:
        resolved_parent = target.parent.resolve(strict=True)
        resolved_parent.relative_to(root)
        validate_workspace_target(root, item.path, allow_create=item.operation == "create")
    except (OSError, RuntimeError, ValueError, WorkspaceError) as exc:
        raise ValueError("The target directory changed or is no longer safe.") from exc
    descriptor, temporary_name = tempfile.mkstemp(prefix=".vask-proposal-", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            temporary.resolve(strict=True).parent.relative_to(root)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if item.operation == "create":
            # Hard-link creation is atomic and fails instead of overwriting a concurrent file.
            validate_workspace_target(root, item.path, allow_create=True)
            os.link(temporary, target)
            temporary.unlink(missing_ok=True)
            return "Applied"

        # Repeat the expected-hash and identity checks immediately before atomic replacement.
        validate_workspace_target(root, item.path)
        _read_current(root, target, item.expected_hash)
        current_stat = target.stat()
        if not os.path.samestat(initial_stat, current_stat):
            raise ValueError("The file was replaced after proposal generation.")
        os.replace(temporary, target)
        return "Applied"
    finally:
        temporary.unlink(missing_ok=True)


def apply_proposal(proposal: ChangeProposal, active_workspace: str | os.PathLike[str]) -> list[dict[str, str]]:
    """Apply each reviewed file independently and report exact per-file results."""
    if proposal.state != ProposalState.READY:
        raise ValueError("This proposal is no longer awaiting review and cannot be applied again.")
    root = resolve_workspace(active_workspace)
    if str(root) != proposal.workspace_root:
        proposal.state = ProposalState.CONFLICT
        proposal.results = [{"path": "", "status": "Conflict", "detail": "The active workspace changed. Reindex and regenerate the proposal."}]
        return proposal.results

    results: list[dict[str, str]] = []
    for item in proposal.files:
        try:
            with _get_write_lock(root / item.path):
                status = _apply_one(root, item)
            results.append({"path": item.path, "status": status, "detail": "File change completed."})
        except (OSError, ValueError, WorkspaceError) as exc:
            detail = str(exc) if isinstance(exc, (ValueError, WorkspaceError)) else "The file could not be safely written."
            conflict_markers = ("changed", "deleted", "exists", "no longer exists", "replaced", "refresh")
            status = "Conflict" if any(marker in detail.casefold() for marker in conflict_markers) else "Failed"
            results.append({"path": item.path, "status": status, "detail": detail})
    proposal.results = results
    applied_count = sum(result["status"] == "Applied" for result in results)
    if applied_count == len(results):
        proposal.state = ProposalState.APPLIED
    elif applied_count:
        proposal.state = ProposalState.PARTIAL
    elif any(result["status"] == "Conflict" for result in results):
        proposal.state = ProposalState.CONFLICT
    else:
        proposal.state = ProposalState.FAILED
    return results
