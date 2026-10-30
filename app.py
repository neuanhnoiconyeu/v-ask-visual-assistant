"V-Ask Streamlit personal assistant."""
from __future__ import annotations

import base64
import hashlib
from html import escape
from pathlib import Path

import streamlit as st

from config import MAX_PROJECT_UPLOAD_MB, MAX_SELECTED_WORKSPACE_CONTEXT_CHARS, MAX_UPLOAD_MB
from developer_modes import MODE_INSTRUCTIONS, build_developer_request
from desktop_actions import APP_ALLOWLIST, detect_action, open_application, open_youtube
from llm_client import answer, request_change_proposal
from memory import (add_message, add_note, clear_conversation, delete_note,
                    get_messages, get_notes, get_or_create_mode_conversation,
                    initialize, new_conversation)
from patch_applier import (ProposalState, apply_proposal, build_change_proposal,
                           context_file_paths, reject_proposal)
from project_importer import (ImportedProject, ProjectImportError, import_project_folder,
                              import_project_zip, list_imported_projects,
                              remove_imported_project)
from rag import all_document_context, extract_text, retrieve
from workspace_context import FileTreeNode, build_file_tree, build_workspace_context
from workspace_reader import WorkspaceError, index_workspace, resolve_workspace

LOGO_PATH = Path(__file__).parent / "assets" / "vask-logo-transparent.png"
MODE_HINTS = {
    "General chat": "Ask anything; relevant indexed project excerpts are included when available.",
    "Explain Code": "Explain code flow, functions, dependencies, and edge cases.",
    "Debug Assistant": "Share code and an error to investigate likely causes and specific fixes.",
    "Code Review": "Review code for correctness, maintainability, performance, and security.",
    "Generate Tests": "Draft tests that match the supplied project conventions; tests are not run.",
}
st.set_page_config(page_title="V-Ask | Developer Workspace", page_icon=LOGO_PATH, layout="wide")

