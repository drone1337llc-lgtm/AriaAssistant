"""
AstroBud edge client (runs on PC 1 — the gaming / dev machine).

Captures screen + mic, ships frames and audio to the AI server over
WebSocket, and plays whatever TTS audio comes back. Also handles
local-only tasks like pyautogui typing, media keys, and global hotkeys.

This client has zero AI / LLM dependencies — it's a thin I/O pipe.
All the heavy lifting happens on PC 2 (the server).

Run:    python client.py
Config: config.json -> server_url
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import sys
import time
from pathlib import Path

import cv2
import mss
import numpy as np
import websockets

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import transport


def load_config() -> dict:
    p = PROJECT_ROOT / "config.json"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict) -> None:
    p = PROJECT_ROOT / "config.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ---- Screen capture ----

def capture_jpeg(quality: int = 70) -> tuple[bytes, int, int] | None:
    """Grab the primary monitor and return (jpeg_bytes, width, height)."""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = np.array(sct.grab(monitor))
        # mss returns BGRA; OpenCV wants BGR for JPEG
        bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return None
        h, w = bgr.shape[:2]
        return buf.tobytes(), w, h
    except Exception as e:
        print(f"[Client] capture error: {e}")
        return None


# ---- Audio capture + playback ----

def record_wav(duration_s: float = 3.0, sample_rate: int = 16000) -> bytes:
    """Record from the default mic and return raw WAV bytes (int16 mono)."""
    import sounddevice as sd
    import scipy.io.wavfile as sio
    n_frames = int(duration_s * sample_rate)
    print(f"[Client] Recording {duration_s}s of audio...")
    recording = sd.rec(n_frames, samplerate=sample_rate, channels=1, dtype="int16")
    sd.wait()
    buf = io.BytesIO()
    sio.write(buf, sample_rate, recording)
    return buf.getvalue()


def play_wav(wav_bytes: bytes) -> None:
    """Play a WAV byte string through the default output device."""
    if not wav_bytes:
        return
    try:
        import sounddevice as sd
        import soundfile as sf
        data, fs = sf.read(io.BytesIO(wav_bytes))
        sd.play(data, fs)
        sd.wait()
    except Exception as e:
        print(f"[Client] playback error: {e}")


# ---- Local-only Windows tools ----

def local_typing(code: str) -> None:
    """Type code into the active window. Local-only — must run on PC 1."""
    import pyautogui
    pyautogui.FAILSAFE = True
    print("[Client] Typing code in 3s — click into your editor now!")
    time.sleep(3.0)
    pyautogui.write(code, interval=0.005)
    print("[Client] Typing complete.")


def local_volume(action: str) -> None:
    """Adjust the local master volume (pycaw)."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        a = action.lower() if isinstance(action, str) else ""
        if a == "mute":
            volume.SetMute(1, None)
        elif a == "unmute":
            volume.SetMute(0, None)
        elif a == "up":
            cur = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(min(cur + 0.15, 1.0), None)
        elif a == "down":
            cur = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(max(cur - 0.15, 0.0), None)
        elif isinstance(action, int) and 0 <= action <= 100:
            volume.SetMasterVolumeLevelScalar(action / 100.0, None)
    except Exception as e:
        print(f"[Client] local volume error: {e}")


# ---- Global hotkeys (Windows; needs admin) ----

def register_hotkeys(on_summon, on_mute, on_describe, on_flag_bug=None, on_export_bugs=None) -> bool:
    try:
        import keyboard
    except ImportError:
        print("[Client] `keyboard` not installed; global hotkeys disabled.")
        print("[Client] Run: pip install keyboard  (then run as Administrator).")
        return False
    try:
        keyboard.add_hotkey("f1", on_summon, suppress=False)
        keyboard.add_hotkey("f2", on_mute, suppress=False)
        keyboard.add_hotkey("f3", on_describe, suppress=False)
        if on_flag_bug:
            keyboard.add_hotkey("f4", on_flag_bug, suppress=False)
        if on_export_bugs:
            keyboard.add_hotkey("f5", on_export_bugs, suppress=False)
        print(
            "[Client] Hotkeys: F1=summon  F2=mute  F3=describe  F4=flag bug  F5=export bugs "
            "(run as Admin for global hooks)"
        )
        return True
    except Exception as e:
        print(f"[Client] Hotkey register failed: {e}")
        return False


# ---- Main async client ----

