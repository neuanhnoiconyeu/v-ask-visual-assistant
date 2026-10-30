# Phase 5 architecture

V-Ask keeps its Streamlit application as one client of shared Python modules. The VS Code extension is a second client; it does not depend on Streamlit session state.

## Existing reusable modules

- `llm_client.py`: Nebius OpenAI-compatible chat-completions client and configured model.
- `developer_modes.py`: five mode instructions.
- `memory.py`: SQLite conversations and notes, including mode-aware conversations.
- `workspace_reader.py` and `workspace_context.py`: bounded, secret-aware indexing and retrieval.
- `patch_applier.py`: proposal parsing, diff creation, conflict detection, guarded apply/reject.

## Extension path

`vscode-extension/` is a TypeScript VS Code extension. It owns editor selection, active workspace discovery, webview state, and the local backend child-process lifecycle. It starts no backend or index operation until a V-Ask command/view action needs one.

The extension starts `vask_service.py` on loopback with a random per-process token. The service accepts only `127.0.0.1` connections and requires `X-Vask-Token`; it does not expose CORS or API keys. The webview talks only to the extension host, never directly to the Python service.

For an installed VSIX, backend discovery never uses a path relative to the extension directory. It prioritizes an explicit `vask.backendPath`, a single recognized workspace-local V-Ask repository, then a previously validated backend location. Ambiguous multi-root workspaces require explicit configuration.

## Data flow and boundaries

1. VS Code passes a selected snippet/active workspace root to the extension host.
2. The extension validates webview messages and calls the authenticated local service.
3. The service validates workspace paths, indexes bounded safe text files, builds selected/retrieved context, and calls the existing Nebius client.
4. For edits, the service reuses `patch_applier` and only applies a reviewed proposal on explicit API action.

## Proposal review workflow

The VS Code webview submits a bounded change request to `POST /v1/proposals`. The local service returns a structured proposal containing file paths, operations, reasons, unified diffs, and in-memory before/after content when the aggregate preview remains within the service preview limit. The webview renders each file's diff and can open VS Code's native `vscode.diff` editor using untitled in-memory documents; preview never writes to the project.

Apply is a separate, modal-confirmed `POST /v1/proposals/{id}/apply` call. It sends the currently opened workspace root, which must match the root recorded when the proposal was created. `patch_applier` then repeats path, symlink, identity, and SHA-256 conflict checks immediately before atomic writes. Reject is a separate endpoint and never writes files. Oversized previews remain reviewable through their bounded unified diff, and malformed/unsafe proposals are rejected by the service before the webview receives them.

The model receives only selected/retrieved bounded excerpts. The service never executes workspace code or shell commands. API keys remain in the Python configuration path and are never sent to the extension/webview.

## Development and packaging

Run Python tests from the repository root. In `vscode-extension/`, install npm dependencies, compile TypeScript, then package a local VSIX. An installed VSIX must configure `vask.backendPath` to the checkout containing `vask_service.py` unless a future distribution bundles the Python backend.