st.markdown("""
<style>
:root {
  --app-bg: #0b0c09;
  --sidebar-bg: #10110d;
  --surface-1: #141510;
  --surface-2: #1a1b15;
  --surface-3: #22231b;
  --text-primary: #f3f1e8;
  --text-secondary: #aaa99f;
  --text-muted: #77786e;
  --accent-lime: #c7f464;
  --accent-lime-strong: #d5ff72;
  --border-subtle: rgba(224, 226, 204, .12);
  --border-strong: rgba(224, 226, 204, .22);
  --radius-sm: 6px;
  --radius-md: 10px;
  --space-1: .4rem;
  --space-2: .75rem;
  --space-3: 1.25rem;
  --space-4: 2rem;
  --duration-fast: 150ms;
  color-scheme: dark;
}
html, body, input, textarea, button, label, p, h1, h2, h3,
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
[data-testid="stWidgetLabel"] {
  font-family: Inter, "Segoe UI", system-ui, sans-serif !important;
}
.stApp {
  color: var(--text-primary) !important;
  background: var(--app-bg) !important;
}
[data-testid="stHeader"], header[data-testid="stHeader"], .stAppHeader,
[data-testid="stToolbar"], [data-testid="stBottom"],
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > div, .stBottomBlockContainer {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
}
[data-testid="stAppViewContainer"] { background: transparent !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stDeployButton"] { background: transparent !important; }
.block-container { max-width: 1120px; padding: 2.25rem 2.5rem 11rem; scroll-padding-bottom: 11rem; }
[data-testid="stSidebar"] {
  background: var(--sidebar-bg) !important;
  border-right: 1px solid var(--border-subtle);
}
[data-testid="stSidebar"] > div:first-child { padding: 1.15rem .9rem 1.5rem; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  color: var(--text-primary); font-weight: 650; letter-spacing: -.02em;
}
[data-testid="stSidebar"] hr { border-color: var(--border-subtle); margin: 1rem 0; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--text-muted); }
[data-testid="stSidebar"] [data-testid="stExpander"] {
  border: 0; border-top: 1px solid var(--border-subtle); border-radius: 0;
  background: transparent; overflow: visible;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  color: var(--text-primary); font-weight: 620; padding: .7rem 0;
}
[data-testid="stSidebar"] [data-testid="stImage"] img {
  object-fit: contain; border-radius: var(--radius-sm);
}
[data-testid="stSidebar"] [data-testid="stButton"] > button {
  min-height: 2.35rem; border-radius: var(--radius-sm); text-align: left;
  white-space: normal; line-height: 1.35;
}
.st-key-vask-sidebar-brand { padding: .2rem .15rem .8rem; border-bottom: 1px solid var(--border-subtle); margin-bottom: .65rem; }
.vask-brand-name { color: var(--text-primary); font-size: 1rem; font-weight: 700; letter-spacing: -.035em; }
.vask-brand-caption { color: var(--text-muted); font-size: .7rem; letter-spacing: .08em; text-transform: uppercase; }
.vask-side-label { color: var(--text-muted); font-size: .67rem; font-weight: 700; letter-spacing: .11em; text-transform: uppercase; margin: 1.2rem 0 .4rem; text-align: center; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  display: flex; justify-content: center; text-align: center;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary > *:first-child {
  margin-left: auto; margin-right: auto;
}
[data-testid="stSidebar"] [data-testid="stButton"] > button,
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] > button {
  justify-content: center; text-align: center;
}
.vask-current-workspace {
  display: flex; gap: .5rem; align-items: flex-start; padding: .6rem 0;
  border: 0; border-left: 2px solid var(--accent-lime);
  background: transparent; color: var(--text-secondary); font-size: .78rem;
  overflow-wrap: anywhere;
}
.vask-current-workspace > * { margin-left: .65rem; }
.vask-current-workspace strong { color: var(--text-primary); font-weight: 620; }
.vask-current-workspace code { color: var(--text-secondary); overflow-wrap: anywhere; white-space: normal; }
.vask-page-header {
  display: flex; justify-content: space-between; align-items: center; gap: 1rem;
  padding: 0 0 .85rem; border-bottom: 1px solid var(--border-subtle); margin-bottom: 1.5rem;
}
.vask-page-eyebrow { color: var(--text-muted); font-size: .72rem; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; }
.vask-page-status { color: var(--text-secondary); font-size: .78rem; }
.vask-page-status span { color: var(--accent-lime); }
.welcome-shell { max-width: 620px; margin: 0; padding: 0; }
.welcome-kicker { color: var(--accent-lime); font-size: .7rem; font-weight: 700; letter-spacing: .17em; text-transform: uppercase; }
.welcome-title { max-width: 680px; margin: .8rem 0 1rem; color: var(--text-primary); font-size: clamp(2.35rem, 5vw, 4.2rem); font-weight: 680; letter-spacing: -.065em; line-height: 1.02; }
.welcome-copy { max-width: 600px; margin: 0; color: var(--text-secondary); font-size: 1rem; line-height: 1.7; }
.welcome-note { margin-top: 1.4rem; color: var(--text-muted); font-size: .78rem; }
.welcome-status { display: flex; align-items: center; gap: .5rem; margin-top: 1.25rem; color: var(--text-secondary); font-size: .78rem; }
.welcome-status::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--accent-lime); }
.vask-welcome-logo { width: min(100%, 250px); margin: 0 auto; position: relative; overflow: hidden; }
.vask-welcome-logo img { display: block; width: 100%; height: auto; }
.vask-welcome-logo.logo-intro img { animation: logo-reveal 1.65s ease-out both; }
.vask-welcome-logo.logo-intro::after {
  content: ""; position: absolute; inset: 0 auto 0 -42%; width: 30%;
  background: linear-gradient(100deg, transparent, rgba(222, 188, 97, .72), transparent);
  mix-blend-mode: screen; transform: skewX(-18deg); animation: logo-sweep .55s ease-out .9s both;
  pointer-events: none;
}
.st-key-welcome-logo-actions { width: min(100%, 250px); margin: 1rem auto 0; }
.st-key-welcome-logo-actions [data-testid="stButton"] > button { justify-content: center; }
.mode-caption { color: var(--text-muted); font-size: .76rem; }
[data-testid="stSegmentedControl"] {
  padding: .2rem; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm);
  background: var(--surface-1); gap: .15rem;
}
[data-testid="stSegmentedControl"] button {
  min-height: 2.25rem; padding: .4rem .65rem; border-radius: 5px !important;
  color: var(--text-secondary); transition: color var(--duration-fast), background var(--duration-fast);
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
  color: var(--accent-lime-strong); background: rgba(199,244,100,.1); box-shadow: inset 0 0 0 1px rgba(199,244,100,.22);
}
[data-testid="stChatMessage"] {
  max-width: 860px; margin: .8rem auto; padding: 1.1rem 0;
  border: 0; border-bottom: 1px solid var(--border-subtle); border-radius: 0; background: transparent;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { line-height: 1.7; max-width: 780px; }
[data-testid="stChatMessage"] h1, [data-testid="stChatMessage"] h2, [data-testid="stChatMessage"] h3 { letter-spacing: -.035em; }
[data-testid="stChatMessage"] a { color: var(--accent-lime-strong); text-decoration-thickness: 1px; text-underline-offset: 3px; }
[data-testid="stChatMessage"] pre, [data-testid="stCode"] pre {
  max-width: 100%; overflow-x: auto; border: 1px solid var(--border-subtle) !important;
  border-radius: var(--radius-sm) !important; background: #0d0e0b !important;
}
[data-testid="stChatMessage"] code, [data-testid="stCode"] code {
  font-family: "Cascadia Code", "SFMono-Regular", Consolas, monospace !important;
  font-size: .88em; font-variant-ligatures: none;
}
[data-testid="stChatMessage"] :not(pre) > code {
  padding: .13em .35em; border: 1px solid var(--border-subtle); border-radius: 4px;
  color: #d8f3a0; background: rgba(199,244,100,.08);
}
[data-testid="stChatInput"] {
  max-width: 860px; margin: 0 auto; border: 1px solid var(--border-strong); border-radius: var(--radius-md);
  background: var(--surface-1); box-shadow: 0 -10px 24px rgba(0,0,0,.12);
  transition: border-color var(--duration-fast), box-shadow var(--duration-fast);
}
[data-testid="stChatInput"]:focus-within {
  border-color: rgba(199,244,100,.62); box-shadow: 0 0 0 3px rgba(199,244,100,.08);
}
[data-testid="stChatInput"] textarea { color: var(--text-primary); line-height: 1.55; }
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {
  border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: #0d0e0b;
  color: var(--text-primary); transition: border-color var(--duration-fast), box-shadow var(--duration-fast);
}
[data-testid="stTextArea"] textarea:focus, [data-testid="stTextInput"] input:focus {
  border-color: rgba(199,244,100,.62); box-shadow: 0 0 0 3px rgba(199,244,100,.09);
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div { border-color: var(--border-subtle); border-radius: var(--radius-sm); background: var(--surface-1); }
[data-testid="stFileUploader"] section { border: 1px dashed rgba(199,244,100,.32); border-radius: var(--radius-sm); background: transparent; }
[data-testid="stExpander"] { border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--surface-1); overflow: hidden; }
[data-testid="stExpander"] summary { color: var(--text-primary); font-weight: 600; }
[data-testid="stTabs"] [role="tablist"] { gap: .35rem; overflow-x: auto; }
[data-testid="stTabs"] button[role="tab"] { color: var(--text-secondary); border-radius: 4px 4px 0 0; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color: var(--accent-lime-strong); }
[data-testid="stAlert"] { border-radius: var(--radius-sm); }
[data-testid="stButton"] > button, [data-testid="stFormSubmitButton"] > button {
  min-height: 2.35rem; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm);
  color: var(--text-primary); background: var(--surface-2); font-weight: 590;
  transition: border-color var(--duration-fast), background var(--duration-fast);
}
[data-testid="stButton"] > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
  border-color: rgba(199,244,100,.4); background: rgba(199,244,100,.08);
}
[data-testid="stFormSubmitButton"] > button[kind="primary"], [data-testid="stButton"] > button[kind="primary"] { border-color: rgba(199,244,100,.48); color: #15180d; background: var(--accent-lime); font-weight: 700; }
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover, [data-testid="stButton"] > button[kind="primary"]:hover { border-color: var(--accent-lime-strong); background: var(--accent-lime-strong); }
[data-testid="stButton"] > button:focus-visible, [data-testid="stFormSubmitButton"] > button:focus-visible,
[data-testid="stSegmentedControl"] button:focus-visible, [data-testid="stChatInput"]:focus-within {
  outline: 2px solid rgba(199,244,100,.8); outline-offset: 2px;
}
[data-testid="stButton"] > button:disabled, [data-testid="stFormSubmitButton"] > button:disabled {
  opacity: .48; cursor: not-allowed;
}
[data-testid="stDialog"] [role="dialog"] { border: 1px solid var(--border-strong); border-radius: var(--radius-md); background: var(--surface-1); }
.st-key-danger-zone [data-testid="stButton"] > button { color: #f2a1aa; border-color: rgba(244,125,140,.2); background: rgba(244,125,140,.045); }
.st-key-danger-zone [data-testid="stButton"] > button:hover { border-color: rgba(244,125,140,.52); background: rgba(244,125,140,.1); }
.st-key-tool-new-conversation [data-testid="stButton"] > button,
.st-key-danger-zone [data-testid="stButton"] > button {
  justify-content: center; text-align: center;
}
[data-testid="stBottomBlockContainer"] { border-top: 1px solid rgba(224,226,204,.06) !important; }
@keyframes logo-reveal {
  0% { opacity: 0; clip-path: inset(0 0 100% 0); }
  42% { opacity: 1; clip-path: inset(0 0 34% 0); }
  100% { opacity: 1; clip-path: inset(0); }
}
@keyframes logo-sweep { from { transform: translateX(0) skewX(-18deg); opacity: 0; } 20% { opacity: 1; } to { transform: translateX(520%) skewX(-18deg); opacity: 0; } }
@media (max-width: 760px) {
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    max-width: 100vw !important; overflow-x: hidden !important;
  }
  .block-container {
    width: 100%; max-width: 100%; min-width: 0; box-sizing: border-box;
    padding: 1.25rem .85rem 12rem !important; scroll-padding-bottom: 12rem;
  }
  [data-testid="stMainBlockContainer"], [data-testid="stVerticalBlock"],
  [data-testid="stHorizontalBlock"], [data-testid="stColumn"] { min-width: 0 !important; }
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  [data-testid="stColumn"] { flex: 1 1 100% !important; width: 100% !important; }
  .welcome-shell { width: 100%; box-sizing: border-box; margin: .5rem 0 .25rem; padding: 0; }
  .welcome-title { font-size: clamp(2.35rem, 11vw, 3.4rem); overflow-wrap: anywhere; }
  .welcome-copy { font-size: .9rem; }
  .vask-welcome-logo { width: 170px; margin: 1.25rem auto .5rem; }
  [data-testid="stSegmentedControl"] { width: 100%; box-sizing: border-box; flex-wrap: wrap; }
  [data-testid="stSegmentedControl"] > div { width: 100%; max-width: 100%; min-width: 0; flex-wrap: wrap; }
  [data-testid="stSegmentedControl"] button { flex: 1 1 42%; width: auto; min-width: 0; white-space: normal; line-height: 1.25; }
  [data-testid="stChatInput"] { width: 100%; box-sizing: border-box; }
  [data-testid="stChatMessage"] { padding: .9rem 0; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
</style>
""", unsafe_allow_html=True)
initialize()

