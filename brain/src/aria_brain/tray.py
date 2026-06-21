"""System-tray icon — the always-visible entry point to Aria.

Right-click menu:
  • Chat with Aria       — opens the PyQt6 chat window
  • Open Dashboard       — opens the existing streamlit dashboard (or new dashboard)
  • Voice on/off         — toggles push-to-talk voice mode (Phase 3 placeholder)
  • Shutdown Aria        — sends shutdown signal to Brain + closes Godot Aria
  • About                — shows brain status
  • Quit tray            — leaves the tray running, just closes this menu

Launch:
    python -m aria_brain.tray
or after `uv sync`:
    uv run aria_brain_tray
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

import httpx
import pystray
from PIL import Image, ImageDraw, ImageFont

from aria_brain.config import ARIA_BRAIN_HOST, ARIA_BRAIN_PORT, ARIA_HEALTH_LOG_PATH

log = logging.getLogger("aria_brain.tray")


def _brain_url() -> str:
    return f"http://{ARIA_BRAIN_HOST}:{ARIA_BRAIN_PORT}"


def _make_icon_image() -> Image.Image:
    """Violet circle with 'A' for the tray icon."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=(120, 80, 200, 255), outline=(180, 140, 255, 255), width=2)
    try:
        font = ImageFont.truetype("segoeui.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    d.text((20, 8), "A", fill=(255, 255, 255, 255), font=font)
    return img


def _health_log(line: str) -> None:
    try:
        ARIA_HEALTH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ARIA_HEALTH_LOG_PATH, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"{datetime.utcnow().isoformat()}Z\taria_tray\t{line}\n")
    except OSError:
        pass


def _open_chat_window(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Launch the PyQt6 chat window in a subprocess."""
    _health_log("tray: open chat window")
    subprocess.Popen(
        [sys.executable, "-m", "aria_brain.chat_window"],
        cwd=str(Path(__file__).resolve().parents[1]),
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


def _open_dashboard(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Open the existing astro_assistant Streamlit dashboard (placeholder URL)."""
    import webbrowser
    _health_log("tray: open dashboard")
    webbrowser.open("http://127.0.0.1:8501")  # streamlit default


def _shutdown_aria(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Tell the Brain to shut down. (Does not kill Godot Aria — that's a separate command.)"""
    try:
        r = httpx.post(f"{_brain_url()}/shutdown", timeout=5.0)
        _health_log(f"tray: shutdown brain -> {r.status_code}")
    except Exception as exc:
        _health_log(f"tray: shutdown brain FAILED: {exc}")


def _about(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Show brain status as a notification balloon."""
    try:
        r = httpx.get(f"{_brain_url()}/health", timeout=5.0)
        data = r.json()
        msg = (
            f"brain v{data['brain_version']}\n"
            f"memory: {data['memory']['backend']} "
            f"({data['memory']['episodic_count']} episodic, "
            f"{data['memory']['facts_count']} facts, "
            f"{data['memory']['thoughts_count']} thoughts)\n"
            f"mood: {data['mood']['value']:.1f} ({data['mood']['label']})"
        )
    except Exception as exc:
        msg = f"brain offline: {exc}"
    icon.notify(msg, title="Aria Brain")


def _quit_tray(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    _health_log("tray: quit")
    icon.stop()


def _toggle_voice(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    """Voice mode toggle — stub for Phase 3."""
    _health_log("tray: voice toggle requested (Phase 3 stub)")


def _reflect_now(icon: pystray.Icon, item: pystray.MenuItem) -> None:
    try:
        r = httpx.post(f"{_brain_url()}/reflect", timeout=30.0)
        data = r.json()
        icon.notify(f"mood {data['mood']:.1f} :: {data['thought'][:100]}", title="Aria reflection")
    except Exception as exc:
        icon.notify(f"reflection failed: {exc}", title="Aria Brain")


def build_icon() -> pystray.Icon:
    menu = pystray.Menu(
        pystray.MenuItem("Chat with Aria", _open_chat_window, default=True),
        pystray.MenuItem("Open Dashboard", _open_dashboard),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Reflect now", _reflect_now),
        pystray.MenuItem("Voice (push-to-talk)", _toggle_voice, checked=lambda item: False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Shutdown Aria", _shutdown_aria),
        pystray.MenuItem("About", _about),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit tray", _quit_tray),
    )
    return pystray.Icon("aria_brain", _make_icon_image(), "Aria Brain", menu)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    _health_log("tray: starting")
    icon = build_icon()
    icon.run()


if __name__ == "__main__":
    main()