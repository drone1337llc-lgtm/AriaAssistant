"""
Network transport for the two-PC AstroBud setup.

Shared protocol used by both `client.py` (PC 1, edge node) and `server.py`
(PC 2, AI server). All messages are JSON dicts with a "type" field; binary
data (screen frames, audio) is base64-encoded inside the JSON.

Why JSON+base64 instead of raw binary WebSocket frames?
    - Simpler to debug (you can `wscat` or print the messages)
    - 33% bandwidth overhead is negligible on gigabit Ethernet
    - Easier to extend with new message types

Message types (client -> server):
    frame     : screen capture, base64 JPEG
    audio     : mic recording, base64 WAV int16 mono
    hotkey    : user pressed F1/F2/F3/F4
    command   : misc control (describe_screen, summon, flag_bug, etc.)
    ping      : keepalive

Message types (server -> client):
    tts_audio : base64 WAV to play
    text      : status / log line to print
    transcript: STT result of a recent audio chunk
    info      : generic info message
    pong      : reply to ping
    typing    : pyautogui typing request (server asks client to type)
    volume    : set Windows master volume on PC 1
    tool      : tool-call result to display
    bug_logged: confirms a flag_bug command was persisted
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Any, Awaitable, Callable, Optional


# ---- Message type constants ----

# Client -> server
FRAME = "frame"
AUDIO = "audio"
HOTKEY = "hotkey"
COMMAND = "command"
PING = "ping"

# Server -> client
TTS_AUDIO = "tts_audio"
TEXT = "text"
TRANSCRIPT = "transcript"
INFO = "info"
PONG = "pong"
TYPING = "typing"
VOLUME = "volume"
TOOL = "tool"
BUG_LOGGED = "bug_logged"


# ---- Builders ----

def frame_message(jpeg_bytes: bytes, width: int, height: int, ts: float | None = None) -> dict[str, Any]:
    return {
        "type": FRAME,
        "ts": ts or time.time(),
        "width": width,
        "height": height,
        "data": base64.b64encode(jpeg_bytes).decode("ascii"),
    }


def audio_message(wav_bytes: bytes, sample_rate: int = 16000, duration_s: float = 0.0, ts: float | None = None) -> dict[str, Any]:
    return {
        "type": AUDIO,
        "ts": ts or time.time(),
        "sample_rate": sample_rate,
        "duration_s": duration_s,
        "data": base64.b64encode(wav_bytes).decode("ascii"),
    }


def hotkey_message(key: str) -> dict[str, Any]:
    return {"type": HOTKEY, "key": key}


def command_message(cmd: str, **kwargs: Any) -> dict[str, Any]:
    return {"type": COMMAND, "cmd": cmd, **kwargs}


def tts_audio_message(wav_bytes: bytes) -> dict[str, Any]:
    return {
        "type": TTS_AUDIO,
        "ts": time.time(),
        "data": base64.b64encode(wav_bytes).decode("ascii"),
    }


def text_message(text: str, level: str = "info") -> dict[str, Any]:
    return {"type": TEXT, "level": level, "text": text}


def transcript_message(text: str) -> dict[str, Any]:
    return {"type": TRANSCRIPT, "text": text}


def info_message(text: str) -> dict[str, Any]:
    return {"type": INFO, "text": text}


def typing_message(code: str) -> dict[str, Any]:
    return {"type": TYPING, "code": code}


def volume_message(level: int) -> dict[str, Any]:
    """level: 0-100, or -1 to toggle mute, or 'down'/'up' for relative."""
    return {"type": VOLUME, "level": level}


def tool_message(name: str, result: str) -> dict[str, Any]:
    return {"type": TOOL, "name": name, "result": result[:1000]}


def bug_logged_message(bug_id: str, summary: str = "") -> dict[str, Any]:
    return {"type": BUG_LOGGED, "id": bug_id, "summary": summary}


def flag_bug_command(jpeg_bytes: bytes, width: int, height: int) -> dict[str, Any]:
    """Ctrl+Shift+F4 hotkey payload — high-quality frame + a flag telling the server to persist a bug entry."""
    return {
        "type": COMMAND,
        "cmd": "flag_bug",
        "width": width,
        "height": height,
        "data": base64.b64encode(jpeg_bytes).decode("ascii"),
    }


def export_bugs_command(last_n: int = 10, fmt: str = "markdown", copy_to_clipboard: bool = True) -> dict[str, Any]:
    """Ctrl+Shift+F5 hotkey payload — request the server export the last N bugs."""
    return {
        "type": COMMAND,
        "cmd": "export_bugs",
        "last_n": last_n,
        "fmt": fmt,
        "copy_to_clipboard": copy_to_clipboard,
    }


# ---- Convenience decoders ----

def get_b64_data(msg: dict[str, Any]) -> bytes:
    """Extract base64 payload and decode to bytes."""
    return base64.b64decode(msg["data"])


# ---- Async send/recv helpers ----

async def send_json(ws, msg: dict[str, Any]) -> None:
    """Send a JSON message over the WebSocket."""
    await ws.send(json.dumps(msg))


async def recv_json(ws) -> dict[str, Any]:
    """Receive and parse a JSON message from the WebSocket."""
    raw = await ws.recv()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return json.loads(raw)
