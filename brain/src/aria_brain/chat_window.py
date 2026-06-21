"""Chat window — PyQt6 UI that talks to the Aria Brain over HTTP/WebSocket.

Features:
  - Text input + scrollback history
  - Mood indicator in status bar
  - "Speak replies" checkbox — Aria says her reply out loud via TTS
  - Hold-to-talk mic button — push to record, release to transcribe and fill input

Launch:
    python -m aria_brain.chat_window
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import sys
import tempfile
import threading
import wave
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

from PyQt6.QtCore import Qt, QMetaObject, QThread, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtMultimedia import QSoundEffect, QAudioOutput
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from aria_brain.config import ARIA_BRAIN_HOST, ARIA_BRAIN_PORT

log = logging.getLogger("aria_brain.chat_window")


def _brain_url() -> str:
    return f"http://{ARIA_BRAIN_HOST}:{ARIA_BRAIN_PORT}"


def _make_icon() -> QIcon:
    """Generate a simple icon — a violet circle with 'A'. Replace with real icon later."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=(120, 80, 200, 255), outline=(180, 140, 255, 255), width=2)
    try:
        font = ImageFont.truetype("segoeui.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    d.text((20, 8), "A", fill=(255, 255, 255, 255), font=font)
    tmp = Path.home() / ".aria_brain_icon.png"
    img.save(tmp)
    return QIcon(str(tmp))


# --- Worker threads --------------------------------------------------------

class BrainWorker(QThread):
    """Send a text message to /message."""

    reply_received = pyqtSignal(dict)

    def __init__(self, text: str, speak: bool = False, parent=None):
        super().__init__(parent)
        self.text = text
        self.speak = speak

    def run(self):
        async def _go():
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(
                    f"{_brain_url()}/message",
                    json={"text": self.text, "source": "chat_window", "speak": self.speak},
                )
                self.reply_received.emit(r.json())
        try:
            asyncio.run(_go())
        except Exception as exc:
            self.reply_received.emit({"error": str(exc), "reply": ""})


class MoodWorker(QThread):
    mood_received = pyqtSignal(dict)

    def run(self):
        try:
            r = httpx.get(f"{_brain_url()}/mood", timeout=5.0)
            self.mood_received.emit(r.json())
        except Exception as exc:
            self.mood_received.emit({"error": str(exc)})


class TranscribeWorker(QThread):
    """POST raw WAV bytes to /transcribe-bytes."""

    transcribed = pyqtSignal(str)

    def __init__(self, audio_bytes: bytes, parent=None):
        super().__init__(parent)
        self.audio_bytes = audio_bytes

    def run(self):
        async def _go():
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    f"{_brain_url()}/transcribe-bytes",
                    content=self.audio_bytes,
                    headers={"Content-Type": "audio/wav"},
                )
                data = r.json()
                return data.get("text", "")
        try:
            text = asyncio.run(_go())
            self.transcribed.emit(text)
        except Exception as exc:
            self.transcribed.emit(f"(transcribe error: {exc})")


# --- Main window -----------------------------------------------------------

