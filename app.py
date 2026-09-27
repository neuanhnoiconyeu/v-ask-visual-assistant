"""V-Ask Streamlit personal assistant."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import MAX_UPLOAD_MB
from desktop_actions import APP_ALLOWLIST, detect_action, open_application, open_youtube
from llm_client import answer
from memory import (add_message, add_note, clear_conversation, delete_note,
                    get_messages, get_notes, initialize, new_conversation)
from rag import all_document_context, extract_text, retrieve

LOGO_PATH = Path(__file__).parent / "assets" / "vask-logo-transparent.png"
st.set_page_config(page_title="V-Ask | Personal AI", page_icon=LOGO_PATH, layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap');
html, body, input, textarea, button, label, p, h1, h2, h3,
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
[data-testid="stWidgetLabel"] {
    font-family: 'Be Vietnam Pro', 'Segoe UI', sans-serif !important;
}
.stApp {
    background:
      radial-gradient(ellipse at 9% 0%, rgba(214, 40, 40, .12), transparent 38%),
      radial-gradient(ellipse at 96% 12%, rgba(191, 149, 59, .13), transparent 36%),
      var(--background-color) !important;
    background-attachment: fixed !important;
    color: var(--text-color) !important;
}
[data-testid="stHeader"], header[data-testid="stHeader"], .stAppHeader {
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
}
[data-testid="stAppViewContainer"] { background: transparent !important; }
[data-testid="stToolbar"] { background: transparent !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stHeader"] [data-testid="stToolbar"] button { color: inherit !important; }
[data-testid="stDeployButton"] { background: transparent !important; }
.block-container { max-width: 1260px; padding-top: 4.5rem; padding-bottom: 5rem; }
[data-testid="stSidebar"] {
    background-image: linear-gradient(165deg, rgba(214, 40, 40, .045), transparent 58%, rgba(191, 149, 59, .035)) !important;
    border-right: 1px solid color-mix(in srgb, currentColor 12%, transparent);
}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    font-weight: 650; letter-spacing: -.02em;
}
[data-testid="stSidebar"] hr { border-color: color-mix(in srgb, currentColor 14%, transparent); margin: 1.25rem 0; }
.brand-eyebrow {
    color: #d9ad5a; font-size: .73rem; font-weight: 700;
    letter-spacing: .16em; text-transform: uppercase; margin-bottom: .35rem;
}
.brand-title { font-size: 2.2rem; line-height: 1.1; font-weight: 800; letter-spacing: -.055em; }
.brand-copy { color: color-mix(in srgb, currentColor 72%, transparent); margin-top: .55rem; font-size: .95rem; }
[data-testid="stChatMessage"] {
    border: 1px solid color-mix(in srgb, currentColor 12%, transparent);
    border-radius: 18px;
    background: color-mix(in srgb, currentColor 4%, transparent);
    padding: .85rem 1rem;
    margin: .6rem 0;
}
[data-testid="stChatInput"] {
    border-radius: 16px;
    border: 1px solid color-mix(in srgb, currentColor 18%, transparent);
}
[data-testid="stChatInput"]:focus-within {
    border-color: rgba(214,40,40,.8);
    box-shadow: 0 0 0 1px rgba(214,40,40,.35);
}
.stButton > button, [data-testid="stFormSubmitButton"] > button {
    border-radius: 11px; font-weight: 600; transition: all .16s ease;
}
.stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
    border-color: #d62828; color: inherit; transform: translateY(-1px);
}
[data-testid="stFileUploader"] section {
    border: 1px dashed rgba(214,40,40,.52);
    border-radius: 14px; background: transparent;
}
[data-testid="stAlert"] { border-radius: 14px; }
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {
    border-radius: 11px;
}
[data-testid="stBottom"], [data-testid="stBottomBlockContainer"], [data-testid="stBottomBlockContainer"] > div, .stBottomBlockContainer {
    background: transparent !important;
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

logo_col, brand_col = st.columns([1, 4], vertical_alignment="center")
with logo_col:
    st.image(str(LOGO_PATH), width=145)
with brand_col:
    st.markdown('<div class="brand-title">V-Ask</div><div class="brand-copy">A calmer space for your notes, documents, and everyday questions.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.subheader("Documents")
    uploads = st.file_uploader(
        "Upload PDF or TXT files",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        help=f"Up to {MAX_UPLOAD_MB} MB per file. Relevant excerpts are sent to Nebius when you ask a question.",
    )
    if uploads:
        for uploaded in uploads:
            if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
                st.error(f"{uploaded.name}: exceeds the {MAX_UPLOAD_MB} MB limit.")
                continue
            if uploaded.name not in st.session_state.documents:
                try:
                    st.session_state.documents[uploaded.name] = extract_text(uploaded.name, uploaded.getvalue())
                except ValueError as exc:
                    st.error(f"{uploaded.name}: {exc}")
        if st.session_state.documents:
            st.caption("In this session: " + ", ".join(st.session_state.documents))
            if st.button("Remove documents from this session"):
                st.session_state.documents = {}
                st.rerun()

    st.divider()
    st.subheader("Personal notes")
    with st.form("note_form", clear_on_submit=True):
        note = st.text_area("Add a note", placeholder="For example: Mom's birthday is...")
        save_note = st.form_submit_button("Save note")
    if save_note and note.strip():
        add_note(note)
        st.success("Saved on this device.")
    for item in get_notes():
        left, right = st.columns([5, 1])
        left.caption(item["content"])
        if right.button("x", key=f"delnote_{item['id']}", help="Delete note"):
            delete_note(item["id"])
            st.rerun()

    st.divider()
    st.subheader("Desktop actions")
    st.caption("Actions only run after you confirm them.")
    selected_app = st.selectbox("Open an application", list(APP_ALLOWLIST))
    if st.button(f"Confirm opening {selected_app}"):
        try:
            st.success(open_application(selected_app))
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
    with st.form("youtube_form"):
        video_query = st.text_input("Search YouTube for music or videos")
        open_video = st.form_submit_button("Open YouTube")
    if open_video:
        try:
            st.success(open_youtube(video_query))
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))

    st.divider()
    if st.button("New conversation", use_container_width=True):
        st.session_state.conversation_id = new_conversation()
        st.rerun()
    if st.button("Delete this conversation's history", use_container_width=True):
        clear_conversation(st.session_state.conversation_id)
        st.rerun()

messages = get_messages(st.session_state.conversation_id)
for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("How can V-Ask help?")
if prompt:
    st.session_state.pending_action = detect_action(prompt)
    add_message(st.session_state.conversation_id, "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)
    context = retrieve(prompt, st.session_state.documents)
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
                    reply = answer(history[-20:], context)
                st.markdown(reply)
                add_message(st.session_state.conversation_id, "assistant", reply)
            except Exception as exc:
                st.error(f"Could not reach the model: {exc}")

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
