#!/usr/bin/env python3
"""
AstroBud Desktop Overlay — animated companion integrated with the AstroBud backend.
AI:    LM Studio (lmstudio_client.py) → falls back to Claude if LM Studio offline
Voice: voice_speak.AstroVoice (shared Jessica XTTS model, loaded once at startup)
Keys:  Ctrl+Shift+F1 = summon chat  |  Ctrl+Shift+F2 = mute/unmute voice

Quick start:
    & "C:\Program Files\Python312\python.exe" astrobud_overlay.py
    & "C:\Program Files\Python312\python.exe" astrobud_overlay.py --character zelda_aoi
    & "C:\Program Files\Python312\python.exe" astrobud_overlay.py --no-voice

Characters: place idle.png (transparent) + manifest.json in characters/<name>/
"""

import argparse
import json
import math
import os
import sys
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from PyQt6.QtCore import (
    QPoint, QSize, Qt, QThread, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QAction, QBrush, QColor, QFont, QKeyEvent, QPainter, QPainterPath,
    QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QPushButton,
    QWidget,
)

# ── Project root on sys.path so backend modules resolve ───────────────────────
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# ── Paths ─────────────────────────────────────────────────────────────────────
CHARS_DIR = PROJECT_DIR / "characters"

# Load config
_cfg_path = PROJECT_DIR / "config.json"
_cfg: dict = json.load(open(_cfg_path)) if _cfg_path.exists() else {}

ANTHROPIC_API_KEY: Optional[str] = _cfg.get("anthropic_api_key") or None
if ANTHROPIC_API_KEY == "YOUR_KEY_HERE":
    ANTHROPIC_API_KEY = None
LMSTUDIO_URL: str = _cfg.get("lmstudio_url", "http://localhost:1234/v1")
CHAT_MODEL: Optional[str] = _cfg.get("chat_model")   # None = LM Studio auto-selects

# ── Layout constants ──────────────────────────────────────────────────────────
BUBBLE_H  = 140
FLOAT_PAD = 14
CHAT_H    = 52
SIDE_PAD  = 14


# ── Workers ───────────────────────────────────────────────────────────────────

class VoiceWorker(QThread):
    """Runs AstroVoice.speak() off the main thread; emits wav array when done."""
    wav_ready = pyqtSignal(object)   # np.ndarray | None

    def __init__(self, voice, text: str):
        super().__init__()
        self._voice = voice
        self._text  = text

    def run(self):
        try:
            wav = self._voice.speak(self._text)
        except Exception as e:
            print(f"[voice] speak failed: {e}")
            wav = None
        self.wav_ready.emit(wav)


class AIWorker(QThread):
    response = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, text: str, system: str, history: list,
                 lmstudio_url: str, chat_model: Optional[str], api_key: Optional[str]):
        super().__init__()
        self.text         = text
        self.system       = system
        self.history      = history
        self.lmstudio_url = lmstudio_url
        self.chat_model   = chat_model
        self.api_key      = api_key

    def run(self):
        msgs = self.history + [{"role": "user", "content": self.text}]

        # Try LM Studio first
        try:
            from lmstudio_client import get_client, chat as lm_chat
            client = get_client(base_url=self.lmstudio_url)
            kwargs = dict(
                messages=[{"role": "system", "content": self.system}] + msgs,
                max_tokens=200,
            )
            if self.chat_model:
                kwargs["model"] = self.chat_model
            r = lm_chat(client, **kwargs)
            self.response.emit(r.choices[0].message.content.strip())
            return
        except Exception as e:
            print(f"[AI] LM Studio unavailable ({e}), falling back to Claude")

        # Fallback: Anthropic Claude
        try:
            import anthropic
            ac = (anthropic.Anthropic(api_key=self.api_key)
                  if self.api_key else anthropic.Anthropic())
            r = ac.messages.create(
                model="claude-opus-4-8",
                max_tokens=200,
                system=self.system,
                messages=msgs,
            )
            self.response.emit(r.content[0].text.strip())
        except Exception as e:
            self.error.emit(str(e))


class AudioWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, wav: np.ndarray):
        super().__init__()
        self.wav = wav

    def run(self):
        try:
            import sounddevice as sd
            sd.play(self.wav, 24000)
            sd.wait()
        except Exception as e:
            print(f"[audio] {e}")
        self.finished.emit()


# ── Speech bubble ─────────────────────────────────────────────────────────────

class SpeechBubble(QWidget):
    """Painted rounded bubble with typewriter text reveal. Tail points down."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._text = ""
        self._shown = ""
        self._tw = QTimer()
        self._tw.timeout.connect(self._typewriter_tick)

        lbl = QLabel(self)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lbl.setStyleSheet("color: #1a1a2e; background: transparent; font-size: 12px;")
        lbl.setFont(QFont("Segoe UI", 11))
        lbl.setGeometry(14, 10, self.width() - 28, self.height() - 28)
        self._lbl = lbl

    def resizeEvent(self, e):
        self._lbl.setGeometry(14, 10, self.width() - 28, self.height() - 30)

    def speak(self, text: str):
        self._text = text
        self._shown = ""
        self._lbl.setText("")
        self.setVisible(True)
        self._tw.start(22)

    def clear(self):
        self._tw.stop()
        self._text = ""
        self._shown = ""
        self._lbl.setText("")
        self.setVisible(False)

    def _typewriter_tick(self):
        n = min(len(self._shown) + 3, len(self._text))
        self._shown = self._text[:n]
        self._lbl.setText(self._shown)
        if n >= len(self._text):
            self._tw.stop()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        tail = 16
        path = QPainterPath()
        path.addRoundedRect(2.0, 2.0, float(w - 4), float(h - tail - 2), 14.0, 14.0)
        cx = w / 2
        by = float(h - tail - 2)
        path.moveTo(cx - 10, by)
        path.lineTo(cx, float(h - 2))
        path.lineTo(cx + 10, by)
        path.closeSubpath()
        p.setPen(QPen(QColor(180, 200, 240, 160), 1.5))
        p.setBrush(QBrush(QColor(245, 250, 255, 230)))
        p.drawPath(path)


# ── Character widget ──────────────────────────────────────────────────────────

class CharacterWidget(QLabel):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: transparent; border: none;")
        self._state = "idle"

        self._shadow = QGraphicsDropShadowEffect()
        self._shadow.setBlurRadius(35)
        self._shadow.setOffset(0, 6)
        self._shadow.setColor(QColor(80, 130, 255, 100))
        self.setGraphicsEffect(self._shadow)

    def load(self, path: Path, display_height: int) -> QSize:
        pm = QPixmap(str(path))
        if pm.isNull():
            print(f"[char] Could not load {path}")
            return QSize(200, display_height)
        scaled = pm.scaledToHeight(display_height, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)
        self.setFixedSize(scaled.size())
        return scaled.size()

    def set_state(self, state: str):
        self._state = state
        colors = {
            "idle":      QColor(80,  130, 255, 100),
            "listening": QColor(80,  200, 255, 140),
            "thinking":  QColor(255, 200,  60, 160),
            "speaking":  QColor(80,  255, 150, 180),
        }
        self._shadow.setColor(colors.get(state, colors["idle"]))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# ── Chat input bar ────────────────────────────────────────────────────────────

class ChatBar(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("Ask me anything…")
        self._edit.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,20);
                color: #e8eeff;
                border: 1px solid rgba(150,170,255,60);
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
                font-family: 'Segoe UI';
            }
            QLineEdit:focus {
                border: 1px solid rgba(150,170,255,140);
                background: rgba(255,255,255,28);
            }
        """)
        self._edit.returnPressed.connect(self._send)

        btn = QPushButton("→")
        btn.setFixedSize(34, 34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: rgba(100,150,255,200);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(120,170,255,240); }
        """)
        btn.clicked.connect(self._send)
        layout.addWidget(self._edit)
        layout.addWidget(btn)

    def open(self):
        self.setVisible(True)
        self._edit.setFocus()
        self._edit.clear()

    def dismiss(self):
        self.setVisible(False)

    def _send(self):
        text = self._edit.text().strip()
        if text:
            self._edit.clear()
            self.submitted.emit(text)


# ── Main overlay window ───────────────────────────────────────────────────────

class AstroBudOverlay(QMainWindow):

    _summon_signal = pyqtSignal()

    def __init__(self, char_name: str, voice: bool):
        super().__init__()
        self._char_name      = char_name
        self._voice_enabled  = voice
        self._state          = "idle"
        self._history: list[dict] = []
        self._drag_pos: Optional[QPoint] = None
        self._float_t        = 0.0
        self._char_base_y    = 0
        self._pending_wav: Optional[np.ndarray] = None
        self._ai_worker: Optional[AIWorker]     = None
        self._audio_worker: Optional[AudioWorker] = None
        self._voice_worker: Optional[VoiceWorker] = None
        self._astro_voice    = None   # AstroVoice instance, loaded in background
        self._voice_ready    = False
        self._hotkeys        = None
        self._tts_state      = None

        manifest_path = CHARS_DIR / char_name / "manifest.json"
        with open(manifest_path) as f:
            self._manifest = json.load(f)

        self._build_window()
        self._init_hotkeys()

        if voice:
            self._warm_voice()

        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(16)   # ~60 fps

    # ── Window construction ───────────────────────────────────────────────────

    def _build_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("AstroBud")

        canvas = QWidget(self)
        canvas.setStyleSheet("background: transparent;")
        self.setCentralWidget(canvas)

        self._char = CharacterWidget(canvas)
        char_h    = self._manifest.get("display_height", 350)
        char_size = self._char.load(CHARS_DIR / self._char_name / "idle.png", char_h)
        cw, ch    = char_size.width(), char_size.height()

        win_w = max(cw + 2 * SIDE_PAD, 260)
        win_h = BUBBLE_H + FLOAT_PAD + ch + FLOAT_PAD + CHAT_H

        canvas.setFixedSize(win_w, win_h)
        self.setFixedSize(win_w, win_h)

        char_x = (win_w - cw) // 2
        char_y = BUBBLE_H + FLOAT_PAD
        self._char.move(char_x, char_y)
        self._char_base_y = char_y

        self._bubble = SpeechBubble(canvas)
        self._bubble.setGeometry(SIDE_PAD, 0, win_w - 2 * SIDE_PAD, BUBBLE_H)

        chat_bg = QWidget(canvas)
        chat_bg.setStyleSheet("""
            QWidget {
                background: rgba(8, 10, 28, 210);
                border-radius: 12px;
            }
        """)
        chat_y = BUBBLE_H + FLOAT_PAD + ch + FLOAT_PAD
        chat_bg.setGeometry(SIDE_PAD, chat_y, win_w - 2 * SIDE_PAD, CHAT_H)

        self._chat = ChatBar(chat_bg)
        self._chat.setGeometry(0, 0, win_w - 2 * SIDE_PAD, CHAT_H)
        self._chat.submitted.connect(self._on_submitted)

        self._char.clicked.connect(self._on_char_clicked)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - win_w - 30, screen.bottom() - win_h - 30)

    # ── Voice warmup ──────────────────────────────────────────────────────────

    def _warm_voice(self):
        """Load AstroVoice in a background thread so startup is non-blocking."""
        def _load():
            try:
                from voice_speak import AstroVoice
                v = AstroVoice()
                v.warmup()
                self._astro_voice = v
                self._voice_ready = True
                print("[voice] AstroVoice ready")
            except Exception as e:
                print(f"[voice] Failed to load AstroVoice: {e}")
                self._voice_enabled = False
        threading.Thread(target=_load, daemon=True).start()

    # ── Hotkeys ───────────────────────────────────────────────────────────────

    def _init_hotkeys(self):
        self._summon_signal.connect(self._summon)
        try:
            from hotkeys import HotkeyManager, TTS_STATE
            self._tts_state = TTS_STATE

            def _on_summon():
                self._summon_signal.emit()   # cross-thread → Qt main thread

            def _on_mute():
                self._tts_state.toggle()
                print(f"[hotkeys] Voice {'muted' if self._tts_state.muted else 'unmuted'}")

            self._hotkeys = HotkeyManager(on_summon=_on_summon, on_mute_tts=_on_mute)
            ok = self._hotkeys.start()
            if ok:
                print("[hotkeys] Ctrl+Shift+F1=summon  Ctrl+Shift+F2=mute")
            else:
                print("[hotkeys] Failed to register (keyboard lib missing?)")
        except Exception as e:
            print(f"[hotkeys] Skipped: {e}")

    def _summon(self):
        if self._chat.isVisible():
            self._chat.dismiss()
            self._set_state("idle")
        else:
            self._chat.open()
            self._set_state("listening")
            self.raise_()
            self.activateWindow()

    # ── 60fps float animation ─────────────────────────────────────────────────

    def _tick(self):
        self._float_t += 0.016
        y_off = math.sin(self._float_t * 0.85) * 7
        if self._state == "speaking":
            y_off += math.sin(self._float_t * 16) * 2
        elif self._state == "thinking":
            y_off += math.sin(self._float_t * 2.5) * 4
        new_y = self._char_base_y + int(y_off)
        if self._char.y() != new_y:
            self._char.move(self._char.x(), new_y)

    # ── State machine ─────────────────────────────────────────────────────────

    def _set_state(self, state: str):
        self._state = state
        self._char.set_state(state)

    # ── Character click / chat ────────────────────────────────────────────────

    def _on_char_clicked(self):
        if self._state in ("idle", "listening"):
            self._summon()

    def _on_submitted(self, text: str):
        self._chat.dismiss()
        self._set_state("thinking")
        self._ai_worker = AIWorker(
            text, self._manifest["system_prompt"], list(self._history),
            lmstudio_url=LMSTUDIO_URL, chat_model=CHAT_MODEL, api_key=ANTHROPIC_API_KEY,
        )
        self._ai_worker.response.connect(self._on_ai_response)
        self._ai_worker.error.connect(self._on_ai_error)
        self._history.append({"role": "user", "content": text})
        self._ai_worker.start()

    def _on_ai_response(self, text: str):
        self._history.append({"role": "assistant", "content": text})
        if len(self._history) > 20:
            self._history = self._history[-20:]

        self._bubble.speak(text)
        self._set_state("speaking")

        muted = getattr(self._tts_state, "muted", False) if self._tts_state else False
        if self._voice_enabled and self._voice_ready and self._astro_voice and not muted:
            self._voice_worker = VoiceWorker(self._astro_voice, text)
            self._voice_worker.wav_ready.connect(self._on_wav_ready)
            self._voice_worker.start()
        else:
            ms = max(3000, int(len(text.split()) / 2.5 * 1000))
            QTimer.singleShot(ms, self._on_done_speaking)

    def _on_ai_error(self, err: str):
        self._bubble.speak(f"Sorry, something went wrong. ({err[:80]})")
        self._set_state("idle")
        QTimer.singleShot(4000, self._bubble.clear)

    def _on_wav_ready(self, wav):
        self._pending_wav = wav
        QTimer.singleShot(0, self._play_wav)

    def _play_wav(self):
        wav = self._pending_wav
        self._pending_wav = None
        if wav is None:
            self._on_done_speaking()
            return
        self._audio_worker = AudioWorker(wav)
        self._audio_worker.finished.connect(self._on_done_speaking)
        self._audio_worker.start()

    def _on_done_speaking(self):
        self._set_state("idle")
        QTimer.singleShot(6000, self._bubble.clear)

    # ── Drag to move ──────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    # ── Context menu ──────────────────────────────────────────────────────────

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(8, 10, 28, 230);
                color: #d0d8ff;
                border: 1px solid rgba(150,170,255,50);
                border-radius: 10px;
                padding: 6px;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
            QMenu::item { padding: 6px 18px; border-radius: 6px; }
            QMenu::item:selected { background: rgba(100,150,255,130); }
            QMenu::separator { height: 1px; background: rgba(255,255,255,20); margin: 4px 10px; }
        """)
        chars = sorted(
            d.name for d in CHARS_DIR.iterdir()
            if d.is_dir() and (d / "idle.png").exists() and (d / "manifest.json").exists()
        )
        for c in chars:
            if c != self._char_name:
                label = json.load(open(CHARS_DIR / c / "manifest.json")).get("name", c.title())
                a = QAction(f"Switch to {label}", self)
                a.triggered.connect(lambda _, name=c: self._switch_character(name))
                menu.addAction(a)
        if len(chars) > 1:
            menu.addSeparator()

        muted = getattr(self._tts_state, "muted", False) if self._tts_state else False
        if muted:
            voice_label = "Unmute voice"
        elif self._voice_enabled:
            voice_label = "Mute voice"
        else:
            voice_label = "Enable voice"

        if self._tts_state:
            menu.addAction(QAction(voice_label, self, triggered=lambda: self._tts_state.toggle()))
        else:
            menu.addAction(QAction(voice_label, self, triggered=self._toggle_voice))
        menu.addSeparator()
        menu.addAction(QAction("Quit", self, triggered=QApplication.instance().quit))
        menu.exec(e.globalPos())

    def _switch_character(self, name: str):
        self._char_name = name
        with open(CHARS_DIR / name / "manifest.json") as f:
            self._manifest = json.load(f)
        self._bubble.clear()
        self._history.clear()

        char_h   = self._manifest.get("display_height", 350)
        new_size = self._char.load(CHARS_DIR / name / "idle.png", char_h)
        cw, ch   = new_size.width(), new_size.height()

        win_w = max(cw + 2 * SIDE_PAD, 260)
        win_h = BUBBLE_H + FLOAT_PAD + ch + FLOAT_PAD + CHAT_H
        canvas = self.centralWidget()
        canvas.setFixedSize(win_w, win_h)
        self.setFixedSize(win_w, win_h)

        char_x = (win_w - cw) // 2
        char_y = BUBBLE_H + FLOAT_PAD
        self._char.move(char_x, char_y)
        self._char_base_y = char_y
        self._bubble.setGeometry(SIDE_PAD, 0, win_w - 2 * SIDE_PAD, BUBBLE_H)

        for child in canvas.children():
            if isinstance(child, QWidget) and child is not self._char and child is not self._bubble:
                child.move(SIDE_PAD, BUBBLE_H + FLOAT_PAD + ch + FLOAT_PAD)
                child.setFixedWidth(win_w - 2 * SIDE_PAD)

    def _toggle_voice(self):
        self._voice_enabled = not self._voice_enabled
        if self._voice_enabled and not self._voice_ready:
            self._warm_voice()
        print(f"[voice] {'enabled' if self._voice_enabled else 'disabled'}")

    # ── Keyboard shortcut: Escape closes chat ─────────────────────────────────

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Escape and self._chat.isVisible():
            self._chat.dismiss()
            self._set_state("idle")

    def closeEvent(self, e):
        if self._hotkeys:
            self._hotkeys.stop()
        e.accept()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="AstroBud desktop overlay companion")
    ap.add_argument("--character", default="astrobot",
                    help="Character name (folder under characters/)")
    ap.add_argument("--no-voice", action="store_true",
                    help="Skip loading XTTS model (text-only mode)")
    args = ap.parse_args()

    char_path = CHARS_DIR / args.character / "idle.png"
    if not char_path.exists():
        available = [d.name for d in CHARS_DIR.iterdir()
                     if d.is_dir() and (d / "idle.png").exists()]
        print(f"[!] Character '{args.character}' not found.")
        print(f"    Available: {available}")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    win = AstroBudOverlay(char_name=args.character, voice=not args.no_voice)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