if "mode_conversation_ids" not in st.session_state:
    legacy_conversation_id = st.session_state.get("conversation_id")
    st.session_state.mode_conversation_ids = {
        mode: (
            legacy_conversation_id
            if mode == "General chat" and legacy_conversation_id
            else get_or_create_mode_conversation(mode)
        )
        for mode in MODE_INSTRUCTIONS
    }
if "documents" not in st.session_state:
    st.session_state.documents = {}
if "mode_documents" not in st.session_state:
    st.session_state.mode_documents = {
        mode: (dict(st.session_state.documents) if mode == "General chat" else {})
        for mode in MODE_INSTRUCTIONS
    }
if "pending_action" not in st.session_state:
    st.session_state.pending_action = None
if "workspace_index" not in st.session_state:
    st.session_state.workspace_index = None
if "active_imported_project_id" not in st.session_state:
    st.session_state.active_imported_project_id = None
if "project_import_open" not in st.session_state:
    st.session_state.project_import_open = False
if "change_proposal" not in st.session_state:
    st.session_state.change_proposal = None
if "generate_change_request" not in st.session_state:
    st.session_state.generate_change_request = ""
if "workspace_refresh_warning" not in st.session_state:
    st.session_state.workspace_refresh_warning = ""
if "confirm_delete_history" not in st.session_state:
    st.session_state.confirm_delete_history = False
if "quick_action_notice" not in st.session_state:
    st.session_state.quick_action_notice = ""
if "assistant_mode" not in st.session_state:
    st.session_state.assistant_mode = "General chat"
if "active_workspace_mode" not in st.session_state:
    st.session_state.active_workspace_mode = st.session_state.assistant_mode
if "logo_intro_played" not in st.session_state:
    st.session_state.logo_intro_played = False


def _active_conversation_id() -> str:
    mode = st.session_state.assistant_mode
    conversation_ids = st.session_state.mode_conversation_ids
    if mode not in conversation_ids:
        conversation_ids[mode] = get_or_create_mode_conversation(mode)
    return conversation_ids[mode]


def switch_assistant_workspace() -> None:
    """Persist the current mode-local UI state before restoring the selected mode."""
    previous_mode = st.session_state.active_workspace_mode
    selected_mode = st.session_state.assistant_mode
    if previous_mode == selected_mode:
        return
    st.session_state.mode_documents[previous_mode] = st.session_state.documents
    st.session_state.documents = st.session_state.mode_documents.setdefault(selected_mode, {})
    st.session_state.pending_action = None
    _active_conversation_id()
    st.session_state.active_workspace_mode = selected_mode


def select_assistant_workspace(target_mode: str, action_title: str = "") -> None:
    """Select a mode from a callback before its segmented-control widget is built."""
    st.session_state.assistant_mode = target_mode
    switch_assistant_workspace()
    if target_mode == "General chat":
        st.session_state.quick_action_notice = (
            "Project context is active for your next question."
            if st.session_state.workspace_index
            else "Index a project in the sidebar to add code context to your questions."
        )
    elif action_title:
        st.session_state.quick_action_notice = f"{action_title} selected. Add your code and context below."


