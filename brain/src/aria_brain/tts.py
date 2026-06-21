"""TTS client — calls the local TTS server on PC 1 (port 5003).

The TTS server returns raw WAV bytes (audio/wav) directly. We save to a local
cache file and return its absolute path so the caller can play it.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx

from aria_brain.config import TTS_URL, TTS_VOICE

log = logging.getLogger("aria_brain.tts")

# Cache directory for generated TTS audio. Filenames are timestamp-based so
# unique per call; the dir grows slowly and the user can clear it anytime.
TTS_CACHE_DIR = Path(__file__).resolve().parents[2] / "tts_cache"


async def speak(text: str, voice: Optional[str] = None, timeout: float = 30.0) -> Optional[str]:
    """Send text to TTS, save the WAV bytes to a cache file, return the path.

    Returns None if the request fails (network down, non-2xx, empty body).
    The path is a local filesystem path — works with QSoundEffect via
    QUrl.fromLocalFile() and with most media players.
    """
    if not text.strip():
        return None
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"text": text, "voice": voice or TTS_VOICE}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(TTS_URL, json=payload)
        if r.status_code != 200:
            log.warning(f"tts: status {r.status_code} body={r.text[:300]}")
            return None
        body = r.content
        if not body:
            log.warning("tts: empty response body")
            return None
        # Save to cache. Filename = timestamp + short hash so we don't collide.
        ts_ms = int(time.time() * 1000)
        out_path = TTS_CACHE_DIR / f"aria_{ts_ms}.wav"
        out_path.write_bytes(body)
        log.info(f"tts: cached {len(body)} bytes -> {out_path}")
        return str(out_path)
    except (httpx.HTTPError, OSError) as exc:
        log.warning(f"tts: {type(exc).__name__}: {exc}")
        return None


def cleanup_cache(keep_last: int = 50) -> int:
    """Delete all but the most-recent N files in the cache. Returns count deleted."""
    if not TTS_CACHE_DIR.exists():
        return 0
    files = sorted(TTS_CACHE_DIR.glob("aria_*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    deleted = 0
    for old in files[keep_last:]:
        try:
            old.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted