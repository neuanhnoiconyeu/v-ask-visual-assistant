# V-Ask — AI Agent & Visual Assistant for Developers

V-Ask is evolving into an AI agent for software development. It can understand a selected project, propose scoped source changes, and let the developer inspect and approve each diff before files are changed.

The application currently runs on Streamlit and uses Nebius Token Factory through its OpenAI-compatible API. Phase 1 added text-based developer modes. **Phase 2 adds a read-only project workspace reader**: users select a local project directory, V-Ask indexes supported text files in the current session, and relevant excerpts are retrieved for questions.

## Product direction

- **AI agent for developers:** Understand requests and work context, then help with tasks from analysis to actionable recommendations. Actions that affect a project should have a clear scope and require user confirmation.
- **Controlled assistance:** Project changes are shown as diffs and applied only after explicit user approval. V-Ask does not execute project code or commands.

## Implemented features

- **General chat:** Ask general questions using the configured Nebius model.
- **Explain Code:** Explain code flow, functions, dependencies, and relevant edge cases.
- **Debug Assistant:** Analyze code and error messages, identify likely causes, and suggest fixes.
- **Code Review:** Review code for potential bugs, maintainability, readability, performance, and security risks.
- **Generate Tests:** Generate tests based on the framework and conventions provided or inferred from available context. The model does not claim that tests were run.
- **Project workspace reader:** Enter a local project directory path and index/refresh it in the sidebar. Search Python, Java, JavaScript, TypeScript, C/C++, and common project configuration files by names and code content; retrieve bounded excerpts with relative paths and line numbers.
- **Safe change proposals:** Describe a project change, review a structured multi-file diff, then apply or reject it. Application checks file hashes for conflicts, blocks traversal and excluded/sensitive paths, and reports per-file outcomes.
- **Document context:** Extract PDF/TXT text and search it locally, then send relevant excerpts to the model as context.
- **Local history and notes:** Store chat history and personal notes in SQLite on the device running V-Ask.
- **Confirmed desktop actions:** Open allowlisted applications and YouTube search results after user confirmation.

V-Ask does not claim that code was executed or tests passed unless they were actually run. Model responses are suggestions for developers to review.

## Roadmap

This roadmap describes the implementation phases.

1. **Phase 1 — Developer assistant:** Four developer modes, text input for code/errors/context, and PDF/TXT documents as model context.
2. **Phase 2 — Project workspace reader:** Read-only indexing and retrieval within a user-selected local project directory.
3. **Phase 3 — Safe project changes:** Generate structured proposals from relevant workspace excerpts, review unified diffs, then explicitly apply or reject with conflict checks.
4. **Later phases — Visual assistant:** Analyze user-selected screenshots, interfaces, diagrams, and visible errors based on visible evidence.

Autonomous terminal execution, automatic test execution, file deletion, and a VS Code extension are not part of the current phases.

## Technology and project structure

```text
v-ask-visual-assistant/
├── app.py                  # Streamlit UI and conversation orchestration
├── developer_modes.py      # Developer mode instructions and input formatting
├── workspace_reader.py     # Bounded, read-only workspace indexing and search
├── patch_applier.py        # Structured proposal validation, diff generation, and safe writes
├── llm_client.py           # OpenAI SDK client for Nebius Token Factory
├── config.py               # Model, upload/context limits, and app configuration
├── memory.py               # Local SQLite chat history and notes
├── rag.py                  # Local PDF/TXT extraction, chunking, and retrieval
├── desktop_actions.py      # User-confirmed, allowlisted desktop actions
├── test_developer_modes.py # Unit tests for developer mode input formatting
├── test_workspace_reader.py # Workspace safety, indexing, and retrieval tests
├── test_patch_applier.py   # Proposal validation, diff, conflict, and safe-write tests
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
- Workspace indexes are held in session memory and are not written to disk. Indexing is limited to 2,000 files and 20 MiB total, with a 512 KiB per-file limit. `.git`, virtual environments, dependency/build/cache directories, known credential paths, secret filenames, binary files, and files with recognized secret markers are excluded by default.
- When a workspace is active, only bounded excerpts relevant to the current question or change request (up to 12,000 characters) are sent to the configured Nebius model. The sidebar displays this notice. Project code is never executed. A reviewed proposal may modify/create supported files only after explicit approval; each target is checked against its indexed SHA-256 before writing. New files require an existing parent directory.
- Project change proposals are held in session memory. They are limited to 5 files, 100,000 patch characters per file, 256 KiB total changed lines, and 512 KiB per resulting file. Multi-file operations report partial outcomes; conflicts require reindexing and proposal regeneration. Writes use same-directory temporary files and atomic replacement/creation where supported.
- Do not upload API keys or sensitive data in code/context. Do not commit secrets to the repository.
- Retrieved document text is reference material, not instructions for the assistant.

## Tests

Run the unit tests for developer modes, workspace reading, and safe change proposals:

```powershell
python -m unittest -v test_developer_modes.py test_workspace_reader.py test_patch_applier.py
```