def open_project_import() -> None:
    """Open the managed project-import controls from the welcome action."""
    select_assistant_workspace("General chat", "Explore project")
    st.session_state.project_import_open = True
if "workspace_selected_files" not in st.session_state:
    st.session_state.workspace_selected_files = set()
if "workspace_expanded_dirs" not in st.session_state:
    st.session_state.workspace_expanded_dirs = set()
if "workspace_selection_root" not in st.session_state:
    st.session_state.workspace_selection_root = None
if "workspace_file_filter" not in st.session_state:
    st.session_state.workspace_file_filter = ""
if "workspace_file_widget_keys" not in st.session_state:
    st.session_state.workspace_file_widget_keys = {}


def start_new_conversation_action() -> None:
    mode = st.session_state.assistant_mode
    st.session_state.mode_conversation_ids[mode] = new_conversation(mode)
    st.session_state.documents = {}
    st.session_state.mode_documents[mode] = st.session_state.documents
    st.session_state.pending_action = None
    st.session_state.quick_action_notice = ""
    st.session_state.generate_change_request = ""
    proposal = st.session_state.change_proposal
    if proposal and proposal.state == ProposalState.READY:
        reject_proposal(proposal)
    st.session_state.change_proposal = None


def _workspace_file_widget_key(root: Path, relative_path: str) -> str:
    digest = hashlib.sha256(f"{root}\0{relative_path}".encode("utf-8")).hexdigest()[:16]
    return f"workspace_context_file_{digest}"


def _set_workspace_selection(root: Path, indexed_paths: set[str]) -> None:
    """Keep still-valid selections on refresh and reset widget state for removed files."""
    old_root = st.session_state.workspace_selection_root
    old_selection = set(st.session_state.workspace_selected_files)
    if old_root != str(root):
        old_selection.clear()
        st.session_state.workspace_expanded_dirs = set()
        st.session_state.workspace_file_filter = ""
        for key in st.session_state.workspace_file_widget_keys.values():
            st.session_state[key] = False
        st.session_state.workspace_file_widget_keys = {}
    else:
        old_selection.intersection_update(indexed_paths)
        removed_paths = []
        for path, key in st.session_state.workspace_file_widget_keys.items():
            if path not in indexed_paths:
                st.session_state[key] = False
                removed_paths.append(path)
        for path in removed_paths:
            st.session_state.workspace_file_widget_keys.pop(path, None)
    st.session_state.workspace_selection_root = str(root)
    st.session_state.workspace_selected_files = old_selection


def clear_workspace_selection() -> None:
    for key in st.session_state.workspace_file_widget_keys.values():
        st.session_state[key] = False
    st.session_state.workspace_selected_files = set()


def update_workspace_file_selection(relative_path: str, widget_key: str) -> None:
    selected = set(st.session_state.workspace_selected_files)
    if st.session_state.get(widget_key, False):
        selected.add(relative_path)
    else:
        selected.discard(relative_path)
    st.session_state.workspace_selected_files = selected


def toggle_workspace_directory(relative_path: str) -> None:
    expanded = set(st.session_state.workspace_expanded_dirs)
    if relative_path in expanded:
        expanded.remove(relative_path)
    else:
        expanded.add(relative_path)
    st.session_state.workspace_expanded_dirs = expanded


def clear_workspace_index() -> None:
    st.session_state.workspace_index = None
    st.session_state.workspace_selection_root = None
    st.session_state.workspace_selected_files = set()
    st.session_state.workspace_expanded_dirs = set()
    st.session_state.workspace_file_filter = ""
    for key in st.session_state.workspace_file_widget_keys.values():
        st.session_state[key] = False
    st.session_state.workspace_file_widget_keys = {}


def activate_imported_project(project: ImportedProject) -> None:
    """Index a managed import and preserve only selections valid for its root."""
    workspace_index = index_workspace(project.root)
    _set_workspace_selection(
        workspace_index.root,
        {file.relative_path for file in workspace_index.files},
    )
    st.session_state.workspace_index = workspace_index
    st.session_state.active_imported_project_id = project.project_id
    st.session_state.workspace_refresh_warning = ""


def render_workspace_tree(
    node: FileTreeNode,
    root: Path,
    *,
    parent: str = "",
    query: str = "",
    depth: int = 0,
    visible: list[int] | None = None,
    limit: int = 240,
) -> bool:
    """Render an expandable, bounded tree using native Streamlit controls."""
    if visible is None:
        visible = [0]
    query = query.casefold().strip()
    expanded = st.session_state.workspace_expanded_dirs
    stopped = False
    for directory, child in sorted(node.directories.items()):
        relative_dir = f"{parent}/{directory}".strip("/")
        if query and not any(query in path.casefold() for path in _tree_paths(child)):
            continue
        if visible[0] >= limit:
            return True
        is_expanded = query != "" or relative_dir in expanded
        label = ("　" * min(depth, 5)) + ("▾ " if is_expanded else "› ") + directory
        st.button(
            label,
            key="workspace_dir_" + hashlib.sha256(relative_dir.encode("utf-8")).hexdigest()[:14],
            help=f"{'Collapse' if is_expanded else 'Expand'} {relative_dir}",
            on_click=toggle_workspace_directory,
            args=(relative_dir,),
            disabled=bool(query),
            use_container_width=True,
        )
        visible[0] += 1
        if is_expanded:
            stopped = render_workspace_tree(
                child, root, parent=relative_dir, query=query, depth=depth + 1,
                visible=visible, limit=limit,
            )
            if stopped:
                return True
    for relative_path in sorted(node.files):
        if query and query not in relative_path.casefold():
            continue
        if visible[0] >= limit:
            return True
        widget_key = _workspace_file_widget_key(root, relative_path)
        st.session_state.workspace_file_widget_keys[relative_path] = widget_key
        if widget_key not in st.session_state:
            st.session_state[widget_key] = relative_path in st.session_state.workspace_selected_files
        st.checkbox(
            ("　" * min(depth, 5)) + Path(relative_path).name,
            key=widget_key,
            help=relative_path,
            on_change=update_workspace_file_selection,
            args=(relative_path, widget_key),
        )
        visible[0] += 1
    return stopped


def _tree_paths(node: FileTreeNode) -> list[str]:
    paths = list(node.files)
    for child in node.directories.values():
        paths.extend(_tree_paths(child))
    return paths