class AstroClient:
    def __init__(self, server_url: str, frame_fps: float = 1.0, jpeg_quality: int = 70):
        self.server_url = server_url
        self.frame_interval = 1.0 / max(frame_fps, 0.1)
        self.jpeg_quality = jpeg_quality
        self.muted = False
        self.ws = None
        self._frame_task = None
        self._recv_task = None
        self._stopped = False

    # ---- Public hooks (called by hotkey thread) ----

    def hotkey_summon(self) -> None:
        """F1: record 3s of audio, send to server."""
        if not self.ws:
            return
        wav_bytes = record_wav(duration_s=3.0)
        if wav_bytes:
            asyncio.run_coroutine_threadsafe(
                self._send_audio(wav_bytes, duration_s=3.0),
                self._loop,
            )

    def hotkey_describe(self) -> None:
        """F3: ask server to describe the current screen."""
        if not self.ws:
            return
        asyncio.run_coroutine_threadsafe(
            transport.send_json(self.ws, transport.command_message("describe_screen")),
            self._loop,
        )

    def hotkey_mute(self) -> None:
        """F2: toggle local TTS playback (we just don't play incoming audio)."""
        self.muted = not self.muted
        print(f"[Client] TTS {'MUTED' if self.muted else 'UNMUTED'}")

    def hotkey_flag_bug(self) -> None:
        """Ctrl+Shift+F4: capture a fresh high-quality frame and send a flag_bug command
        to the server, which persists the frame + OCR text + auto-triage into the bug log."""
        if not self.ws:
            return
        # Use higher JPEG quality for bug captures (90 vs the stream's 70)
        cap = capture_jpeg(quality=90)
        if cap is None:
            print("[Client] Ctrl+Shift+F4: capture failed.")
            return
        jpeg, w, h = cap
        print(f"[Client] Ctrl+Shift+F4 pressed -> flagging bug with {w}x{h} frame ({len(jpeg)//1024} KB)")
        asyncio.run_coroutine_threadsafe(
            transport.send_json(self.ws, transport.flag_bug_command(jpeg, w, h)),
            self._loop,
        )

    def hotkey_export_bugs(self) -> None:
        """Ctrl+Shift+F5: ask the server to export the most recent bug entries
        as Markdown, and push the text to the local clipboard for easy pasting."""
        if not self.ws:
            return
        print("[Client] Ctrl+Shift+F5 pressed -> requesting bug export (10 most recent, markdown)")
        # Use cfg to determine how many to export; default 10
        try:
            cfg = load_config()
            last_n = int(cfg.get("export_last_n", 10))
        except Exception:
            last_n = 10
        asyncio.run_coroutine_threadsafe(
            transport.send_json(
                self.ws,
                transport.export_bugs_command(last_n=last_n, fmt="markdown", copy_to_clipboard=True),
            ),
            self._loop,
        )

    # ---- Async core ----

    async def _send_audio(self, wav_bytes: bytes, duration_s: float) -> None:
        try:
            await transport.send_json(
                self.ws,
                transport.audio_message(wav_bytes, sample_rate=16000, duration_s=duration_s),
            )
        except Exception as e:
            print(f"[Client] audio send failed: {e}")

    async def _frame_producer(self) -> None:
        while not self._stopped:
            try:
                cap = await asyncio.to_thread(capture_jpeg, self.jpeg_quality)
                if cap is not None:
                    jpeg, w, h = cap
                    await transport.send_json(self.ws, transport.frame_message(jpeg, w, h))
            except websockets.ConnectionClosed:
                return
            except Exception as e:
                print(f"[Client] frame loop error: {e}")
            await asyncio.sleep(self.frame_interval)

    async def _recv_loop(self) -> None:
        try:
            async for raw in self.ws:
                try:
                    msg = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode("utf-8"))
                except Exception:
                    continue
                mtype = msg.get("type")
                if mtype == transport.TTS_AUDIO:
                    if self.muted:
                        continue
                    try:
                        wav_bytes = transport.get_b64_data(msg)
                    except Exception:
                        continue
                    await asyncio.to_thread(play_wav, wav_bytes)
                elif mtype in (transport.TEXT, transport.INFO):
                    print(f"[Server] {msg.get('text','')}")
                elif mtype == transport.TRANSCRIPT:
                    print(f"[Whisper] {msg.get('text','')}")
                elif mtype == transport.TYPING:
                    code = msg.get("code", "")
                    if code:
                        await asyncio.to_thread(local_typing, code)
                elif mtype == transport.VOLUME:
                    level = msg.get("level")
                    await asyncio.to_thread(local_volume, level)
                elif mtype == transport.TOOL:
                    print(f"[Tool:{msg.get('name')}] {msg.get('result','')[:200]}")
                elif mtype == transport.BUG_LOGGED:
                    print(f"[Bug] {msg.get('id','')} -> {msg.get('summary','')}")
                elif mtype == transport.PONG:
                    pass
        except websockets.ConnectionClosed:
            print("[Client] Server closed connection.")

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        backoff = 1.0
        while not self._stopped:
            try:
                print(f"[Client] Connecting to {self.server_url} ...")
                async with websockets.connect(self.server_url, max_size=64 * 1024 * 1024) as ws:
                    self.ws = ws
                    backoff = 1.0
                    print(f"[Client] Connected.")
                    self._frame_task = asyncio.create_task(self._frame_producer())
                    self._recv_task = asyncio.create_task(self._recv_loop())
                    await asyncio.gather(self._frame_task, self._recv_task)
            except (OSError, websockets.WebSocketException) as e:
                print(f"[Client] Connection error: {e}. Reconnecting in {backoff:.0f}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", help="WebSocket URL, e.g. ws://192.168.10.2:8765")
    parser.add_argument("--fps", type=float, default=1.0, help="Screen capture frames per second")
    parser.add_argument("--quality", type=int, default=70, help="JPEG quality 1-100")
    args = parser.parse_args()

    cfg = load_config()
    server_url = args.server or cfg.get("server_url") or "ws://127.0.0.1:8765"
    frame_fps = args.fps or cfg.get("client_frame_fps", 1.0)
    jpeg_quality = args.quality or cfg.get("client_jpeg_quality", 70)

    print(f"[Client] Target server: {server_url}")
    print(f"[Client] Frame rate: {frame_fps} FPS, JPEG quality: {jpeg_quality}")

    client = AstroClient(server_url, frame_fps=frame_fps, jpeg_quality=jpeg_quality)

    # Hotkeys (best-effort)
    register_hotkeys(
        client.hotkey_summon,
        client.hotkey_mute,
        client.hotkey_describe,
        on_flag_bug=client.hotkey_flag_bug,
        on_export_bugs=client.hotkey_export_bugs,
    )

    # Optional: console fallback ("press Enter to talk")
    import threading
    def console_loop():
        while True:
            try:
                input()
            except EOFError:
                return
            client.hotkey_summon()
    threading.Thread(target=console_loop, daemon=True).start()

    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n[Client] Shutting down.")


if __name__ == "__main__":
    main()
