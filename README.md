# V-Ask — AI Agent & Visual Assistant for Developers

V-Ask is evolving into an AI agent for software development, combining developer-focused assistance with visual analysis to help developers understand code, investigate errors, review changes, and improve testing workflows.

The application currently runs on Streamlit and uses Nebius Token Factory through its OpenAI-compatible API. **Phase 1 focuses on a text-based developer assistant**: users provide code, errors, and context, and V-Ask responds using the configured model. Project access, file edit proposals, command execution, and image analysis are planned for later phases and are not available in Phase 1.

## Product direction

- **AI agent for developers:** Understand requests and work context, then help with tasks from analysis to actionable recommendations. Actions that affect a project should have a clear scope and require user confirmation.
- **Visual assistant:** The product is intended to analyze user-provided screenshots, interfaces, diagrams, and error images, and explain issues based on visible evidence.
- **Controlled assistance:** Today, V-Ask only receives content users provide and attached PDF/TXT documents. It does not read an entire project, edit code files, run arbitrary commands, or integrate with VS Code.

## Current features — Phase 1

- **General chat:** Ask general questions using the configured Nebius model.
- **Explain Code:** Explain code flow, functions, dependencies, and relevant edge cases.
- **Debug Assistant:** Analyze code and error messages, identify likely causes, and suggest fixes.
- **Code Review:** Review code for potential bugs, maintainability, readability, performance, and security risks.
- **Generate Tests:** Generate tests based on the framework and conventions provided or inferred from available context. The model does not claim that tests were run.
- **Document context:** Extract PDF/TXT text and search it locally, then send relevant excerpts to the model as context.
- **Local history and notes:** Store chat history and personal notes in SQLite on the device running V-Ask.
- **Confirmed desktop actions:** Open allowlisted applications and YouTube search results after user confirmation.

V-Ask does not claim that code was executed or tests passed unless they were actually run. Model responses are suggestions for developers to review.

## Roadmap

This roadmap describes the intended direction; these items are not all implemented.

1. **Phase 1 — Developer assistant:** Four developer modes, text input for code/errors/context, and PDF/TXT documents as model context.
2. **Phase 2 — Visual assistant:** Accept user-selected screenshots and images; analyze UIs, diagrams, and visible errors, and connect observations to visible regions.
3. **Phase 3 — Project-aware agent:** Read project files within a user-selected scope, search the codebase, and propose changes as diffs for user review.
4. **Later phases:** Consider running tests or developer commands with limited scope, clear action previews, and user confirmation before execution.

Project-wide filesystem access, autonomous code editing, arbitrary terminal execution, and a VS Code extension are outside Phase 1.

## Technology and project structure

```text
v-ask-visual-assistant/
├── app.py                  # Streamlit UI and conversation orchestration
├── developer_modes.py      # Developer mode instructions and input formatting
├── llm_client.py           # OpenAI SDK client for Nebius Token Factory
├── config.py               # Model, upload/context limits, and app configuration
├── memory.py               # Local SQLite chat history and notes
├── rag.py                  # Local PDF/TXT extraction, chunking, and retrieval
├── desktop_actions.py      # User-confirmed, allowlisted desktop actions
├── test_developer_modes.py # Unit tests for developer mode input formatting
├── assets/                 # Logo and UI assets
├── .streamlit/config.toml  # Streamlit theme and upload settings
├── requirements.txt
└── .env.example            # Environment variable template; not loaded automatically
```

## Requirements

- Python 3.10 or later
- A Nebius Token Factory API key
- A Nemotron model enabled for your Nebius account

## Run locally on Windows

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml` and add your API key:

```toml
NEBIUS_API_KEY = "your-nebius-api-key"
```

Start the application:

```powershell
streamlit run app.py
```

The default model is `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`. Set `NEBIUS_MODEL` in the environment to use another model enabled for your Nebius account.

## Data and privacy

- Chat history and notes are stored in `data/vask.sqlite3` on the machine running the application. Set `VASK_DATA_DIR` to use a different data directory.
- PDF/TXT text is extracted and kept in the current session; the RAG module does not write document text to disk. Relevant excerpts are sent to Nebius when generating an answer.
- Do not upload API keys or sensitive data in code/context. Do not commit secrets to the repository.
- Retrieved document text is reference material, not instructions for the assistant.

## Tests

Run the unit tests for developer mode input formatting:

```powershell
python -m unittest -v test_developer_modes.py
```