with st.sidebar:
    with st.container(key="vask-sidebar-brand"):
        logo_col, brand_col = st.columns([.8, 2.7], vertical_alignment="center")
        with logo_col:
            st.image(str(LOGO_PATH), width=47)
        with brand_col:
            st.markdown('<div class="vask-brand-name">V-Ask</div><div class="vask-brand-caption">Developer workspace</div>', unsafe_allow_html=True)

    if st.button("New conversation", key="tool_new_conversation", icon=":material/add_comment:", use_container_width=True):
        start_new_conversation_action()
        st.rerun()

    st.markdown('<div class="vask-side-label">Project context</div>', unsafe_allow_html=True)
    with st.expander(
        "Project workspace", expanded=st.session_state.project_import_open,
        icon=":material/folder_open:",
    ):
        st.caption("Import a project into V-Ask's managed workspace. Only bounded, safe text files are indexed and sent as relevant excerpts.")
        folder_tab, zip_tab = st.tabs(["Upload folder", "Upload ZIP"])
        with folder_tab:
            st.caption("Supported in this Streamlit version. Folder structure is retained from the browser upload.")
            folder_files = st.file_uploader(
                "Choose project folder", accept_multiple_files="directory",
                key="project_folder_upload", max_upload_size=MAX_PROJECT_UPLOAD_MB,
            )
            if st.button("Import folder", key="import_project_folder", icon=":material/folder_zip:", use_container_width=True):
                try:
                    with st.spinner("Validating and importing project files..."):
                        project = import_project_folder(
                            [(item.name, item.getvalue()) for item in (folder_files or [])],
                            name=(folder_files[0].name.split("/")[0] if folder_files else "Uploaded project"),
                        )
                        activate_imported_project(project)
                    st.success(f"Imported {project.imported_files:,} safe project files.")
                except ProjectImportError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("The uploaded folder could not be imported safely.")
        with zip_tab:
            st.caption("Use a ZIP archive when folder upload is unavailable in your browser.")
            zip_file = st.file_uploader(
                "Choose ZIP archive", type=["zip"], key="project_zip_upload",
                max_upload_size=MAX_PROJECT_UPLOAD_MB,
            )
            if st.button("Import ZIP", key="import_project_zip", icon=":material/archive:", use_container_width=True):
                try:
                    with st.spinner("Validating and extracting ZIP archive..."):
                        if zip_file is None:
                            raise ProjectImportError("Choose a ZIP archive first.")
                        project = import_project_zip(zip_file.name, zip_file.getvalue())
                        activate_imported_project(project)
                    st.success(f"Imported {project.imported_files:,} safe project files.")
                except ProjectImportError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("The ZIP archive could not be imported safely.")

        imported_projects = list_imported_projects()
        imported_by_id = {project.project_id: project for project in imported_projects}
        if imported_projects:
            selected_import_id = st.selectbox(
                "Previously imported projects", options=list(imported_by_id),
                format_func=lambda project_id: f"{imported_by_id[project_id].name} · {imported_by_id[project_id].imported_files:,} files",
                key="imported_project_picker",
            )
            reopen_col, remove_col = st.columns(2)
            if reopen_col.button("Open import", key="open_imported_project", icon=":material/folder_open:", use_container_width=True):
                try:
                    activate_imported_project(imported_by_id[selected_import_id])
                    st.success("Imported project indexed in this session.")
                except (ProjectImportError, WorkspaceError):
                    st.error("This imported project is unavailable.")
            if remove_col.button("Remove import", key="remove_imported_project", icon=":material/delete_outline:", use_container_width=True):
                try:
                    if st.session_state.active_imported_project_id == selected_import_id:
                        clear_workspace_index()
                        st.session_state.active_imported_project_id = None
                    remove_imported_project(selected_import_id)
                    st.success("Imported project removed from V-Ask storage.")
                    st.rerun()
                except ProjectImportError as exc:
                    st.error(str(exc))
        active_workspace = st.session_state.workspace_index
        if st.session_state.workspace_refresh_warning:
            st.warning(st.session_state.workspace_refresh_warning)
        if active_workspace:
            st.markdown(
                '<div class="vask-current-workspace"><span aria-hidden="true">●</span><div>'
                '<strong>Indexed in this session</strong><br><code>'
                + escape(str(active_workspace.root))
                + "</code></div></div>",
                unsafe_allow_html=True,
            )
            st.caption(
                f"{active_workspace.file_count:,} files · "
                f"{active_workspace.total_bytes / (1024 * 1024):.1f} MiB indexed"
            )
            if active_workspace.skipped_files:
                st.caption(f"{active_workspace.skipped_files:,} files skipped by safety or size filters.")
            if active_workspace.truncated:
                st.caption("Index limits were reached; refresh with a smaller workspace for broader coverage.")
        else:
            st.info("Upload a project folder or ZIP archive to ask questions about its code.")

        st.markdown("**Propose changes**")
        st.caption("Relevant excerpts are sent to Nebius. Project files stay untouched until you review and apply a diff.")
        with st.form("change_request_form", clear_on_submit=True):
            requested_change = st.text_area(
                "Describe the change",
                placeholder="For example: add validation to the user registration function and cover invalid inputs.",
                height=90,
            )
            generate_proposal = st.form_submit_button(
                "Generate proposal", icon=":material/difference:", use_container_width=True,
                disabled=not bool(st.session_state.workspace_index),
            )
        if generate_proposal:
            if not requested_change.strip():
                st.error("Describe the project change first.")
            elif st.session_state.change_proposal and st.session_state.change_proposal.state == ProposalState.READY:
                st.error("Review or reject the current proposal before generating another.")
            else:
                st.session_state.generate_change_request = requested_change.strip()

    active_workspace = st.session_state.workspace_index
    with st.expander(
        f"Project Explorer · {len(st.session_state.workspace_selected_files)} selected",
        expanded=False,
        icon=":material/folder_data:",
    ):
        if not active_workspace:
            st.info("Import a project in Project workspace to browse its safe, supported files.")
        elif not active_workspace.files:
            st.warning("No supported text files were found. Check the workspace path or refresh after adding source files.")
        else:
            indexed_by_path = {file.relative_path: file for file in active_workspace.files}
            available_paths = set(indexed_by_path)
            selected_paths = set(st.session_state.workspace_selected_files) & available_paths
            st.session_state.workspace_selected_files = selected_paths
            selected_chars = sum(len(indexed_by_path[path].text) for path in selected_paths)
            st.caption(f"{active_workspace.root.name or active_workspace.root} · {active_workspace.root}")
            st.caption(
                f"{len(selected_paths)} selected · ~{selected_chars:,} chars · "
                f"~{(selected_chars + 3) // 4:,} tokens estimated · "
                f"AI context limit {MAX_SELECTED_WORKSPACE_CONTEXT_CHARS:,} chars"
            )
            st.button(
                "Clear selected files",
                key="workspace_clear_selection",
                icon=":material/deselect:",
                disabled=not selected_paths,
                on_click=clear_workspace_selection,
                use_container_width=True,
            )
            if selected_paths:
                ordered_selected = sorted(selected_paths)
                shown = ", ".join(f"`{path}`" for path in ordered_selected[:5])
                if len(ordered_selected) > 5:
                    shown += f" and {len(ordered_selected) - 5} more"
                st.markdown("**Selected for AI context:** " + shown)
            else:
                st.info(
                    "No files selected. Choose files below for full-file context; without a selection, "
                    "V-Ask can still retrieve relevant indexed excerpts for your question."
                )
            st.text_input(
                "Filter files",
                key="workspace_file_filter",
                placeholder="Search paths or filenames...",
                label_visibility="collapsed",
            )
            tree = build_file_tree(active_workspace)
            visible_count = [0]
            truncated_tree = render_workspace_tree(
                tree,
                active_workspace.root,
                query=st.session_state.workspace_file_filter,
                visible=visible_count,
            )
            if truncated_tree:
                st.caption("Showing the first 240 matching tree entries. Filter paths to find other files.")
            st.caption("Only indexed text files are shown. Excluded folders, sensitive files, binary files, and oversized files are never sent.")

    st.markdown('<div class="vask-side-label">Your tools</div>', unsafe_allow_html=True)
    with st.expander("Personal notes", expanded=False, icon=":material/sticky_note_2:"):
        with st.form("note_form", clear_on_submit=True):
            note = st.text_area("Add a note", placeholder="For example: Mom's birthday is...")
            save_note = st.form_submit_button("Save note", icon=":material/save:", use_container_width=True)
        if save_note and note.strip():
            add_note(note)
            st.success("Saved on this device.")
        notes = get_notes()
        if notes:
            st.divider()
            for item in notes:
                note_col, delete_col = st.columns([4, 2], vertical_alignment="center")
                note_col.caption(item["content"])
                if delete_col.button("Delete", key=f"delnote_{item['id']}", icon=":material/delete_outline:", help="Delete note"):
                    delete_note(item["id"])
                    st.rerun()

    with st.expander(f"Attached documents · {len(st.session_state.documents)}", expanded=False, icon=":material/attach_file:"):
        if st.session_state.documents:
            for filename in list(st.session_state.documents):
                file_col, remove_col = st.columns([4, 2], vertical_alignment="center")
                file_col.caption(f"▤ {filename}")
                if remove_col.button("Remove", key=f"remove_doc_{filename}", icon=":material/close:", help=f"Remove {filename}"):
                    del st.session_state.documents[filename]
                    st.rerun()
            if st.button("Clear all files", key="clear_docs", icon=":material/delete_sweep:", use_container_width=True):
                st.session_state.documents = {}
                st.rerun()
        else:
            st.caption("No documents attached. Use the composer attachment control to add PDF or TXT files.")

    with st.expander("Desktop actions", expanded=False, icon=":material/desktop_windows:"):
        st.caption("Actions run only after you confirm them.")
        selected_app = st.selectbox("Open an application", list(APP_ALLOWLIST), key="tool_selected_app")
        if st.button(f"Confirm opening {selected_app}", key="tool_open_app", icon=":material/open_in_new:", use_container_width=True):
            try:
                st.success(open_application(selected_app))
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
        with st.form("youtube_form"):
            video_query = st.text_input("Search YouTube for music or videos")
            open_video = st.form_submit_button("Open YouTube", icon=":material/ondemand_video:", use_container_width=True)
        if open_video:
            try:
                st.success(open_youtube(video_query))
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))

    with st.container(key="danger-zone"):
        if st.button("Delete conversation history", key="tool_clear_history", icon=":material/delete_forever:", use_container_width=True):
            st.session_state.confirm_delete_history = True


