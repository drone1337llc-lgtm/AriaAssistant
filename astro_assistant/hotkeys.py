"""
Global hotkey handler for AstroBud.

Hooks Windows system-wide hotkeys so the user can summon AstroBud without
having the terminal in focus. Requires admin privileges on Windows (or run
from an elevated shell).

Hotkeys (defaults, configurable in config.json):
    Ctrl+Shift+F1 = "Summon"   -> triggers an immediate voice prompt + AI turn
    Ctrl+Shift+F2 = "Mute TTS" -> toggles whether AstroBud speaks out loud
    Ctrl+Shift+F3 = "Describe" -> one-shot: prints a description of the current screen
    Ctrl+Shift+F4 = "Flag bug" -> captures a high-quality frame, runs OCR +
                                  auto-triage, persists a bug entry
    Ctrl+Shift+F5 = "Export"   -> exports the last N bug entries as Markdown
                                  to beta_feedback/exports/ and copies to clipboard

We use Ctrl+Shift+ modifiers specifically to avoid conflicts with:
    - F1-F12 alone (almost every game uses these for menus/abilities)
    - WASD + modifier combos (common ability bindings)
    - Alt+F4 (OS close window)
    - OS shortcuts (Win+key, Ctrl+C/V/X, etc.)

The `keyboard` library with `suppress=False` lets the combo pass through to
the active application in addition to triggering our callback — so the game
still sees the keystrokes, but AstroBud also fires.

Usage:
    from hotkeys import HotkeyManager
    hm = HotkeyManager(
        on_summon=lambda: trigger_turn(),
        on_mute_tts=lambda: toggle_mute(),
        on_describe=lambda: describe_screen(),
        on_flag_bug=lambda: flag_bug(),
        on_export_bugs=lambda: export_bugs(),
    )
    hm.start()        # non-blocking; runs in a background thread
    ...
    hm.stop()         # clean up

If `keyboard` isn't installed, the import is soft-fail and `start()` is a no-op.
The rest of AstroBud still works — global hotkeys are an enhancement, not a
hard dependency.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional


class HotkeyManager:
    def __init__(
        self,
        on_summon: Optional[Callable[[], None]] = None,
        on_mute_tts: Optional[Callable[[], None]] = None,
        on_describe: Optional[Callable[[], None]] = None,
        on_flag_bug: Optional[Callable[[], None]] = None,
        on_export_bugs: Optional[Callable[[], None]] = None,
        summon_key: str = "ctrl+shift+f1",
        mute_key: str = "ctrl+shift+f2",
        describe_key: str = "ctrl+shift+f3",
        flag_bug_key: str = "ctrl+shift+f4",
        export_key: str = "ctrl+shift+f5",
    ):
        self.on_summon = on_summon
        self.on_mute_tts = on_mute_tts
        self.on_describe = on_describe
        self.on_flag_bug = on_flag_bug
        self.on_export_bugs = on_export_bugs
        self.summon_key = summon_key
        self.mute_key = mute_key
        self.describe_key = describe_key
        self.flag_bug_key = flag_bug_key
        self.export_key = export_key
        self._available = False
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> bool:
        """Start listening for global hotkeys. Returns True on success."""
        with self._lock:
            if self._started:
                return True
            try:
                import keyboard  # type: ignore
            except ImportError:
                print("[Hotkeys] `keyboard` not installed. Run: pip install keyboard")
                print("[Hotkeys] Global hotkeys disabled; use Enter in the terminal to talk.")
                return False

            self._available = True
            try:
                if self.on_summon:
                    keyboard.add_hotkey(self.summon_key, self._safe(self.on_summon), suppress=False)
                if self.on_mute_tts:
                    keyboard.add_hotkey(self.mute_key, self._safe(self.on_mute_tts), suppress=False)
                if self.on_describe:
                    keyboard.add_hotkey(self.describe_key, self._safe(self.on_describe), suppress=False)
                if self.on_flag_bug:
                    keyboard.add_hotkey(self.flag_bug_key, self._safe(self.on_flag_bug), suppress=False)
                if self.on_export_bugs:
                    keyboard.add_hotkey(self.export_key, self._safe(self.on_export_bugs), suppress=False)
                self._started = True
                print(
                    f"[Hotkeys] {self.summon_key}=Summon  {self.mute_key}=Mute  "
                    f"{self.describe_key}=Describe  {self.flag_bug_key}=Flag bug  "
                    f"{self.export_key}=Export"
                )
                return True
            except Exception as e:
                # Common cause: not running as admin
                print(f"[Hotkeys] Failed to register: {e}")
                print("[Hotkeys] Try running the script as Administrator, or skip global hotkeys.")
                return False

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            try:
                import keyboard
                for key in (self.summon_key, self.mute_key, self.describe_key,
                            self.flag_bug_key, self.export_key):
                    try:
                        keyboard.remove_hotkey(key)
                    except KeyError:
                        pass
            except Exception:
                pass
            self._started = False

    def _safe(self, fn: Callable[[], None]) -> Callable[[], None]:
        """Wrap a callback so an exception in one hotkey doesn't kill the listener."""
        def wrapper():
            try:
                fn()
            except Exception as e:
                print(f"[Hotkeys] Callback error: {e}")
        return wrapper


# Module-level mute state (shared with main_astro via tts_enabled toggle)
class TTSMute:
    def __init__(self) -> None:
        self._muted = False

    def toggle(self) -> bool:
        self._muted = not self._muted
        return self._muted

    @property
    def muted(self) -> bool:
        return self._muted


# Global singleton so tools._speak_local_piper can check it
TTS_STATE = TTSMute()


if __name__ == "__main__":
    # Demo: register handlers that just print
    def summon():
        print("[Demo] Summon pressed")

    def mute():
        m = TTS_STATE.toggle()
        print(f"[Demo] TTS muted = {m}")

    def describe():
        print("[Demo] Describe pressed")

    def flag():
        print("[Demo] Flag bug pressed")

    def export():
        print("[Demo] Export pressed")

    hm = HotkeyManager(
        on_summon=summon, on_mute_tts=mute, on_describe=describe,
        on_flag_bug=flag, on_export_bugs=export,
    )
    if hm.start():
        print("Press Ctrl+Shift+F1..F5. Ctrl+C to exit.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            hm.stop()

