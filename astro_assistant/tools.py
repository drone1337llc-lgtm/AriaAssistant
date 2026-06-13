"""
Tool definitions for AstroBud's daytime engine.

This replaces the spec's JSON-blob tool-dispatch hack with the standard
OpenAI `tools` parameter format (function-calling). It's much more reliable:
- The model returns structured tool_calls, not free-form JSON
- Parameter schemas are validated client-side
- Multi-tool calls in one turn are supported natively

Each tool has:
- A Python function that does the work
- A `get_*_schema()` function returning the OpenAI tool schema

To add a new tool:
    1. Write the Python function
    2. Add a `get_<name>_schema()` returning the OpenAI tool schema
    3. Register it in `TOOL_REGISTRY` (name -> callable)
    4. Add the schema to `get_all_tool_schemas()`
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).parent.resolve()

# We import system tools lazily inside the function bodies to keep this module
# importable on machines that don't have pywin32/pycaw/pyautogui installed
# (e.g., when running just the dashboard).
SANDBOX_TIMEOUT_SEC = 5
SELF_CORRECTION_MAX_ATTEMPTS = 3
PIPER_EXE = "piper"
PIPER_MODEL = "en_US-lessac-medium.onnx"
OUTPUT_WAV = "astro_response.wav"


# =====================================================================
# TOOL FUNCTIONS
# =====================================================================

def open_application(app_name: str) -> str:
    """Launch a local Windows application."""
    app_mapping = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "browser": "start chrome",
        "chrome": "start chrome",
        "firefox": "start firefox",
        "cmd": "start cmd",
        "powershell": "start powershell",
        "explorer": "explorer.exe",
    }
    target = app_mapping.get(app_name.lower(), app_name)
    try:
        subprocess.Popen(target, shell=True)
        return f"*Bloop* Successfully launched {app_name}!"
    except Exception as e:
        return f"Failed to open {app_name}. Error: {e}"


def control_media_volume(action: str) -> str:
    """Adjust Windows master volume: mute | unmute | up | down."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))

        action = action.lower()
        if action == "mute":
            volume.SetMute(1, None)
        elif action == "unmute":
            volume.SetMute(0, None)
        elif action == "up":
            current = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(min(current + 0.15, 1.0), None)
        elif action == "down":
            current = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(max(current - 0.15, 0.0), None)
        else:
            return f"Unknown volume action: {action}. Use mute|unmute|up|down."

        return f"*Whir* Volume updated: {action}."
    except Exception as e:
        return f"Could not adjust master audio. Error: {e}"


