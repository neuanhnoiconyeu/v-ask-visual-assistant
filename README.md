# V-Ask — Vietnamese Personal AI

V-Ask is a privacy-conscious personal assistant built with Streamlit, NVIDIA Nemotron, and Nebius Token Factory. Chat history and personal notes are stored locally in SQLite. PDF and TXT documents are extracted and searched locally; only relevant excerpts are sent to Nebius when generating an answer.

## Project structure

```text
v-ask-visual-assistant/
├── app.py                 # Streamlit interface and app orchestration
├── config.py              # Shared configuration
├── llm_client.py          # OpenAI SDK client for Nebius Token Factory
├── memory.py              # SQLite chat history and personal notes
├── rag.py                 # Local PDF/TXT extraction, chunking, and retrieval
├── desktop_actions.py     # Confirmed app launch and YouTube search actions
├── assets/                # V-Ask logo assets
├── .streamlit/config.toml # Streamlit themes and upload settings
├── requirements.txt
└── .env.example
```

## Requirements

- Python 3.10 or later
- A Nebius Token Factory API key
- A Nemotron model enabled for your Nebius account

## Run locally

1. Create and activate a virtual environment, then install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Open `.streamlit/secrets.toml` and add your key:

   ```toml
   NEBIUS_API_KEY = "your-nebius-api-key"
   ```

   The file is ignored by Git. Set `NEBIUS_MODEL` as an environment variable if you need a different model ID; the default is configured in `config.py`.

3. Start the app:

   ```powershell
   streamlit run app.py
   ```

The app stores its local database at `data/vask.sqlite3`. Set `VASK_DATA_DIR` to use another local directory. Each installation maintains its own memory.

## Features and privacy

- **Local memory:** Chat history and personal notes are stored in SQLite on the device running V-Ask.
- **Local document retrieval:** PDF and TXT files are extracted and searched in the current Streamlit session. Document text is not written to disk by the RAG module. Relevant excerpts are sent to Nebius for answers. Long summary requests are limited to the configured context size.
- **Spotify player:** On Windows, a Spotify-style bar shows artwork, title, artist, playback progress, and controls using the local Spotify Desktop media session. No Spotify login or Client ID is needed.
- **Desktop actions:** Applications must be listed in the allowlist in `desktop_actions.py`. App launches and YouTube searches require an explicit confirmation. YouTube opens search results; it does not automatically start playback.
- **Themes:** The Streamlit settings menu supports custom Light and Dark themes. The app uses Be Vietnam Pro when Google Fonts is available and falls back to Segoe UI.

## Two-person task assignment

| Team member | Ownership | Main files |
|---|---|---|
| A — AI, memory, and RAG | Nebius client and prompts; SQLite schema and queries; PDF/TXT extraction, chunking, retrieval, and provider error handling. Coordinate through the public interfaces `answer(messages, context)`, `memory.*`, `extract_text()`, and `retrieve()`. | `llm_client.py`, `memory.py`, `rag.py`, `config.py`, `requirements.txt` |
| B — Product UI and desktop integration | Streamlit interface, uploads, notes and chat display, theme styling, confirmed desktop actions, and setup documentation. Consume member A's public functions without editing their implementation. | `app.py`, `desktop_actions.py`, `.streamlit/`, `README.md`, `.gitignore` |

### Git workflow

- Work on separate branches: `feature/ai-memory-rag` and `feature/streamlit-actions`.
- Keep UI changes in `app.py` with member B, and storage/retrieval changes in `memory.py` and `rag.py` with member A.
- Keep public function signatures stable; discuss interface changes before integrating.
- Commit on feature branches and open pull requests into `main`. Integrate the AI/memory/RAG interfaces before the UI branch depends on them.
