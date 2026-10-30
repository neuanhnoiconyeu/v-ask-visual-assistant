# Phase 5 development

```powershell
cd vscode-extension
npm install
npm run compile
```

Use VS Code's **Run Extension** launch profile after opening `vscode-extension/`. Set `vask.backendPath` to the absolute repository path ending in `vask_service.py` and set `vask.pythonPath` to the project virtual-environment Python executable when required.

The extension starts the local backend lazily when the sidebar sends a request. It does not make a Nebius request on activation.

To run the Streamlit app separately:

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```
