"""Read and control the local Spotify Desktop media session on Windows."""
from __future__ import annotations

import asyncio
import base64
import sys


def _seconds(value) -> float:
    try:
        return max(0.0, value.total_seconds())
    except (AttributeError, TypeError):
        try:
            return max(0.0, value.duration / 10_000_000)
        except (AttributeError, TypeError):
            return 0.0


async def _spotify_session():
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SessionManager
    manager = await SessionManager.request_async()
    for session in manager.get_sessions():
        if "spotify" in session.source_app_user_model_id.casefold():
            return session
    return None


async def _read_thumbnail(props) -> str | None:
    if not props.thumbnail:
        return None
    try:
        from winrt.windows.storage.streams import DataReader
        stream = await props.thumbnail.open_read_async()
        size = int(stream.size)
        if size <= 0 or size > 5_000_000:
            return None
        reader = DataReader(stream.get_input_stream_at(0))
        await reader.load_async(size)
        image_buffer = bytearray(size)
        reader.read_bytes(image_buffer)
        raw = bytes(image_buffer)
        mime = getattr(stream, "content_type", "image/jpeg") or "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return None


async def _read_spotify_session() -> dict | None:
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
    session = await _spotify_session()
    if session is None:
        return None
    props = await session.try_get_media_properties_async()
    if not props or not props.title:
        return None
    playback = session.get_playback_info()
    timeline = session.get_timeline_properties()
    start = _seconds(timeline.start_time)
    end = _seconds(timeline.end_time)
    position = _seconds(timeline.position)
    return {
        "title": props.title,
        "artist": props.artist or "Unknown artist",
        "album": props.album_title or "",
        "playing": playback.playback_status == PlaybackStatus.PLAYING,
        "position": max(0.0, position - start),
        "duration": max(0.0, end - start),
        "artwork": await _read_thumbnail(props),
    }


async def _control(action: str, position: float | None = None) -> bool:
    session = await _spotify_session()
    if session is None:
        return False
    if action == "toggle":
        return bool(await session.try_toggle_play_pause_async())
    if action == "previous":
        return bool(await session.try_skip_previous_async())
    if action == "next":
        return bool(await session.try_skip_next_async())
    if action == "seek" and position is not None:
        return bool(await session.try_change_playback_position_async(int(position * 10_000_000)))
    return False


def get_spotify_now_playing() -> dict | None:
    """Return the current Spotify title, artist, timeline and optional artwork."""
    if sys.platform != "win32":
        return None
    return asyncio.run(_read_spotify_session())


def control_spotify(action: str, position: float | None = None) -> bool:
    """Send a playback command to Spotify Desktop through Windows media controls."""
    if sys.platform != "win32":
        return False
    return asyncio.run(_control(action, position))
