"""
AstroBud storage watchdog.

Watches the project folder size. If it exceeds a configurable threshold
(default 500 MB), deletes old PNG / WAV / sandbox files to bring it back
under the cap. The astro_memory/ folder is skipped so we don't corrupt
ChromaDB's lock files.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.resolve()
SKIP_DIRS = {"astro_memory", "__pycache__", ".git", "logs"}
TEMP_GLOBS = ["*.png", "*.wav", "screen_change_*.png", "sandbox_temp.py"]


def get_directory_size_mb(folder: str | Path = PROJECT_ROOT) -> float:
    """Return the size of the project folder in MB, skipping known heavy/locked dirs."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        # In-place filter to skip heavy/locked dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            fp = Path(dirpath) / f
            if not fp.exists():
                continue
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


def enforce_storage_cap(max_size_mb: float = 500.0) -> tuple[float, int, float]:
    """
    If the project folder exceeds `max_size_mb`, delete temp media files
    (.png, .wav, sandbox script) from the project root to get back under
    the cap. Returns (current_size_mb, files_purged, mb_freed).
    """
    current_size = get_directory_size_mb()
    if current_size <= max_size_mb:
        return current_size, 0, 0.0

    print(f"[StorageWatchdog] {current_size:.2f}MB > {max_size_mb}MB cap. Purging temp media...")
    files_purged = 0
    bytes_freed = 0
    for pattern in TEMP_GLOBS:
        for filepath in glob.glob(pattern, root_dir=str(PROJECT_ROOT)):
            full = PROJECT_ROOT / filepath
            try:
                size = full.stat().st_size
                full.unlink()
                files_purged += 1
                bytes_freed += size
            except OSError:
                pass
    return current_size, files_purged, bytes_freed / (1024 * 1024)
