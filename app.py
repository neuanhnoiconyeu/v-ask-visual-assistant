"V-Ask Streamlit personal assistant."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import MAX_UPLOAD_MB
from developer_modes import MODE_INSTRUCTIONS, build_developer_request
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
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
    padding: .15rem; border-radius: 14px; color: #f4f4f5;
    background: #08090b; border: 1px solid #252629;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] { color: #f4f4f5; }
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] { color: #a1a1aa; }
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stImage"] img { border-radius: 7px; object-fit: cover; }
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stButton"] > button {
    color: #e4e4e7; background: transparent; border: 0; min-height: 2rem;
    font-size: 1rem; padding: 0; box-shadow: none;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stButton"] > button:hover { color: #fff; background: #202124; transform: none; }
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stSlider"] { padding-top: 0; padding-bottom: 0; }
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
    st.markdown("### Tools")
    with st.expander("Personal notes", expanded=False):
        with st.form("note_form", clear_on_submit=True):
            note = st.text_area("Add a note", placeholder="For example: Mom's birthday is...")
            save_note = st.form_submit_button("Save note", use_container_width=True)
        if save_note and note.strip():
            add_note(note)
            st.success("Saved on this device.")
        notes = get_notes()
        if notes:
            st.divider()
            for item in notes:
                note_col, delete_col = st.columns([5, 1], vertical_alignment="center")
                note_col.caption(item["content"])
                if delete_col.button("?", key=f"delnote_{item['id']}", help="Delete note"):
                    delete_note(item["id"])
                    st.rerun()

    with st.expander("Desktop actions", expanded=False):
        st.caption("Actions run only after you confirm them.")
        selected_app = st.selectbox("Open an application", list(APP_ALLOWLIST), key="tool_selected_app")
        if st.button(f"Confirm opening {selected_app}", key="tool_open_app", use_container_width=True):
            try:
                st.success(open_application(selected_app))
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
        with st.form("youtube_form"):
            video_query = st.text_input("Search YouTube for music or videos")
            open_video = st.form_submit_button("Open YouTube", use_container_width=True)
        if open_video:
            try:
                st.success(open_youtube(video_query))
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))

    if st.button("New conversation", key="tool_new_conversation", use_container_width=True):
        st.session_state.conversation_id = new_conversation()
        st.session_state.documents = {}
        st.session_state.pending_action = None
        st.rerun()
    if st.button("Delete this conversation's history", key="tool_clear_history", use_container_width=True):
        clear_conversation(st.session_state.conversation_id)
        st.session_state.pending_action = None
        st.rerun()
    st.divider()

    with st.expander(f"Attached documents ({len(st.session_state.documents)})", expanded=False):
        if st.session_state.documents:
            for filename in list(st.session_state.documents):
                file_col, remove_col = st.columns([5, 1], vertical_alignment="center")
                file_col.caption(f"?? {filename}")
                if remove_col.button("?", key=f"remove_doc_{filename}", help=f"Remove {filename}"):
                    del st.session_state.documents[filename]
                    st.rerun()
            if st.button("Clear all files", key="clear_docs", use_container_width=True):
                st.session_state.documents = {}
                st.rerun()
        else:
            st.caption("Use + in the chat composer to attach PDF or TXT files.")

messages = get_messages(st.session_state.conversation_id)
for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

mode_col, mode_hint_col = st.columns([2, 5], vertical_alignment="bottom")
with mode_col:
    mode = st.selectbox("Assistant mode", list(MODE_INSTRUCTIONS), key="assistant_mode")
with mode_hint_col:
    if mode != "General chat":
        st.caption(f"{mode} is active for your next message.")

prompt = ""
uploaded_files = []
developer_inputs = {}
if mode == "General chat":
    submitted = st.chat_input(
        "How can V-Ask help?",
        accept_file="multiple",
        file_type=["pdf", "txt"],
        max_upload_size=MAX_UPLOAD_MB,
    )
    if submitted:
        uploaded_files = submitted.files if not isinstance(submitted, str) else []
        prompt = submitted.text.strip() if not isinstance(submitted, str) else submitted.strip()
else:
    with st.form("developer_composer", clear_on_submit=True):
        st.markdown(f"**{mode} inputs**")
        request_text = st.text_input("Request (optional)", placeholder=f"What should I do? ({mode})")
        developer_inputs["code"] = st.text_area(
            "Code", height=200, placeholder="Paste code here."
        )
        developer_inputs["error"] = st.text_area("Error message (optional)", height=100)
        developer_inputs["context"] = st.text_area(
            "Additional context (optional)", height=100,
            placeholder="Language, framework, expected behavior, constraints…",
        )
        uploaded_files = st.file_uploader(
            "Attach documents (PDF or TXT)", type=["pdf", "txt"],
            accept_multiple_files=True, max_upload_size=MAX_UPLOAD_MB,
        )
        submitted = st.form_submit_button("Send", icon=":material/send:")
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
                    reply = answer(history[-20:], context, mode=mode)
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