class ChatWindow(QMainWindow):
    SR = 16000  # sample rate for mic

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aria — chat")
        self.setWindowIcon(_make_icon())
        self.resize(620, 520)

        # TTS playback — one QSoundEffect, reused per reply. QSoundEffect
        # plays WAV files asynchronously and emits `playingChanged` so we
        # can update the status bar.
        self._tts_effect = QSoundEffect(self)
        self._tts_effect.setLoopCount(1)
        self._tts_effect.setVolume(1.0)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # History
        self.history = QTextBrowser()
        self.history.setOpenExternalLinks(False)
        f = QFont("Segoe UI", 11)
        self.history.setFont(f)
        layout.addWidget(self.history, stretch=1)

        # Input row
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("say something to aria…")
        self.input.setFont(f)
        self.input.returnPressed.connect(self.send)
        input_row.addWidget(self.input, stretch=1)

        self.voice_btn = QPushButton("\U0001F3A4")  # mic emoji
        self.voice_btn.setToolTip("hold to record")
        self.voice_btn.setFixedWidth(40)
        self.voice_btn.setFixedHeight(36)
        self.voice_btn.pressed.connect(self._start_recording)
        self.voice_btn.released.connect(self._stop_recording)
        input_row.addWidget(self.voice_btn)

        self.speak_checkbox = QCheckBox("speak")
        self.speak_checkbox.setToolTip("Aria reads her reply out loud")
        self.speak_checkbox.setChecked(True)   # voice on by default
        input_row.addWidget(self.speak_checkbox)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

        # Status bar with mood
        self.status = QStatusBar()
        self.mood_label = QLabel("mood: ?")
        self.status.addPermanentWidget(self.mood_label)
        self.setStatusBar(self.status)
        self.refresh_mood()

        # Ctrl+L clears history
        QShortcut(QKeySequence("Ctrl+L"), self, self.history.clear)

        # Recording state
        self._recording = False
        self._recorded_chunks: list[np.ndarray] = []
        self._record_thread: threading.Thread | None = None

        self._append_system("Aria Brain at " + _brain_url())
        self._append_system("Press the mic button and hold to talk, or just type and hit Enter.")
        self._append_system("Check 'speak' to hear her replies (TTS must be running on " +
                            f"{_brain_url().replace('8770', '5003')}/tts).")

    # --- Mood ---------------------------------------------------------------

    def refresh_mood(self):
        w = MoodWorker(self)
        w.mood_received.connect(self._on_mood)
        w.start()

    def _on_mood(self, payload: dict):
        if "error" in payload:
            self.mood_label.setText("mood: offline")
            return
        v = payload.get("value", 3.0)
        label = payload.get("label", "baseline")
        self.mood_label.setText(f"mood: {v:.1f} ({label})")

    # --- History rendering --------------------------------------------------

    def _append(self, who: str, text: str, ts: str | None = None):
        ts = ts or datetime.now().strftime("%H:%M")
        color = "#aa86e8" if who == "aria" else "#7fb3ff"
        # Plain text, not HTML — escape just enough to keep formatting safe.
        safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        self.history.append(
            f'<div style="margin: 6px 0;">'
            f'<span style="color:#888;">{ts}</span> '
            f'<b style="color:{color};">{who}</b>: '
            f'<span>{safe}</span>'
            f'</div>'
        )

    def _append_system(self, text: str):
        safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        self.history.append(f'<div style="margin: 6px 0; color:#888; font-style:italic;">{safe}</div>')

    # --- Text send ----------------------------------------------------------

    def send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._append("you", text)
        self.input.setEnabled(False)
        self.send_btn.setEnabled(False)
        speak = self.speak_checkbox.isChecked()
        self.status.showMessage("thinking…" + (" (will speak)" if speak else ""))
        self.worker = BrainWorker(text, speak=speak, parent=self)
        self.worker.reply_received.connect(self._on_reply)
        self.worker.start()

    def _on_reply(self, payload: dict):
        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.input.setFocus()
        self.status.clearMessage()
        if "error" in payload and not payload.get("reply"):
            self._append_system(f"error: {payload['error']}")
            return
        reply = payload.get("reply", "")
        if reply:
            self._append("aria", reply)
            # TTS — call the local TTS server directly (PC 1, port 5003).
            # We bypass the brain's audio_url path entirely because:
            #   • brain runs on PC 2 — its 127.0.0.1:5003 is PC 2's loopback,
            #     not the XTTS server on PC 1.
            #   • audio_url is a filesystem path on PC 2, inaccessible from PC 1.
            # Calling TTS directly here always works as long as start_aria.ps1
            # launched the TTS window (takes ~30s to load XTTS weights).
            if self.speak_checkbox.isChecked():
                self._speak_direct(reply)
            # Surface drift info if the brain had to retry.
            if payload.get("drift_detected"):
                attempts = payload.get("attempts", 1)
                script = payload.get("drift_script", "non-Latin")
                self._append_system(
                    f"⚠ language drift was detected ({script}); "
                    f"took {attempts} attempts. If this keeps happening, "
                    "the LLM endpoint may need a different model."
                )
        self.refresh_mood()

    def _play_audio(self, path: str):
        """Play a WAV file via QSoundEffect. Non-blocking; updates status bar."""
        try:
            url = QUrl.fromLocalFile(str(path))
            self._tts_effect.setSource(url)
            self._tts_effect.play()
            self.status.showMessage(f"speaking: {Path(path).name}")
        except Exception as exc:
            self._append_system(f"audio playback failed: {exc}")

    def _speak_direct(self, text: str):
        """Call the local TTS server (127.0.0.1:5003) directly and play the WAV.

        The brain server runs on PC 2 and cannot reach PC 1's TTS server via
        its own loopback.  We call the server ourselves from PC 1 where it lives,
        receive raw WAV bytes, write them to a temp file, and play via QSoundEffect.
        Runs in a daemon thread so the UI stays responsive.
        """
        tts_url = os.environ.get("TTS_URL", "http://127.0.0.1:5003/tts")

        # Strip *action*/emote cues (e.g. "*grins*", "*leans in*") so TTS speaks
        # only the words, not the stage directions. The chat display still shows
        # the full reply with emotes.
        spoken = re.sub(r"\*[^*]*\*", " ", text)
        spoken = re.sub(r"\s+", " ", spoken).strip()
        if not spoken:
            return  # reply was all emotes; nothing to speak

        def _worker():
            try:
                r = httpx.post(tts_url, json={"text": spoken, "speaker": "", "language": "en"}, timeout=60.0)
                if r.status_code != 200 or not r.content:
                    log.warning(f"tts direct: status={r.status_code} body={r.text[:200]}")
                    self._append_system(f"(TTS server returned {r.status_code} — is it running at {tts_url}?)")
                    return
                # Write to a temp WAV file so QSoundEffect (which needs a file URL) can play it.
                suffix = ".wav"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(r.content)
                tmp.flush()
                tmp.close()
                # Schedule playback back on the Qt main thread.
                self._pending_tts_path = tmp.name
                QMetaObject.invokeMethod(self, "_play_pending_tts", Qt.ConnectionType.QueuedConnection)
            except Exception as exc:
                log.warning(f"tts direct: {type(exc).__name__}: {exc}")
                self._append_system(f"(TTS failed: {exc})")

        self._pending_tts_path = None
        threading.Thread(target=_worker, daemon=True).start()

    @pyqtSlot()
    def _play_pending_tts(self):
        """Qt slot — plays the WAV path written by _speak_direct's worker thread."""
        path = getattr(self, "_pending_tts_path", None)
        if path and Path(path).exists():
            self._play_audio(path)

    # --- Voice input --------------------------------------------------------

    def _start_recording(self):
        try:
            import sounddevice as sd
        except OSError as exc:
            self._append_system(f"mic error: {exc}")
            return
        self._recorded_chunks = []
        self._recording = True
        self.voice_btn.setText("\U0001F534")  # red dot
        self.status.showMessage("recording…")
        log.info("recording started")

        def _loop():
            try:
                import sounddevice as sd
                while self._recording:
                    chunk = sd.rec(int(0.1 * self.SR), samplerate=self.SR,
                                   channels=1, dtype="int16")
                    sd.wait()
                    if chunk is not None and len(chunk) > 0:
                        self._recorded_chunks.append(chunk.copy())
            except Exception as exc:
                log.warning(f"recording loop error: {exc}")
                self._recording = False

        self._record_thread = threading.Thread(target=_loop, daemon=True)
        self._record_thread.start()

    def _stop_recording(self):
        if not self._recording:
            return
        self._recording = False
        self.voice_btn.setText("\U0001F3A4")
        log.info("recording stopped, transcribing")
        # Give the record thread a beat to flush its last chunk
        if self._record_thread:
            self._record_thread.join(timeout=0.5)

        if not self._recorded_chunks:
            self.status.clearMessage()
            self._append_system("no audio captured")
            return

        try:
            audio = np.concatenate(self._recorded_chunks).reshape(-1)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SR)
                wf.writeframes(audio.tobytes())
            wav_bytes = buf.getvalue()
        except Exception as exc:
            self.status.clearMessage()
            self._append_system(f"audio encode error: {exc}")
            return

        self.status.showMessage("transcribing…")
        self.tr_worker = TranscribeWorker(wav_bytes, parent=self)
        self.tr_worker.transcribed.connect(self._on_transcribed)
        self.tr_worker.start()

    def _on_transcribed(self, text: str):
        self.status.clearMessage()
        if text.startswith("("):
            # error message
            self._append_system(text)
            return
        if text:
            self.input.setText(text)
            self.input.setFocus()
            self._append_system(f"heard: \"{text}\"")
        else:
            self._append_system("(no speech recognized)")


def main():
    app = QApplication(sys.argv)
    # When launched standalone (no tray), allow the X button to quit the app.
    # The tray sets this to False so closing the chat window doesn't kill the tray.
    app.setQuitOnLastWindowClosed(True)
    win = ChatWindow()
    # Ctrl+Q always quits, regardless of how the window was launched.
    QShortcut(QKeySequence("Ctrl+Q"), win, app.quit)
    win.show()
    # Make Ctrl-C in the parent console kill the GUI cleanly.
    import signal
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    sys.exit(app.exec())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()