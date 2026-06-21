"""Log-tail tool — read the last N lines of a log file (read-only)."""
from __future__ import annotations

from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class LogTailInput(BaseModel):
    path: str = Field(..., description="Absolute path to the log file.")
    lines: int = Field(20, description="How many trailing lines to return.", ge=1, le=500)
    filter_substring: str = Field("", description="If non-empty, keep only lines containing this substring.")


class LogTailTool(BaseTool):
    name: str = "log_tail"
    description: str = (
        "Tail a log file (read-only). Returns the last N lines, optionally filtered by a substring. "
        "Use this when the Diagnostician asks 'what did the log say around the failure?'."
    )
    args_schema: Type[BaseModel] = LogTailInput

    def _run(self, path: str, lines: int = 20, filter_substring: str = "") -> str:
        p = Path(path)
        if not p.exists():
            return f"[log_tail] file not found: {path}"
        try:
            # Read last ~64KB or all of it if small.
            size = p.stat().st_size
            with p.open("rb") as f:
                if size > 64_000:
                    f.seek(size - 64_000)
                raw = f.read().decode("utf-8", errors="replace")
            all_lines = raw.splitlines()
            tail = all_lines[-lines:] if lines < len(all_lines) else all_lines
            if filter_substring:
                tail = [ln for ln in tail if filter_substring in ln]
                if not tail:
                    return f"[log_tail] no lines in last {lines} match '{filter_substring}'"
            return "\n".join(tail)
        except OSError as exc:
            return f"[log_tail] OSError: {exc}"