def check_system_resources() -> str:
    """Read CPU and RAM utilization."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        return f"Current internal matrix status: CPU at {cpu}%, RAM at {ram}%."
    except Exception as e:
        return f"Could not read system resources. Error: {e}"


def execute_and_verify_code(code_snippet: str) -> dict[str, Any]:
    """
    Write `code_snippet` to a temp file and run it with a hard timeout.
    Returns {"status": "success"|"failed", "output"|"error": str}.
    """
    import tempfile
    fd, sandbox_path = tempfile.mkstemp(suffix=".py", prefix="astro_sandbox_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code_snippet)
        print(f"[Sandbox]: Running {len(code_snippet)} chars ...")
        result = subprocess.run(
            [sys.executable, sandbox_path],
            capture_output=True,
            text=True,
            timeout=SANDBOX_TIMEOUT_SEC,
        )
        if result.returncode == 0:
            return {"status": "success", "output": result.stdout.strip()}
        return {"status": "failed", "error": result.stderr.strip() or "Non-zero exit code"}
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "error": f"Execution Timeout! Code took longer than {SANDBOX_TIMEOUT_SEC}s.",
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            os.remove(sandbox_path)
        except OSError:
            pass


def type_code_to_ide(code_to_type: str) -> str:
    """
    Warn the user out loud, wait 3 seconds, then simulate keystrokes
    into the active window using pyautogui.
    """
    try:
        import pyautogui
    except ImportError:
        return "pyautogui is not installed. Run: pip install pyautogui"

    pyautogui.FAILSAFE = True  # mouse-to-corner aborts

    warning = (
        "*Bloop* I am preparing to write the code fix directly into your editor! "
        "Please click your text editor window now. Typing starts in 3 seconds!"
    )
    print(f"\n[AstroBud]: {warning}")
    _speak_local_piper(warning)

    time.sleep(3.0)

    print("[Macro Active]: Simulating keystrokes...")
    pyautogui.write(code_to_type, interval=0.005)
    print("[Macro Finished]: Code injected successfully.")

    confirm = "*Happy electronic chirp* Auto-typing sequence complete! Review your workspace matrix."
    _speak_local_piper(confirm)
    return confirm


def _send_media_key(vk_code: int) -> str:
    """Send a multimedia key (play/pause, next, prev) via ctypes on Windows."""
    if sys.platform != "win32":
        return "Media keys are Windows-only."
    try:
        import ctypes
        # keybd_event is the simplest reliable way to fire media keys
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)            # key down
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)            # key up (KEYEVENTF_KEYUP = 2)
        return "ok"
    except Exception as e:
        return f"Media key failed: {e}"


def play_pause_media() -> str:
    """Toggle media play/pause (works in most players, browsers, Spotify, etc.)."""
    # VK_MEDIA_PLAY_PAUSE = 0xB3
    result = _send_media_key(0xB3)
    return "*Click* Media play/pause toggled." if result == "ok" else result


def next_track() -> str:
    """Skip to the next track in the active media player."""
    result = _send_media_key(0xB0)  # VK_MEDIA_NEXT_TRACK
    return "*Click* Skipped to next track." if result == "ok" else result


def previous_track() -> str:
    """Go back to the previous track in the active media player."""
    result = _send_media_key(0xB1)  # VK_MEDIA_PREV_TRACK
    return "*Click* Went back to previous track." if result == "ok" else result


def set_volume(level: int) -> str:
    """Set Windows master volume to a specific level (0-100)."""
    if not (0 <= level <= 100):
        return f"Volume level must be 0-100, got {level}."
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"*Whir* Volume set to {level}%."
    except Exception as e:
        return f"Could not set volume: {e}"


def take_screenshot_to_clipboard() -> str:
    """Capture the primary monitor and copy the image to the Windows clipboard."""
    if sys.platform != "win32":
        return "Clipboard screenshot is Windows-only."
    try:
        import mss
        from PIL import Image
        import win32clipboard

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = np.array(sct.grab(monitor))
        # Convert BGRA -> RGB
        rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        pil_img = Image.fromarray(rgb)

        # Push to clipboard as BMP (universally accepted)
        output = io.BytesIO()
        pil_img.save(output, "BMP")
        data = output.getvalue()[14:]  # BMP header is 14 bytes; CF_DIB wants post-header
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        win32clipboard.CloseClipboard()
        return "*Snapshot* Screenshot copied to clipboard. Paste away!"
    except ImportError as e:
        return f"Missing dependency: {e}. Run: pip install pillow pywin32"
    except Exception as e:
        return f"Screenshot failed: {e}"


def get_active_window_title() -> str:
    """Return the title of the currently focused window. Useful for context."""
    if sys.platform != "win32":
        return "Active window title is Windows-only."
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd) or "(untitled window)"
    except Exception as e:
        return f"Could not read active window: {e}"


# ---- Beta feedback logger (open-world RPG playtesting) ----

BETA_FEEDBACK_DIR = PROJECT_ROOT / "beta_feedback"
BUGS_LOG_PATH = BETA_FEEDBACK_DIR / "bugs.jsonl"
BUG_SCREENS_DIR = BETA_FEEDBACK_DIR / "screens"


def log_bug_observation(
    ocr_text: str,
    vision_context: str,
    user_note: str = "",
    frame_path: str = "",
    category: str = "",
    description: str = "",
) -> str:
    """
    Persist a single bug / observation entry for the beta program.

    Each call appends a JSON line to `beta_feedback/bugs.jsonl` and (if a
    `frame_path` is provided) copies the referenced frame into
    `beta_feedback/screens/{bug_id}.png`. Returns a short human-readable
    confirmation with the bug ID (timestamp-based) so the user knows it
    was saved.
    """
    import shutil

    BETA_FEEDBACK_DIR.mkdir(exist_ok=True)
    BUG_SCREENS_DIR.mkdir(exist_ok=True)
    bug_id = f"bug_{int(time.time())}_{os.getpid() % 10000:04d}"

    saved_frame = ""
    if frame_path and os.path.exists(frame_path):
        dest = BUG_SCREENS_DIR / f"{bug_id}.png"
        try:
            shutil.copy2(frame_path, dest)
            saved_frame = str(dest.relative_to(PROJECT_ROOT))
        except OSError:
            pass

    entry = {
        "id": bug_id,
        "timestamp": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ocr_text": ocr_text[:2000],
        "vision_context": vision_context[:1000],
        "user_note": user_note[:1000],
        "category": category[:60],
        "description": description[:300],
        "frame": saved_frame,
        "active_window": "",
    }
    try:
        if sys.platform == "win32":
            try:
                import win32gui
                entry["active_window"] = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            except Exception:
                pass
    except Exception:
        pass

    try:
        with open(BUGS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        return f"Could not write bug log: {e}"

    summary_bits = [f"Bug {bug_id} logged"]
    if category:
        summary_bits.append(f"category: {category}")
    if description:
        summary_bits.append(f"desc: {description[:60]}")
    if user_note.strip():
        summary_bits.append(f"note: {user_note[:60]}")
    if saved_frame:
        summary_bits.append(f"frame saved")
    return " | ".join(summary_bits)


def list_bug_observations(limit: int = 50) -> list[dict]:
    """Return the most recent `limit` bug entries (parsed from the JSONL log)."""
    if not BUGS_LOG_PATH.exists():
        return []
    out: list[dict] = []
    try:
        with open(BUGS_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines[-limit:]):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


# ---- Export ----

EXPORT_DIR = BETA_FEEDBACK_DIR / "exports"


def _format_bug_markdown(entry: dict) -> str:
    parts = [
        f"## {entry.get('id', '?')} — {entry.get('iso', '?')}",
        "",
    ]
    if entry.get("category"):
        parts.append(f"- **Category:** {entry['category']}")
    if entry.get("description"):
        parts.append(f"- **Description:** {entry['description']}")
    if entry.get("user_note"):
        parts.append(f"- **Note:** {entry['user_note']}")
    if entry.get("active_window"):
        parts.append(f"- **Active window:** `{entry['active_window']}`")
    if entry.get("frame"):
        parts.append(f"- **Frame:** `{entry['frame']}`")
    if entry.get("ocr_text"):
        parts.append("")
        parts.append("**OCR text:**")
        parts.append("")
        parts.append("```")
        parts.append(entry["ocr_text"][:2000])
        parts.append("```")
    if entry.get("vision_context"):
        parts.append("")
        parts.append(f"**Vision context:** {entry['vision_context'][:500]}")
    parts.append("")
    parts.append("---")
    parts.append("")
    return "\n".join(parts)


def _format_bug_json(entry: dict) -> str:
    return json.dumps(entry, indent=2, ensure_ascii=False)


def _format_bug_csv(entries: list[dict]) -> str:
    import csv
    import io
    keys = ["id", "iso", "timestamp", "category", "description", "user_note",
            "active_window", "frame", "ocr_text", "vision_context"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for e in entries:
        w.writerow({k: e.get(k, "") for k in keys})
    return buf.getvalue()


def export_bugs(
    last_n: int = 10,
    fmt: str = "markdown",
    copy_to_clipboard: bool = False,
) -> str:
    """
    Export the most recent `last_n` bug entries to a file under
    `beta_feedback/exports/`. Returns a short confirmation with the file
    path. `fmt` is one of: "markdown", "json", "csv". If `copy_to_clipboard`
    is True, the rendered content is also pushed to the OS clipboard
    (Windows only) so the user can paste directly into a bug tracker.
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    entries = list_bug_observations(limit=last_n)
    if not entries:
        return f"No bug entries to export. Press Ctrl+Shift+F4 to flag one first."

    fmt = fmt.lower().strip()
    if fmt not in ("markdown", "json", "csv"):
        return f"Unknown export format '{fmt}'. Use markdown, json, or csv."

    stamp = time.strftime("%Y%m%d_%H%M%S")
    if fmt == "markdown":
        body = f"# Bug Report Export — {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        body += f"Exported {len(entries)} bug entries (most recent first).\n\n"
        body += "\n".join(_format_bug_markdown(e) for e in entries)
        ext = "md"
    elif fmt == "json":
        body = "[\n" + ",\n".join(_format_bug_json(e) for e in entries) + "\n]\n"
        ext = "json"
    else:  # csv
        body = _format_bug_csv(entries)
        ext = "csv"

    filename = f"bugs_{stamp}_{len(entries)}.{ext}"
    out_path = EXPORT_DIR / filename
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(body)
    except OSError as e:
        return f"Could not write export: {e}"

    if copy_to_clipboard and sys.platform == "win32":
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            # CF_UNICODETEXT for text content
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, body)
            win32clipboard.CloseClipboard()
        except Exception as e:
            return f"Exported to {out_path} (clipboard copy failed: {e})"

    relative = out_path.relative_to(PROJECT_ROOT)
    return f"Exported {len(entries)} bug(s) -> {relative}" + (" (clipboard)" if copy_to_clipboard else "")