@st.dialog("Delete conversation history?", icon=":material/delete_outline:", dismissible=False)
def confirm_history_deletion():
    st.write("This removes the messages in the current conversation from local history. This cannot be undone.")
    keep_col, delete_col = st.columns(2)
    if keep_col.button("Keep conversation", key="cancel_clear_history", use_container_width=True):
        st.session_state.confirm_delete_history = False
        st.rerun()
    if delete_col.button("Delete history", key="confirm_clear_history", icon=":material/delete_forever:", type="primary", use_container_width=True):
        clear_conversation(_active_conversation_id())
        st.session_state.pending_action = None
        st.session_state.change_proposal = None
        st.session_state.confirm_delete_history = False
        st.toast("Conversation history deleted.")
        st.rerun()

if st.session_state.confirm_delete_history:
    confirm_history_deletion()

def handle_mode_change() -> None:
    switch_assistant_workspace()
    st.session_state.quick_action_notice = ""


mode = st.segmented_control(
    "Assistant mode",
    options=list(MODE_INSTRUCTIONS),
    selection_mode="single",
    key="assistant_mode",
    label_visibility="collapsed",
    width="stretch",
    wrap=True,
    on_change=handle_mode_change,
) or "General chat"
_active_conversation_id()
if st.session_state.quick_action_notice:
    st.caption(st.session_state.quick_action_notice)
else:
    st.caption(MODE_HINTS[mode])

messages = get_messages(_active_conversation_id())
active_workspace = st.session_state.workspace_index
if messages:
    st.markdown(
        '<div class="vask-page-header"><div class="vask-page-eyebrow">V-Ask / Developer workspace</div>'
        '<div class="vask-page-status"><span>●</span> Conversation</div></div>',
        unsafe_allow_html=True,
    )
