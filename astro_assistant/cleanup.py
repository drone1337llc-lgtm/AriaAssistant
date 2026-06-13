"""
AstroBud cleanup utilities — temp file purge + Python RAM flush.

LM Studio manages its own VRAM (there's no clean API to unload a model from
the local server). Use the LM Studio GUI to unload models manually when you
want to free GPU memory. This module handles the Python-side cleanup:

    - purge_temporary_files()  : deletes screen.png, sandbox_temp.py, WAVs,
                                 and resets daily_log.json
    - free_hardware_ram()      : runs gc.collect() (Python side)
"""

from __future__ import annotations

import gc
import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.resolve()
LOG_FILE = PROJECT_ROOT / "daily_log.json"
TEMP_FILE_NAMES = [
    "screen.png",
    "screen_change.png",
    "sandbox_temp.py",
    "input.wav",
    "astro_response.wav",
]


def purge_temporary_files() -> int:
    """
    Delete temp files generated during the current session and reset the
    daily log. Returns the count of files removed.
    """
    removed = 0
    for name in TEMP_FILE_NAMES:
        p = PROJECT_ROOT / name
        if p.exists():
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass

    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        except OSError:
            pass

    return removed


def free_hardware_ram() -> bool:
    """
    Force a Python garbage collection pass. LM Studio VRAM is managed by the
    LM Studio server itself — use the GUI (or `lms unload <model>`) for that.
    """
    gc.collect()
    return True
