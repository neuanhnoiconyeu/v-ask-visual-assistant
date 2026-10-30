# V-Ask VS Code extension

V-Ask brings the local V-Ask Python backend into VS Code through an Activity Bar sidebar. It supports the five assistant modes, editor selection commands, bounded workspace indexing, and a token-authenticated loopback backend.

## Local development

1. Open `vscode-extension/` in VS Code.
2. Install dependencies with `npm install`. If the trusted CA is installed in the Windows certificate store, run `$env:NODE_USE_SYSTEM_CA="1"; npm install` in PowerShell. Otherwise obtain the trusted proxy or organization CA PEM file from the network administrator and configure npm's `cafile` (or Node's `NODE_EXTRA_CA_CERTS`) with it. Keep TLS verification enabled; do not set `strict-ssl=false` or `NODE_TLS_REJECT_UNAUTHORIZED=0`.
3. Run `npm run compile`.
4. Set `vask.backendPath` to the absolute path of `vask_service.py` in the V-Ask checkout.
5. Press **Run Extension**.

The backend starts only when V-Ask needs it. It binds to loopback and uses a random token created by the extension. API keys remain in the Python environment or Streamlit secrets configuration; they are not sent to the webview.

## Commands

Use the Command Palette for **V-Ask: Open Assistant**, **Explain Selection**, **Explain Active File**, **Debug Selection**, **Review Selection**, **Generate Tests**, and **Refresh Project Index**.

## Proposal review

Enter a requested change in the assistant composer and choose **Propose change**. Each returned proposal lists affected files, reasons, and a unified diff. **Open native diff** compares service-supplied in-memory before/after documents with VS Code's diff editor; it does not write preview files. **Apply reviewed changes** always asks for a modal confirmation, then the local backend rechecks the workspace root, path safety, symlink rules, and file hashes before any atomic write. **Reject proposal** never changes project files.

The extension source has not yet been TypeScript-compiled or packaged in this environment because `npm install` is blocked by a certificate-chain error. Treat this workflow as source-level implementation until the build and manual runtime checks in `docs/PHASE5_TESTING.md` succeed.

## Packaging

Run `npm run package`; the intended artifact is `../dist/v-ask-vscode.vsix`. Install it with VS Code's Extensions UI or `code --install-extension ..\dist\v-ask-vscode.vsix`.

An installed VSIX currently expects access to the V-Ask Python checkout through `vask.backendPath`; bundling a Python runtime is intentionally out of scope for this local-development package.