else:
    logo_intro_class = "logo-intro" if not st.session_state.logo_intro_played else ""
    logo_data = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    hero_logo, hero_content = st.columns([.8, 1.2], gap="large", vertical_alignment="center")
    with hero_logo:
        st.markdown(
            f'<div class="vask-welcome-logo {logo_intro_class}" aria-label="V-Ask logo">'
            f'<img src="data:image/png;base64,{logo_data}" alt="V-Ask" /></div>',
            unsafe_allow_html=True,
        )
        with st.container(key="welcome-logo-actions"):
            st.button(
                "New conversation", key="welcome_new_conversation", icon=":material/add_comment:",
                type="primary", use_container_width=True, on_click=start_new_conversation_action,
            )
            st.button(
                "Explore project", key="welcome_explore_project", icon=":material/folder_open:",
            use_container_width=True, on_click=open_project_import,
            )
    with hero_content:
        st.markdown(
            '<section class="welcome-shell">'
            '<div class="welcome-kicker">V-Ask · Developer workspace</div>'
            '<h1 class="welcome-title">Think clearly.<br>Build confidently.</h1>'
            '<p class="welcome-copy">Understand your codebase, investigate bugs, review changes, and make safe, reviewable progress in one focused workspace.</p>'
            + (
                f'<p class="welcome-status">Workspace ready · {active_workspace.file_count:,} files indexed</p>'
                if active_workspace else
                '<p class="welcome-status">Ready for your code, context, and next question</p>'
            )
            + '<p class="welcome-note">Choose a workflow below, or start with a message.</p>'
            '</section>',
            unsafe_allow_html=True,
        )
    st.session_state.logo_intro_played = True

for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if st.session_state.generate_change_request:
    request = st.session_state.generate_change_request
    st.session_state.generate_change_request = ""
    active_workspace = st.session_state.workspace_index
    if not active_workspace:
        st.error("Select and index a project workspace before generating a change proposal.")
    else:
        with st.spinner("Finding relevant project code and preparing a proposal..."):
            try:
                context_result = build_workspace_context(
                    active_workspace,
                    request,
                    st.session_state.workspace_selected_files,
                )
                retrieved = context_result.content
                paths = context_file_paths(retrieved)
                if not paths:
                    st.error("No relevant indexed source files were found. Try a more specific request or refresh the workspace.")
                else:
                    indexed = {file.relative_path: file.text for file in active_workspace.files}
                    hashes = {
                        path: hashlib.sha256(indexed[path].encode("utf-8")).hexdigest()
                        for path in sorted(paths) if path in indexed
                    }
                    raw_proposal = request_change_proposal(request, retrieved, hashes)
                    st.session_state.change_proposal = build_change_proposal(
                        active_workspace, request, raw_proposal, set(hashes)
                    )
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error("Could not generate a valid change proposal. Check the model configuration, refresh the workspace if files changed, and try again.")

proposal = st.session_state.change_proposal
if proposal:
    with st.expander(f"Project change proposal · {proposal.state.value}", expanded=proposal.state == ProposalState.READY):
        st.markdown(proposal.explanation or "No overall explanation was provided.")
        st.caption(f"Workspace: `{proposal.workspace_root}` · {len(proposal.files)} file(s)")
        if proposal.state == ProposalState.READY:
            removed = sum(
                line.startswith("-")
                for item in proposal.files for line in item.patch.splitlines()
            )
            added = sum(
                line.startswith("+")
                for item in proposal.files for line in item.patch.splitlines()
            )
            metric_files, metric_added, metric_removed = st.columns(3)
            metric_files.metric("Files affected", len(proposal.files))
            metric_added.metric("Lines added", added)
            metric_removed.metric("Lines removed", removed)
            st.info("Review each file diff. Applying changes will not run project code or tests.")
            if len(proposal.files) > 1:
                review_tabs = st.tabs([item.path for item in proposal.files])
            else:
                review_tabs = [st.container()]
            for item, review_tab in zip(proposal.files, review_tabs):
                with review_tab:
                    st.markdown(f"**{item.operation.title()} · `{item.path}`**")
                    st.caption(item.reason)
                    st.code(item.diff, language="diff", height=min(620, max(180, len(item.diff.splitlines()) * 22)))
            apply_col, reject_col, discard_col = st.columns(3)
            if apply_col.button("Apply reviewed changes", key="apply_change_proposal", type="primary", icon=":material/check:", use_container_width=True):
                active_workspace = st.session_state.workspace_index
                try:
                    if not active_workspace or resolve_workspace(active_workspace.root) != active_workspace.root:
                        proposal.state = ProposalState.CONFLICT
                        proposal.results = [{"path": "", "status": "Conflict", "detail": "The selected workspace changed. Reindex and generate a new proposal."}]
                    else:
                        results = apply_proposal(proposal, active_workspace.root)
                        if any(result["status"] == "Applied" for result in results):
                            try:
                                st.session_state.workspace_index = index_workspace(active_workspace.root)
                                st.session_state.workspace_refresh_warning = ""
                            except Exception:
                                st.session_state.workspace_refresh_warning = "Changes were applied, but the workspace index could not refresh. Reopen the imported project before asking follow-up questions."
                except Exception:
                    proposal.state = ProposalState.FAILED
                    proposal.results = [{"path": "", "status": "Failed", "detail": "The workspace could not be validated for safe application."}]
                st.rerun()
            if reject_col.button("Reject", key="reject_change_proposal", icon=":material/block:", use_container_width=True):
                reject_proposal(proposal)
                st.rerun()
            if discard_col.button("Discard", key="discard_change_proposal", icon=":material/close:", use_container_width=True):
                reject_proposal(proposal)
                st.session_state.change_proposal = None
                st.rerun()
        elif proposal.results:
            if proposal.state == ProposalState.APPLIED:
                st.success("All listed file changes were applied.")
            elif proposal.state == ProposalState.PARTIAL:
                st.warning("Some files were applied and some were not. Review each result below, refresh the workspace, and regenerate conflicted changes.")
            elif proposal.state == ProposalState.CONFLICT:
                st.warning("The workspace or target files changed. No conflicted file was overwritten; refresh the workspace and generate a new proposal.")
            elif proposal.state == ProposalState.FAILED:
                st.error("The proposal could not be fully applied. Review the per-file results below.")
            for result in proposal.results:
                label = f"`{result['path']}` — {result['status']}" if result["path"] else result["status"]
                st.markdown(f"**{label}**: {result['detail']}")
        elif proposal.state == ProposalState.REJECTED:
            st.info("Rejected. No project files were changed.")

