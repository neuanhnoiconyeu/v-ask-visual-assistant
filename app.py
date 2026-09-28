"""V-Ask Streamlit personal assistant."""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from config import MAX_UPLOAD_MB
from desktop_actions import APP_ALLOWLIST, detect_action, open_application, open_youtube
from llm_client import answer
from memory import (add_message, add_note, clear_conversation, delete_note,
                    get_messages, get_notes, initialize, new_conversation)
from rag import all_document_context, extract_text, retrieve
from now_playing import control_spotify, get_spotify_now_playing
import base64

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
[data-testid="stSidebar"] .music-timeline { margin: .25rem .05rem .3rem; }
[data-testid="stSidebar"] .music-progress-track { height: 4px; background: #424247; border-radius: 99px; overflow: hidden; }
[data-testid="stSidebar"] .music-progress-fill { height: 100%; background: #e7e7e9; border-radius: 99px; position: relative; }
[data-testid="stSidebar"] .music-progress-fill::after { content: ""; position: absolute; right: -4px; top: -2px; width: 8px; height: 8px; background: #fff; border-radius: 50%; }
[data-testid="stSidebar"] .music-time-row { display: flex; justify-content: space-between; margin-top: 4px; color: #a1a1aa; font-size: .72rem; line-height: 1.1; }
[data-testid="stSidebar"] .music-controls [data-testid="stButton"] > button { min-height: 1.85rem; }
[data-testid="stSidebar"] [class*="st-key-music_previous"] button,
[data-testid="stSidebar"] [class*="st-key-music_play"] button,
[data-testid="stSidebar"] [class*="st-key-music_pause"] button,
[data-testid="stSidebar"] [class*="st-key-music_next"] button {
    width: 2.45rem !important; height: 2.45rem !important; min-height: 2.45rem !important;
    border-radius: 50% !important; padding: 0 !important; display: flex !important;
    align-items: center !important; justify-content: center !important;
    background: #202126 !important; border: 1px solid #373840 !important;
    font-size: 1rem !important;
}
[data-testid="stSidebar"] [class*="st-key-music_previous"] button span,
[data-testid="stSidebar"] [class*="st-key-music_play"] button span,
[data-testid="stSidebar"] [class*="st-key-music_pause"] button span,
[data-testid="stSidebar"] [class*="st-key-music_next"] button span { margin: 0 !important; line-height: 1 !important; }
[data-testid="stSidebar"] [class*="st-key-music_play"] button > div,
[data-testid="stSidebar"] [class*="st-key-music_pause"] button > div {
    width: 100%; height: 100%; display: flex !important;
    align-items: center !important; justify-content: center !important;
}
[data-testid="stSidebar"] [class*="st-key-music_play"] button { position: relative !important; }
[data-testid="stSidebar"] [class*="st-key-music_play"] button::after {
    content: ""; position: absolute; left: 50%; top: 50%;
    width: 0; height: 0; transform: translate(-35%, -50%);
    border-top: 8px solid transparent; border-bottom: 8px solid transparent;
    border-left: 12px solid #e4e4e7;
}
[data-testid="stSidebar"] [class*="st-key-music_pause"] button { position: relative !important; }
[data-testid="stSidebar"] [class*="st-key-music_pause"] button::after {
    content: ""; position: absolute; left: 50%; top: 50%; width: 14px; height: 16px;
    transform: translate(-50%, -50%); border-radius: 2px;
    background: linear-gradient(to right, #e4e4e7 0 35%, transparent 35% 65%, #e4e4e7 65% 100%);
}
[data-testid="stSidebar"] [class*="st-key-music_previous"] button,
[data-testid="stSidebar"] [class*="st-key-music_next"] button { position: relative !important; }
[data-testid="stSidebar"] [class*="st-key-music_previous"] button [data-testid="stIconMaterial"],
[data-testid="stSidebar"] [class*="st-key-music_next"] button [data-testid="stIconMaterial"] {
    position: absolute !important; left: 50% !important; top: 50% !important;
    width: 1.4rem; height: 1.4rem; display: flex !important;
    align-items: center !important; justify-content: center !important;
    margin: 0 !important; font-size: 1.35rem !important;
    transform: translate(-50%, -50%) !important;
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

@st.cache_data(ttl=5, show_spinner=False)
def _cached_spotify_track():
    return get_spotify_now_playing()


def _player_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _render_spotify_player():
    with st.container(border=True):
        try:
            spotify_track = _cached_spotify_track()
        except Exception:
            spotify_track = None

        if spotify_track:
            art_col, song_col, refresh_col = st.columns([1, 3.2, .7], vertical_alignment="center")
            with art_col:
                artwork = spotify_track.get("artwork")
                if artwork and artwork.startswith("data:image"):
                    st.image(base64.b64decode(artwork.split(",", 1)[1]), width=54)
                else:
                    st.markdown("<div style='font-size:2rem;color:#a1a1aa'>&#9835;</div>", unsafe_allow_html=True)
            with song_col:
                st.markdown(f"**{spotify_track['title']}**")
                st.caption(spotify_track["artist"])
            if refresh_col.button(" ", icon=":material/refresh:", key="music_refresh", help="Refresh song"):
                _cached_spotify_track.clear()
                st.rerun()

            seek_value = st.query_params.get("music_seek")
            if seek_value is not None:
                try:
                    control_spotify("seek", float(seek_value))
                finally:
                    st.query_params.pop("music_seek", None)
                    _cached_spotify_track.clear()
                    st.rerun()

            spacer_left, previous_col, toggle_col, next_col, spacer_right = st.columns([1, 1, 1, 1, 1])
            if previous_col.button(" ", icon=":material/skip_previous:", key="music_previous"):
                control_spotify("previous")
                _cached_spotify_track.clear()
                st.rerun()
            toggle_key = "music_pause" if spotify_track["playing"] else "music_play"
            if toggle_col.button(" ", key=toggle_key):
                control_spotify("toggle")
                _cached_spotify_track.clear()
                st.rerun()
            if next_col.button(" ", icon=":material/skip_next:", key="music_next"):
                control_spotify("next")
                _cached_spotify_track.clear()
                st.rerun()

            duration = max(1, int(spotify_track.get("duration") or 1))
            position = min(duration, max(0, int(spotify_track.get("position") or 0)))
            progress_pct = min(100.0, (position / duration) * 100)
            components.html(
                f'''<!doctype html><html><head><style>
                    * {{ box-sizing: border-box; }}
                    html, body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; }}
                    .timeline {{ padding: 4px 2px 2px; color: #a1a1aa; font: 12px 'Be Vietnam Pro', 'Segoe UI', sans-serif; }}
                    .track {{ height: 4px; background: #424247; border-radius: 99px; overflow: visible; cursor: pointer; }}
                    .fill {{ height: 100%; width: {progress_pct:.2f}%; background: #e7e7e9; border-radius: 99px; position: relative; }}
                    .fill:after {{ content: ''; position: absolute; right: -3px; top: -2px; width: 8px; height: 8px; border-radius: 50%; background: #fff; }}
                    .times {{ display: flex; justify-content: space-between; margin-top: 7px; line-height: 14px; }}
                </style></head><body>
                    <div class="timeline"><div class="track" id="track"><div class="fill" id="fill"></div></div>
                    <div class="times"><span id="elapsed">{_player_time(position)}</span><span>{_player_time(duration)}</span></div></div>
                    <script>
                    (() => {{
                      let position = {position};
                      const duration = {duration};
                      const playing = {str(bool(spotify_track['playing'])).lower()};
                      const fill = document.getElementById('fill');
                      const elapsed = document.getElementById('elapsed');
                      document.getElementById('track').addEventListener('click', event => {{
                        const rect = event.currentTarget.getBoundingClientRect();
                        const target = Math.round(Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * duration);
                        window.top.location.search = `?music_seek=${{target}}`;
                      }});
                      const format = value => `${{Math.floor(value / 60)}}:${{String(value % 60).padStart(2, '0')}}`;
                      if (playing) setInterval(() => {{
                        position = Math.min(duration, position + 1);
                        fill.style.width = `${{Math.min(100, position / duration * 100)}}%`;
                        elapsed.textContent = format(position);
                      }}, 1000);
                    }})();
                    </script>
                </body></html>''',
                height=36,
                scrolling=False,
            )
            st.caption(spotify_track.get("album") or "Spotify Desktop")
        else:
            st.caption("Spotify Desktop - start a song to show it here.")
            if st.button("Refresh player", key="music_refresh_empty", use_container_width=True):
                _cached_spotify_track.clear()
                st.rerun()

with st.sidebar:
    st.subheader("Now listening")
    _render_spotify_player()
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

with st.popover("?", help="V-Ask tools and shortcuts", use_container_width=False):
    st.caption("TOOLS")
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

    st.divider()
    if st.button("?  New conversation", key="tool_new_conversation", use_container_width=True):
        st.session_state.conversation_id = new_conversation()
        st.session_state.documents = {}
        st.session_state.pending_action = None
        st.rerun()
    if st.button("Delete this conversation's history", key="tool_clear_history", use_container_width=True):
        clear_conversation(st.session_state.conversation_id)
        st.session_state.pending_action = None
        st.rerun()


submitted = st.chat_input(
    "How can V-Ask help?",
    accept_file="multiple",
    file_type=["pdf", "txt"],
    max_upload_size=MAX_UPLOAD_MB,
)
prompt = ""
if submitted:
    uploaded_files = submitted.files if not isinstance(submitted, str) else []
    prompt = submitted.text.strip() if not isinstance(submitted, str) else submitted.strip()
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