# =====================================================================
# TTS helper (used by type_code_to_ide and main_astro)
# =====================================================================

def _speak_local_piper(text_to_speak: str) -> None:
    """
    Pipe text through the local Piper binary and play the resulting WAV.
    Strips asterisks so we don't vocalize '*bloop*' literally.
    """
    clean_text = text_to_speak.replace("*", "")
    try:
        command = (
            f'echo "{clean_text}" | {PIPER_EXE} --model {PIPER_MODEL} '
            f'--output_file {OUTPUT_WAV}'
        )
        subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import soundfile as sf
        import sounddevice as sd
        data, fs = sf.read(OUTPUT_WAV)
        sd.play(data, fs)
        sd.wait()
    except Exception as e:
        print(f"[TTS] Piper playback failed: {e}")


# =====================================================================
# TOOL REGISTRY + OPENAI SCHEMAS
# =====================================================================

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "open_application": open_application,
    "control_media_volume": control_media_volume,
    "check_system_resources": check_system_resources,
    "execute_and_verify_code": execute_and_verify_code,
    "type_code_to_ide": type_code_to_ide,
    "play_pause_media": play_pause_media,
    "next_track": next_track,
    "previous_track": previous_track,
    "set_volume": set_volume,
    "take_screenshot_to_clipboard": take_screenshot_to_clipboard,
    "get_active_window_title": get_active_window_title,
    "log_bug_observation": log_bug_observation,
    "export_bugs": export_bugs,
}