prompt = ""
uploaded_files = []
developer_inputs = {}
if mode == "General chat":
    submitted = st.chat_input(
        "Ask about your project..." if active_workspace else "Message V-Ask...",
        accept_file="multiple",
        file_type=["pdf", "txt"],
        max_upload_size=MAX_UPLOAD_MB,
    )
    if submitted:
        uploaded_files = submitted.files if not isinstance(submitted, str) else []
        prompt = submitted.text.strip() if not isinstance(submitted, str) else submitted.strip()
else:
    mode_key = mode.casefold().replace(" ", "_")
    with st.form(f"developer_composer_{mode_key}", clear_on_submit=True):
        st.markdown(f"**{mode} · inputs**")
        request_text = st.text_input(
            "Request (optional)", key=f"developer_request_{mode_key}",
            placeholder=f"What do you want V-Ask to do? · {mode}",
        )
        developer_inputs["code"] = st.text_area(
            "Code", key=f"developer_code_{mode_key}", height=200, placeholder="Paste code here."
        )
        developer_inputs["error"] = st.text_area(
            "Error message (optional)", key=f"developer_error_{mode_key}", height=100,
        )
        developer_inputs["context"] = st.text_area(
            "Additional context (optional)", key=f"developer_context_{mode_key}", height=100,
            placeholder="Language, framework, expected behavior, constraints…",
        )
        uploaded_files = st.file_uploader(
            "Attach project notes (PDF or TXT)", type=["pdf", "txt"],
            accept_multiple_files=True, max_upload_size=MAX_UPLOAD_MB,
            key=f"developer_upload_{mode_key}",
        )
        submitted = st.form_submit_button("Send to V-Ask", icon=":material/send:", type="primary", use_container_width=True)
    if submitted:
        prompt = request_text.strip()

if submitted:
    newly_added = []
    for uploaded in uploaded_files:
        if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
            st.error(f"{uploaded.name}: exceeds the {MAX_UPLOAD_MB} MB limit.")
            continue
        if uploaded.name not in st.session_state.documents:
            try:
                st.session_state.documents[uploaded.name] = extract_text(uploaded.name, uploaded.getvalue())
                newly_added.append(uploaded.name)
            except ValueError as exc:
                st.error(f"{uploaded.name}: {exc}")
    if not prompt and uploaded_files:
        prompt = "Summarize the uploaded document(s)."
    if newly_added:
        st.toast("Attached: " + ", ".join(newly_added))
    if mode != "General chat":
        prompt = build_developer_request(
            prompt,
            developer_inputs["code"],
            developer_inputs["error"],
            developer_inputs["context"],
        )
        if not prompt:
            st.error("Add a request, code, error message, or context before submitting.")

if prompt:
    st.session_state.pending_action = detect_action(prompt) if mode == "General chat" else None
    add_message(_active_conversation_id(), "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)
    context = retrieve(prompt, st.session_state.documents)
    active_workspace = st.session_state.workspace_index
    workspace_context_result = build_workspace_context(
        active_workspace,
        prompt,
        st.session_state.workspace_selected_files,
    )
    normalized_prompt = prompt.casefold()
    summary_phrases = ("summarize", "summary", "give me an overview", "\u0074\u00f3m t\u1eaft")
    if st.session_state.documents and any(phrase in normalized_prompt for phrase in summary_phrases):
        document_text = all_document_context(st.session_state.documents)
        if document_text:
            context = "The user asked for a summary of the uploaded document(s). Summarize the source text below and mention if it is incomplete.\n\n" + document_text
        else:
            context = "The uploaded file(s) contain no extractable text. Explain that the PDF may be scanned or image-only and request a text-based copy."
    with st.chat_message("assistant"):
        if workspace_context_result.included_files:
            st.caption(
                "Selected project files included: "
                + ", ".join(f"`{path}`" for path in workspace_context_result.included_files)
            )
        if workspace_context_result.truncated_files:
            st.warning(
                "Some selected files were truncated to fit the AI context limit: "
                + ", ".join(workspace_context_result.truncated_files)
            )
        if workspace_context_result.omitted_files:
            with st.expander(f"Selected files omitted · {len(workspace_context_result.omitted_files)}"):
                for issue in workspace_context_result.omitted_files:
                    st.caption(f"{issue.path}: {issue.reason}")
        if workspace_context_result.retrieved_files:
            st.caption(
                "Relevant indexed excerpts also included: "
                + ", ".join(f"`{path}`" for path in workspace_context_result.retrieved_files)
            )
        with st.spinner("V-Ask is thinking..."):
            try:
                history = get_messages(_active_conversation_id())
                notes_text = "\n".join(f"- {n['content']}" for n in get_notes())
                note_terms = ("note", "remember", "\u0067hi ch\u00fa", "\u0111\u00e3 l\u01b0u")
                if notes_text and any(term in prompt.casefold() for term in note_terms):
                    context = (context + "\n\nThe user's personal notes:\n" + notes_text).strip()
                action = st.session_state.pending_action
                if action and action["type"] == "youtube":
                    reply = f"I can search YouTube for **{action['query']}**. Confirm below to open the results."
                elif action and action["type"] == "app":
                    reply = f"I can open **{action['name']}**. Confirm below to launch it."
                else:
                    reply = answer(
                        history[-20:], context, mode=mode,
                        workspace_context=workspace_context_result.content,
                    )
                st.markdown(reply)
                add_message(_active_conversation_id(), "assistant", reply)
            except Exception as exc:
                st.error("Could not reach the model. Check the connection, API configuration, and model availability.")

pending = st.session_state.pending_action
if pending:
    if pending["type"] == "app":
        st.info(f"Detected request: open {pending['name']}.")
        confirm_label = f"Confirm opening {pending['name']}"
    else:
        st.info(f"Detected request: search YouTube for: {pending['query']}")
        confirm_label = "Confirm opening YouTube"
    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button(confirm_label, key="confirm_detected_action"):
        try:
            result = open_application(pending["name"]) if pending["type"] == "app" else open_youtube(pending["query"])
            st.success(result)
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
        st.session_state.pending_action = None
    if cancel_col.button("Cancel", key="cancel_detected_action"):
        st.session_state.pending_action = None
        st.rerun()
