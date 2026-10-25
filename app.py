"V-Ask Streamlit personal assistant."""
from __future__ import annotations

import base64
import hashlib
from html import escape
from pathlib import Path

import streamlit as st

from config import MAX_UPLOAD_MB
from developer_modes import MODE_INSTRUCTIONS, build_developer_request
from desktop_actions import APP_ALLOWLIST, detect_action, open_application, open_youtube
from llm_client import answer, request_change_proposal
from memory import (add_message, add_note, clear_conversation, delete_note,
                    get_messages, get_notes, initialize, new_conversation)
from patch_applier import (ProposalState, apply_proposal, build_change_proposal,
                           context_file_paths, reject_proposal)
from rag import all_document_context, extract_text, retrieve
from workspace_reader import WorkspaceError, index_workspace, search_workspace

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
  --success: #c7f464;
  --danger: #f28b80;
  --radius-sm: 9px;
  --radius-md: 14px;
  --radius-lg: 20px;
  --shadow-soft: 0 18px 55px rgba(0, 0, 0, .24);
  --space-1: .35rem;
  --space-2: .65rem;
  --space-3: 1rem;
  --space-4: 1.5rem;
  --ease-ui: cubic-bezier(.2, .75, .25, 1);
  --duration-fast: 150ms;
  --duration-ui: 220ms;
  color-scheme: dark;
}
html, body, input, textarea, button, label, p, h1, h2, h3,
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
[data-testid="stWidgetLabel"] {
  font-family: Inter, "Segoe UI", system-ui, sans-serif !important;
}
html { scroll-behavior: smooth; }
.stApp {
  color: var(--text-primary) !important;
  background:
    radial-gradient(ellipse at 72% 12%, rgba(199, 244, 100, .075), transparent 38%),
    radial-gradient(ellipse at 0% 80%, rgba(190, 190, 160, .035), transparent 35%),
    var(--app-bg) !important;
  background-attachment: fixed !important;
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
.block-container { max-width: 1240px; padding: 3.1rem 2.4rem 12rem; scroll-padding-bottom: 12rem; }
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #11120e 0%, var(--sidebar-bg) 70%) !important;
  border-right: 1px solid var(--border-subtle);
}
[data-testid="stSidebar"] > div:first-child { padding: 1.35rem 1rem 1.5rem; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  color: var(--text-primary); font-weight: 650; letter-spacing: -.025em;
}
[data-testid="stSidebar"] hr { border-color: var(--border-subtle); margin: 1.05rem 0; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--text-muted); }
[data-testid="stSidebar"] [data-testid="stExpander"] {
  border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
  background: rgba(255,255,255,.018); overflow: hidden;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  color: var(--text-primary); font-weight: 600;
}
[data-testid="stSidebar"] [data-testid="stImage"] img {
  object-fit: contain; border-radius: 10px;
}
[data-testid="stSidebar"] [data-testid="stButton"] > button {
  min-height: 2.45rem; border-radius: 11px; text-align: left;
  white-space: normal; line-height: 1.35;
}
.st-key-vask-sidebar-brand { padding: .35rem .15rem .85rem; border-bottom: 1px solid var(--border-subtle); margin-bottom: .75rem; }
.vask-brand-name { color: var(--text-primary); font-size: 1.02rem; font-weight: 720; letter-spacing: -.04em; }
.vask-brand-caption { color: var(--text-muted); font-size: .7rem; letter-spacing: .08em; text-transform: uppercase; }
.vask-side-label { color: var(--text-muted); font-size: .68rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; margin: .3rem 0 .55rem; }
.vask-current-workspace {
  display: flex; gap: .55rem; align-items: flex-start; padding: .7rem .75rem;
  border: 1px solid rgba(199,244,100,.2); border-radius: var(--radius-sm);
  background: rgba(199,244,100,.045); color: var(--text-secondary); font-size: .78rem;
  overflow-wrap: anywhere;
}
.vask-current-workspace strong { color: var(--text-primary); font-weight: 600; }
.vask-current-workspace code { color: var(--text-secondary); overflow-wrap: anywhere; white-space: normal; }
.vask-page-header {
  display: flex; justify-content: space-between; align-items: center; gap: 1rem;
  padding: .15rem 0 1rem; border-bottom: 1px solid var(--border-subtle); margin-bottom: 1.3rem;
}
.vask-page-eyebrow { color: var(--text-muted); font-size: .72rem; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; }
.vask-page-status { color: var(--text-secondary); font-size: .78rem; }
.vask-page-status span { color: var(--accent-lime); }
.welcome-shell { position: relative; margin: 1.5rem 0 1rem; padding: 1.5rem 1.2rem; overflow: hidden; }
.welcome-shell.welcome-enter .welcome-copy, .welcome-shell.welcome-enter .welcome-kicker,
.welcome-shell.welcome-enter .welcome-title { animation: welcome-in 560ms var(--ease-ui) both; }
.welcome-kicker { color: var(--accent-lime); font-size: .7rem; font-weight: 700; letter-spacing: .17em; text-transform: uppercase; }
.welcome-title { max-width: 650px; margin: .95rem 0 1rem; color: var(--text-primary); font-size: clamp(2.5rem, 5.1vw, 4.7rem); font-weight: 690; letter-spacing: -.07em; line-height: .99; }
.welcome-copy { max-width: 510px; margin: 0; color: var(--text-secondary); font-size: 1rem; line-height: 1.75; }
.welcome-note { margin-top: 1.7rem; color: var(--text-muted); font-size: .74rem; letter-spacing: .015em; }
.welcome-status { display: flex; align-items: center; gap: .55rem; margin-top: 1.4rem; color: var(--text-muted); font-size: .72rem; }
.welcome-status::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--accent-lime); box-shadow: 0 0 12px rgba(199,244,100,.48); }
.welcome-orbit { display: grid; place-items: center; min-height: 350px; }
.orbit-stage { position: relative; display: grid; place-items: center; width: min(100%, 300px); aspect-ratio: 1; isolation: isolate; }
.orbit-stage::before { content: ""; position: absolute; inset: 18%; z-index: -1; border-radius: 50%; background: radial-gradient(circle, rgba(199,244,100,.15), rgba(199,244,100,.035) 48%, transparent 72%); filter: blur(14px); animation: orbit-glow 8s ease-in-out infinite alternate; }
.orbit-track { position: absolute; border: 1px solid rgba(222,226,201,.13); border-radius: 50%; animation: orbit-spin linear infinite; }
.orbit-track::after { content: ""; position: absolute; top: 50%; left: -4px; width: 7px; height: 7px; border-radius: 50%; background: var(--accent-lime); box-shadow: 0 0 14px rgba(199,244,100,.7); }
.orbit-track--outer { inset: 4%; animation-duration: 48s; }
.orbit-track--middle { inset: 16%; border-style: dashed; border-color: rgba(222,226,201,.18); animation-duration: 36s; animation-direction: reverse; }
.orbit-track--inner { inset: 28%; animation-duration: 27s; }
.orbit-track--outer::after { top: 17%; left: 85%; width: 5px; height: 5px; background: #f3f1e8; }
.orbit-track--middle::after { top: 75%; left: 14%; width: 6px; height: 6px; }
.orbit-core { display: grid; place-items: center; width: 30%; aspect-ratio: 1; border: 1px solid rgba(199,244,100,.38); border-radius: 50%; background: linear-gradient(145deg, rgba(35,38,26,.94), rgba(16,18,13,.96)); box-shadow: 0 0 70px rgba(199,244,100,.13), inset 0 0 28px rgba(199,244,100,.08); }
.orbit-core img { width: 62%; height: auto; object-fit: contain; filter: drop-shadow(0 0 16px rgba(199,244,100,.15)); }
.orbit-label { position: absolute; padding: .34rem .55rem; border: 1px solid var(--border-subtle); border-radius: 99px; background: rgba(16,17,13,.84); color: var(--text-secondary); font-size: .58rem; font-weight: 650; letter-spacing: .12em; }
.orbit-label--top { top: 19%; right: 1%; }
.orbit-label--bottom { bottom: 11%; left: 3%; }
.quick-action-title { margin: 1.1rem 0 .65rem; color: var(--text-muted); font-size: .68rem; font-weight: 700; letter-spacing: .13em; text-align: left; text-transform: uppercase; }
.mode-caption { color: var(--text-muted); font-size: .74rem; }
[data-testid="stSegmentedControl"] {
  padding: .28rem; border: 1px solid var(--border-subtle); border-radius: 13px;
  background: rgba(21,22,17,.88); gap: .2rem;
}
[data-testid="stSegmentedControl"] button {
  min-height: 2.45rem; padding: .45rem .7rem; border-radius: 9px !important;
  color: var(--text-secondary); transition: color var(--duration-fast) var(--ease-ui), background var(--duration-fast) var(--ease-ui), transform var(--duration-fast) var(--ease-ui);
}
[data-testid="stSegmentedControl"] button[aria-pressed="true"],
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
  color: var(--accent-lime-strong); background: rgba(199,244,100,.1); box-shadow: inset 0 0 0 1px rgba(199,244,100,.26);
}
[data-testid="stChatMessage"] {
  padding: 1rem 1.15rem; margin: .7rem 0; border: 1px solid var(--border-subtle);
  border-radius: 16px; background: rgba(21,22,17,.7);
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { line-height: 1.72; }
[data-testid="stChatMessage"] h1, [data-testid="stChatMessage"] h2, [data-testid="stChatMessage"] h3 { letter-spacing: -.035em; }
[data-testid="stChatMessage"] a { color: var(--accent-lime-strong); text-decoration-thickness: 1px; text-underline-offset: 3px; }
[data-testid="stChatMessage"] pre, [data-testid="stCode"] pre {
  max-width: 100%; overflow-x: auto; border: 1px solid var(--border-subtle) !important;
  border-radius: 12px !important; background: #0d0e0b !important;
}
[data-testid="stChatMessage"] code, [data-testid="stCode"] code {
  font-family: "Cascadia Code", "SFMono-Regular", Consolas, monospace !important;
  font-size: .88em; font-variant-ligatures: none;
}
[data-testid="stChatMessage"] :not(pre) > code {
  padding: .15em .38em; border: 1px solid var(--border-subtle); border-radius: 5px;
  color: #d8f3a0; background: rgba(199,244,100,.08);
}
[data-testid="stChatInput"] {
  border: 1px solid var(--border-strong); border-radius: 18px;
  background: rgba(20,21,16,.97); box-shadow: 0 14px 45px rgba(0,0,0,.28);
  transition: border-color var(--duration-ui) var(--ease-ui), box-shadow var(--duration-ui) var(--ease-ui);
}
[data-testid="stChatInput"]:focus-within {
  border-color: rgba(199,244,100,.62); box-shadow: 0 0 0 3px rgba(199,244,100,.09), 0 14px 45px rgba(0,0,0,.28);
}
[data-testid="stChatInput"] textarea { color: var(--text-primary); line-height: 1.55; }
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {
  border: 1px solid var(--border-subtle); border-radius: 11px; background: rgba(12,13,10,.82);
  color: var(--text-primary); transition: border-color var(--duration-fast) var(--ease-ui), box-shadow var(--duration-fast) var(--ease-ui);
}
[data-testid="stTextArea"] textarea:focus, [data-testid="stTextInput"] input:focus {
  border-color: rgba(199,244,100,.62); box-shadow: 0 0 0 3px rgba(199,244,100,.09);
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div { border-color: var(--border-subtle); border-radius: 11px; background: var(--surface-1); }
[data-testid="stFileUploader"] section { border: 1px dashed rgba(199,244,100,.35); border-radius: 13px; background: rgba(199,244,100,.025); }
[data-testid="stExpander"] { border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: rgba(21,22,17,.48); overflow: hidden; }
[data-testid="stExpander"] summary { color: var(--text-primary); font-weight: 600; }
[data-testid="stTabs"] [role="tablist"] { gap: .35rem; overflow-x: auto; }
[data-testid="stTabs"] button[role="tab"] { color: var(--text-secondary); border-radius: 9px 9px 0 0; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color: var(--accent-lime-strong); }
[data-testid="stAlert"] { border-radius: var(--radius-md); }
[data-testid="stButton"] > button, [data-testid="stFormSubmitButton"] > button {
  min-height: 2.55rem; border: 1px solid var(--border-subtle); border-radius: 11px;
  color: var(--text-primary); background: rgba(26,27,21,.82); font-weight: 590;
  transition: border-color var(--duration-fast) var(--ease-ui), background var(--duration-fast) var(--ease-ui), transform var(--duration-fast) var(--ease-ui), box-shadow var(--duration-fast) var(--ease-ui);
}
[data-testid="stButton"] > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
  border-color: rgba(199,244,100,.4); background: rgba(199,244,100,.08); transform: translateY(-1px);
}
[data-testid="stFormSubmitButton"] > button[kind="primary"], [data-testid="stButton"] > button[kind="primary"] { border-color: rgba(199,244,100,.48); color: #15180d; background: var(--accent-lime); font-weight: 700; }
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover, [data-testid="stButton"] > button[kind="primary"]:hover { border-color: var(--accent-lime-strong); background: var(--accent-lime-strong); }
[data-testid="stButton"] > button:focus-visible, [data-testid="stFormSubmitButton"] > button:focus-visible,
[data-testid="stSegmentedControl"] button:focus-visible, [data-testid="stChatInput"]:focus-within {
  outline: 2px solid rgba(199,244,100,.8); outline-offset: 2px;
}
[data-testid="stButton"] > button:disabled, [data-testid="stFormSubmitButton"] > button:disabled {
  opacity: .48; cursor: not-allowed; transform: none;
}
[data-testid="stDialog"] [role="dialog"] { border: 1px solid var(--border-strong); border-radius: 20px; background: var(--surface-1); box-shadow: var(--shadow-soft); }
.st-key-danger-zone [data-testid="stButton"] > button { color: #f2a1aa; border-color: rgba(244,125,140,.2); background: rgba(244,125,140,.045); }
.st-key-danger-zone [data-testid="stButton"] > button:hover { border-color: rgba(244,125,140,.52); background: rgba(244,125,140,.1); }
[class*="st-key-quick-action-"] button { text-align: left; justify-content: flex-start; min-height: 3.1rem; }
[class*="st-key-quick-action-"] button:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(199,244,100,.08); }
[data-testid="stBottomBlockContainer"] { border-top: 1px solid rgba(224,226,204,.06) !important; }
@keyframes welcome-in { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
@keyframes orbit-spin { to { transform: rotate(360deg); } }
@keyframes orbit-glow { from { opacity: .55; transform: scale(.92); } to { opacity: 1; transform: scale(1.08); } }
@media (max-width: 760px) {
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    max-width: 100vw !important; overflow-x: hidden !important;
  }
  .block-container {
    width: 100%; max-width: 100%; min-width: 0; box-sizing: border-box;
    padding: 1.25rem .85rem 13rem !important; scroll-padding-bottom: 13rem;
  }
  [data-testid="stMainBlockContainer"], [data-testid="stVerticalBlock"],
  [data-testid="stHorizontalBlock"], [data-testid="stColumn"] { min-width: 0 !important; }
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  [data-testid="stColumn"] { flex: 1 1 100% !important; width: 100% !important; }
  .welcome-shell { width: 100%; box-sizing: border-box; margin: .2rem auto .25rem; padding: 1.2rem .2rem; }
  .welcome-title { font-size: clamp(2.35rem, 11vw, 3.4rem); overflow-wrap: anywhere; }
  .welcome-copy { font-size: .9rem; }
  .welcome-orbit { min-height: 230px; }
  .orbit-stage { width: min(100%, 250px); }
  .orbit-label { font-size: .52rem; }
  [data-testid="stSegmentedControl"] { width: 100%; box-sizing: border-box; flex-wrap: wrap; }
  [data-testid="stSegmentedControl"] > div { width: 100%; max-width: 100%; min-width: 0; flex-wrap: wrap; }
  [data-testid="stSegmentedControl"] button { flex: 1 1 42%; width: auto; min-width: 0; white-space: normal; line-height: 1.25; }
  [data-testid="stChatInput"] { width: 100%; box-sizing: border-box; }
  [data-testid="stChatMessage"] { padding: .85rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
</style>
""", unsafe_allow_html=True)
initialize()

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = new_conversation()
if "documents" not in st.session_state:
    st.session_state.documents = {}
if "pending_action" not in st.session_state:
    st.session_state.pending_action = None
if "workspace_index" not in st.session_state:
    st.session_state.workspace_index = None
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
if "welcome_animation_played" not in st.session_state:
    st.session_state.welcome_animation_played = False


def start_new_conversation_action() -> None:
    st.session_state.conversation_id = new_conversation()
    st.session_state.documents = {}
    st.session_state.pending_action = None
    st.session_state.assistant_mode = "General chat"
    st.session_state.quick_action_notice = ""
    st.session_state.generate_change_request = ""
    proposal = st.session_state.change_proposal
    if proposal and proposal.state == ProposalState.READY:
        reject_proposal(proposal)
    st.session_state.change_proposal = None


def explore_project_action() -> None:
    st.session_state.assistant_mode = "General chat"
    st.session_state.quick_action_notice = (
        "Project context is ready for your next question."
        if st.session_state.workspace_index
        else "Index a project in the sidebar to add code context to your questions."
    )


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
    with st.expander("Project workspace", expanded=False, icon=":material/folder_open:"):
        st.caption("Choose a local project and V-Ask will retrieve limited, relevant excerpts for model requests.")
        st.text_input(
            "Local project directory",
            key="workspace_path_input",
            placeholder=r"C:\Projects\my-app",
            help="Enter the local project directory path on the machine running V-Ask.",
        )
        index_col, clear_col = st.columns(2)
        if index_col.button("Index / refresh", key="workspace_index_button", icon=":material/refresh:", use_container_width=True):
            try:
                if not st.session_state.workspace_path_input.strip():
                    st.error("Enter a project directory path first.")
                else:
                    st.session_state.workspace_index = index_workspace(
                        st.session_state.workspace_path_input
                    )
                    st.session_state.workspace_refresh_warning = ""
                    st.success("Workspace indexed in this session.")
            except WorkspaceError as exc:
                st.error(str(exc))
            except Exception:
                st.error("The selected workspace could not be indexed.")
        if clear_col.button("Clear", key="workspace_clear_button", icon=":material/close:", use_container_width=True):
            st.session_state.workspace_index = None
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
            st.info("No project selected yet. Index a local folder to ask questions about its code.")

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
        clear_conversation(st.session_state.conversation_id)
        st.session_state.pending_action = None
        st.session_state.change_proposal = None
        st.session_state.confirm_delete_history = False
        st.toast("Conversation history deleted.")
        st.rerun()

if st.session_state.confirm_delete_history:
    confirm_history_deletion()

messages = get_messages(st.session_state.conversation_id)
active_workspace = st.session_state.workspace_index
if messages:
    st.markdown(
        '<div class="vask-page-header"><div class="vask-page-eyebrow">V-Ask / Developer workspace</div>'
        '<div class="vask-page-status"><span>●</span> Conversation</div></div>',
        unsafe_allow_html=True,
    )
else:
    welcome_class = "welcome-enter" if not st.session_state.welcome_animation_played else ""
    st.session_state.welcome_animation_played = True
    hero_copy, hero_orbit = st.columns([1.2, .8], gap="large", vertical_alignment="center")
    with hero_copy:
        st.markdown(
            f'<section class="welcome-shell {welcome_class}">'
            '<div class="welcome-kicker">V-Ask · Your developer workspace</div>'
            '<h1 class="welcome-title">Your code.<br>Your next breakthrough.</h1>'
            '<p class="welcome-copy">Understand your codebase, investigate bugs, review changes, and shape what comes next—with V-Ask alongside you.</p>'
            + (
                f'<p class="welcome-status">Workspace ready · {active_workspace.file_count:,} files indexed</p>'
                if active_workspace else
                '<p class="welcome-status">Ready for your code, context, and next question</p>'
            )
            + '<p class="welcome-note">A focused AI workspace for thinking clearly and building confidently.</p>'
            '</section>',
            unsafe_allow_html=True,
        )
        start_col, explore_col = st.columns(2, gap="small")
        if start_col.button("New conversation", key="welcome_new_conversation", icon=":material/add_comment:", type="primary", use_container_width=True):
            start_new_conversation_action()
            st.rerun()
        if explore_col.button("Explore project", key="welcome_explore_project", icon=":material/folder_open:", use_container_width=True):
            explore_project_action()
            st.rerun()
    with hero_orbit:
        logo_data = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        st.markdown(
            '<div class="welcome-orbit"><div class="orbit-stage" role="img" aria-label="V-Ask logo surrounded by slowly orbiting lime indicators">'
            '<div class="orbit-track orbit-track--outer"></div>'
            '<div class="orbit-track orbit-track--middle"></div>'
            '<div class="orbit-track orbit-track--inner"></div>'
            f'<div class="orbit-core"><img src="data:image/png;base64,{logo_data}" alt="V-Ask" /></div>'
            '<span class="orbit-label orbit-label--top">CODE</span>'
            '<span class="orbit-label orbit-label--bottom">CONTEXT</span>'
            '</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown('<div class="quick-action-title">Developer workflows</div>', unsafe_allow_html=True)
    quick_actions = [
        ("Explain Code", "Explain Code", ":material/code:", "Understand a function, module, or code snippet."),
        ("Debug Assistant", "Debug Code", ":material/bug_report:", "Investigate an error and get concrete fixes."),
        ("Code Review", "Review Code", ":material/rule:", "Look for correctness, readability, and security issues."),
        ("Generate Tests", "Generate Tests", ":material/science:", "Draft tests that follow the supplied framework."),
        ("General chat", "Explore Project", ":material/folder_open:", "Ask questions with relevant indexed project context."),
    ]
    quick_columns = st.columns(2)
    for position, (target_mode, title, icon, help_text) in enumerate(quick_actions):
        with quick_columns[position % 2]:
            with st.container(key=f"quick-action-{position}"):
                if st.button(title, key=f"quick_mode_{position}", icon=icon, help=help_text, use_container_width=True):
                    st.session_state.assistant_mode = target_mode
                    if target_mode == "General chat":
                        st.session_state.quick_action_notice = (
                            "Project context is active for your next question."
                            if st.session_state.workspace_index
                            else "Index a project in the sidebar to add code context to your questions."
                        )
                    else:
                        st.session_state.quick_action_notice = f"{title} selected. Add your code and context below."
                    st.rerun()

def clear_quick_action_notice() -> None:
    st.session_state.quick_action_notice = ""


mode = st.segmented_control(
    "Assistant mode",
    options=list(MODE_INSTRUCTIONS),
    selection_mode="single",
    key="assistant_mode",
    label_visibility="collapsed",
    width="stretch",
    wrap=True,
    on_change=clear_quick_action_notice,
) or "General chat"
if st.session_state.quick_action_notice:
    st.caption(st.session_state.quick_action_notice)
else:
    st.caption(MODE_HINTS[mode])

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
                retrieved = search_workspace(active_workspace, request)
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
                selected_path = st.session_state.get("workspace_path_input", "").strip()
                try:
                    from workspace_reader import resolve_workspace
                    if not active_workspace or resolve_workspace(selected_path) != active_workspace.root:
                        proposal.state = ProposalState.CONFLICT
                        proposal.results = [{"path": "", "status": "Conflict", "detail": "The selected workspace changed. Reindex and generate a new proposal."}]
                    else:
                        results = apply_proposal(proposal, active_workspace.root)
                        if any(result["status"] == "Applied" for result in results):
                            try:
                                st.session_state.workspace_index = index_workspace(active_workspace.root)
                                st.session_state.workspace_refresh_warning = ""
                            except Exception:
                                st.session_state.workspace_refresh_warning = "Changes were applied, but the workspace index could not refresh. Use Index / refresh before asking follow-up questions."
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
    with st.form("developer_composer", clear_on_submit=True):
        st.markdown(f"**{mode} · inputs**")
        request_text = st.text_input("Request (optional)", placeholder=f"What do you want V-Ask to do? · {mode}")
        developer_inputs["code"] = st.text_area(
            "Code", height=200, placeholder="Paste code here."
        )
        developer_inputs["error"] = st.text_area("Error message (optional)", height=100)
        developer_inputs["context"] = st.text_area(
            "Additional context (optional)", height=100,
            placeholder="Language, framework, expected behavior, constraints…",
        )
        uploaded_files = st.file_uploader(
            "Attach project notes (PDF or TXT)", type=["pdf", "txt"],
            accept_multiple_files=True, max_upload_size=MAX_UPLOAD_MB,
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
    add_message(st.session_state.conversation_id, "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)
    context = retrieve(prompt, st.session_state.documents)
    workspace_context = ""
    active_workspace = st.session_state.workspace_index
    if active_workspace:
        workspace_context = search_workspace(active_workspace, prompt)
    normalized_prompt = prompt.casefold()
    summary_phrases = ("summarize", "summary", "give me an overview", "\u0074\u00f3m t\u1eaft")
    if st.session_state.documents and any(phrase in normalized_prompt for phrase in summary_phrases):
        document_text = all_document_context(st.session_state.documents)
        if document_text:
            context = "The user asked for a summary of the uploaded document(s). Summarize the source text below and mention if it is incomplete.\n\n" + document_text
        else:
            context = "The uploaded file(s) contain no extractable text. Explain that the PDF may be scanned or image-only and request a text-based copy."
    with st.chat_message("assistant"):
        with st.spinner("V-Ask is thinking..."):
            try:
                history = get_messages(st.session_state.conversation_id)
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
                        workspace_context=workspace_context,
                    )
                st.markdown(reply)
                add_message(st.session_state.conversation_id, "assistant", reply)
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
