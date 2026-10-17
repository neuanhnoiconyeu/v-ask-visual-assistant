"""Nebius Token Factory client using the OpenAI-compatible API."""
from __future__ import annotations

import os
from datetime import datetime
from openai import OpenAI
import streamlit as st

from config import NEBIUS_BASE_URL, NEBIUS_MODEL, SYSTEM_PROMPT
from developer_modes import MODE_INSTRUCTIONS


def _client() -> OpenAI:
    key = os.getenv("NEBIUS_API_KEY", "").strip()
    if not key:
        try:
            key = str(st.secrets.get("NEBIUS_API_KEY", "")).strip()
        except Exception:
            # Streamlit raises when no secrets file/config is present.
            key = ""
    if not key:
        raise RuntimeError("NEBIUS_API_KEY is not configured. Add your Nebius API key to Streamlit secrets.")
    return OpenAI(api_key=key, base_url=NEBIUS_BASE_URL)


def answer(messages: list[dict[str, str]], context: str = "", mode: str = "General chat") -> str:
    """Generate a response. Only the relevant local excerpts are sent upstream."""
    local_now = datetime.now().astimezone()
    current_date = local_now.strftime("%A, %Y-%m-%d %H:%M %Z")
    system = SYSTEM_PROMPT + f"\n\nCurrent local date and time on the app host: {current_date}. Use this as the source of truth for questions about today, current time, or relative dates; do not guess from prior knowledge."
    if mode not in MODE_INSTRUCTIONS:
        raise ValueError(f"Unknown assistant mode: {mode}")
    if MODE_INSTRUCTIONS[mode]:
        system += "\n\nDeveloper mode instructions:\n" + MODE_INSTRUCTIONS[mode]
    if context:
        system += "\n\nRelevant excerpts from the user's uploaded documents follow.\n" + context
    response = _client().chat.completions.create(
        model=os.getenv("NEBIUS_MODEL", NEBIUS_MODEL),
        messages=[{"role": "system", "content": system}, *messages],
        temperature=0.4,
    )
    if not response.choices:
        return "The model returned no response. Please try again."
    content = response.choices[0].message.content
    return content.strip() if isinstance(content, str) and content.strip() else "The model returned no content. Please try again."
