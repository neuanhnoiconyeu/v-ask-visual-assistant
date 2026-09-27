"""Explicit, allowlisted desktop actions. Never execute model-generated shell commands."""
from __future__ import annotations

import platform
import re
import subprocess
import webbrowser
from urllib.parse import quote_plus

# Edit these display names and paths for your own computer. No arbitrary shell input is accepted.
APP_ALLOWLIST = {
    "notepad": {"Windows": ["notepad.exe"], "Darwin": ["open", "-a", "TextEdit"], "Linux": ["gedit"]},
    "calculator": {"Windows": ["calc.exe"], "Darwin": ["open", "-a", "Calculator"], "Linux": ["gnome-calculator"]},
}


def detect_action(request: str) -> dict[str, str] | None:
    """Detect a narrow desktop intent; the UI must ask for confirmation."""
    text = request.strip()
    lowered = text.casefold()
    music_terms = (
        "\u0062\u1eadt nh\u1ea1c", "\u0070\u0068\u00e1\u0074 nh\u1ea1c",
        "\u006d\u1edf nh\u1ea1c", "\u0062\u00e0i h\u00e1t", "\u006e\u0068\u1ea1c",
        "play music", "play song", "listen to music", "turn on music",
    )
    generic_play = any(term in lowered for term in music_terms) or bool(
        re.search(r"\b(play|listen to|turn on)\b", lowered)
    )
    youtube_intent = any(term in lowered for term in ("youtube", "video", "\u0076\u0069\u0064\u0065\u006f"))

    if generic_play or youtube_intent:
        query = re.sub(
            r"(?i)\b(gi\u00fap t\u00f4i|cho t\u00f4i|m\u1edf|b\u1eadt|ph\u00e1t|t\u00ecm|youtube|video|b\u00e0i h\u00e1t|nh\u1ea1c|play|listen to|turn on|song|music)\b",
            " ", text,
        )
        query = re.sub(r"\s+", " ", query).strip(" :,-")
        if not query:
            query = "music" if any(term in lowered for term in ("play", "listen", "turn on", "music")) else "\u006e\u0068\u1ea1c"
        return {"type": "youtube", "query": query}

    if any(word in lowered for word in ("\u006d\u1edf", "open", "\u006b\u0068\u1edfi ch\u1ea1y")):
        for name in APP_ALLOWLIST:
            if name in lowered:
                return {"type": "app", "name": name}
    return None


def open_application(app_name: str) -> str:
    key = app_name.casefold().strip()
    if key not in APP_ALLOWLIST:
        raise ValueError("That application is not in the allowlist. Add it in desktop_actions.py.")
    command = APP_ALLOWLIST[key].get(platform.system())
    if not command:
        raise RuntimeError(f"{key} is not configured for {platform.system()}.")
    subprocess.Popen(command, shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"Sent a request to open {key}."


def open_youtube(query: str) -> str:
    query = query.strip()
    if not query:
        raise ValueError("Enter a song or video title.")
    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    if not webbrowser.open(url, new=2):
        raise RuntimeError("Could not open the default browser.")
    return "Opened YouTube search results in your default browser."