def get_all_tool_schemas() -> list[dict[str, Any]]:
    """Return all tool schemas in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": "open_application",
                "description": "Launch a local Windows application by common name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "enum": [
                                "notepad", "calculator", "browser",
                                "chrome", "firefox", "cmd", "powershell", "explorer",
                            ],
                            "description": "Name of the application to launch.",
                        }
                    },
                    "required": ["app_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "control_media_volume",
                "description": "Adjust the system master volume.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["mute", "unmute", "up", "down"],
                            "description": "What to do to the volume.",
                        }
                    },
                    "required": ["action"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_system_resources",
                "description": "Read current CPU and RAM utilization.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_and_verify_code",
                "description": (
                    "Write a Python code snippet to a sandbox file, run it with a "
                    "5-second timeout, and return stdout or stderr. Used for testing "
                    "potential code fixes before showing them to the user."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code_snippet": {
                            "type": "string",
                            "description": "Complete Python code to execute in isolation.",
                        }
                    },
                    "required": ["code_snippet"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "type_code_to_ide",
                "description": (
                    "Simulate keyboard input to type a verified code snippet into "
                    "the user's currently-active text editor. Triggers a 3-second "
                    "vocal warning first so the user can click into their IDE."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code_to_type": {
                            "type": "string",
                            "description": "The code to type into the active editor.",
                        }
                    },
                    "required": ["code_to_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "play_pause_media",
                "description": "Toggle media play/pause in the active player.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "next_track",
                "description": "Skip to the next track in the active media player.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "previous_track",
                "description": "Go back to the previous track in the active media player.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_volume",
                "description": "Set the Windows master volume to a specific level (0-100).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Target volume percentage (0=mute, 100=max).",
                        }
                    },
                    "required": ["level"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "take_screenshot_to_clipboard",
                "description": "Capture the primary monitor and copy the image to the Windows clipboard.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_active_window_title",
                "description": "Return the title of the currently focused window. Useful for context.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "log_bug_observation",
                "description": (
                    "Save a beta-test bug / observation entry to disk. Use this when the "
                    "user reports something worth logging, or when you (the AI) notice a "
                    "visual anomaly that should be tracked. Captures OCR text + vision "
                    "context + user note into beta_feedback/bugs.jsonl, and saves a frame "
                    "screenshot to beta_feedback/screens/."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ocr_text": {
                            "type": "string",
                            "description": "Text visible on screen at the moment of the observation.",
                        },
                        "vision_context": {
                            "type": "string",
                            "description": "Visual / UI context describing what's on screen.",
                        },
                        "user_note": {
                            "type": "string",
                            "description": "Optional short note from the user about what they noticed.",
                        },
                        "frame_path": {
                            "type": "string",
                            "description": "Path to a screenshot of the current screen (PNG/JPG).",
                        },
                        "category": {
                            "type": "string",
                            "description": "Bug category from auto-triage (e.g. 'Visual Glitch', 'Quest Bug').",
                        },
                        "description": {
                            "type": "string",
                            "description": "One-line description of the issue from auto-triage.",
                        },
                    },
                    "required": ["ocr_text", "vision_context"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "export_bugs",
                "description": (
                    "Export the most recent bug / observation entries to a file under "
                    "beta_feedback/exports/. Returns the file path. Use this when the user "
                    "asks to package their bug log for submission to the dev team / "
                    "bug tracker."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "last_n": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "default": 10,
                            "description": "How many recent entries to export (default 10).",
                        },
                        "fmt": {
                            "type": "string",
                            "enum": ["markdown", "json", "csv"],
                            "default": "markdown",
                            "description": "Output format.",
                        },
                        "copy_to_clipboard": {
                            "type": "boolean",
                            "default": False,
                            "description": "Also push the rendered text to the OS clipboard (Windows only).",
                        },
                    },
                    "required": [],
                },
            },
        },
    ]


def execute_tool_call(tool_name: str, arguments_json: str) -> str:
    """
    Dispatch a tool call (from an OpenAI tool_call object) to the right function.
    Returns a JSON string suitable for putting in a tool-result message.
    """
    func = TOOL_REGISTRY.get(tool_name)
    if func is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        args = {}

    try:
        result = func(**args)
        # Tools return either str or dict; normalize
        if isinstance(result, (dict, list)):
            return json.dumps(result)
        return str(result)
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {e}"})


def self_correction_loop(
    client,
    chat_model: str,
    initial_faulty_code: str,
    max_attempts: int = SELF_CORRECTION_MAX_ATTEMPTS,
    on_progress: Callable[[int, str], None] | None = None,
) -> tuple[str, bool, str]:
    """
    Ask the code brain to fix `initial_faulty_code`, run each attempt in the
    sandbox, and feed stderr back to the model on failure. Returns
    (final_code, success, execution_output_or_error).
    """
    from lmstudio_client import chat, text_message

    current_prompt = (
        f"Fix the following Python code so it runs perfectly without errors. "
        f"Reply ONLY with a code block in ```python fences:\n```python\n{initial_faulty_code}\n```"
    )

    final_code = initial_faulty_code
    for attempt in range(1, max_attempts + 1):
        if on_progress:
            on_progress(attempt, f"Generating fix attempt {attempt}/{max_attempts}...")

        response = chat(
            client,
            model=chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an elite automated Python compiler debugger. "
                        "Reply ONLY with a clean ```python``` code block. "
                        "No greetings, no explanations."
                    ),
                },
                text_message("user", current_prompt),
            ],
            temperature=0.2,
        )
        ai_reply = response.choices[0].message.content or ""

        # Robust code-block extraction
        if "```python" in ai_reply:
            raw_code = ai_reply.split("```python", 1)[1].split("```", 1)[0].strip()
        elif "```" in ai_reply:
            raw_code = ai_reply.split("```", 1)[1].split("```", 1)[0].strip()
        else:
            raw_code = ai_reply.strip()

        sandbox_report = execute_and_verify_code(raw_code)
        if sandbox_report["status"] == "success":
            if on_progress:
                on_progress(attempt, f"Success on attempt {attempt}!")
            return raw_code, True, sandbox_report.get("output", "")

        if on_progress:
            on_progress(
                attempt,
                f"Failed: {sandbox_report.get('error', 'unknown')[:200]}",
            )
        current_prompt = (
            f"Your previous fix failed with this execution error:\n"
            f"```\n{sandbox_report.get('error', 'unknown error')}\n```\n\n"
            f"Failing code:\n```python\n{raw_code}\n```\n\n"
            f"Generate a corrected version in a ```python``` code block."
        )
        final_code = raw_code

    return final_code, False, "Max correction iterations exhausted."
