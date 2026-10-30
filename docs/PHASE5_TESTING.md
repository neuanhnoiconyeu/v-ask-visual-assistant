# Phase 5 testing

Python tests do not need a Nebius key; client calls are mocked where applicable.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Extension validation:

```powershell
cd vscode-extension
npm run compile
npm run package
```

These commands require the extension development dependencies. If npm reports a certificate-chain error, stop there and configure a trusted CA supplied by the relevant network administrator; do not disable TLS validation. A successful Python test run validates the local service contract only, not TypeScript compilation, VSIX packaging, or VS Code runtime behavior.

`test_vask_service.py` uses mocked proposal-provider responses to cover proposal display payloads, reject-without-write, multiple files, workspace conflict handling, invalid proposal IDs, unsafe paths, and provider failures. These are service-contract tests, not a real Nebius or VS Code integration test.

Once npm dependencies are available, compile and package first. Then install the VSIX in a disposable workspace and manually verify: generate a multi-file proposal, inspect each unified diff, open the native diff preview, reject a proposal, apply a proposal after the modal confirmation, and change an original file before apply to confirm the backend reports a conflict rather than overwriting it.

Also test backend discovery with (a) the V-Ask repository open directly and (b) an unrelated workspace. In the unrelated workspace, use **V-Ask: Configure Backend** to choose the checkout, then run **V-Ask: Test Backend Connection**. Confirm invalid folders are rejected, multi-root ambiguity does not choose a backend silently, and no token appears in Output → **V-Ask**.

Install the resulting VSIX with `code --install-extension ..\dist\v-ask-vscode.vsix`, then configure `vask.backendPath`. Manual verification should cover editor-selection commands, an indexed workspace, a configured Nebius response, and proposal review before any apply action.
