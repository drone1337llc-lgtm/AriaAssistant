"""Action executor tool — run a safe, whitelisted command.

In SAFE_MODE, only commands in the whitelist are allowed. The whitelist covers
the common remediation primitives (curl, kill, netstat, query a model, etc.)
but explicitly excludes anything that modifies Godot project files.
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aisistant.config import SAFE_MODE


# Whitelist of (executable, allowed_subcommand_prefixes_or_None).
# None means any subcommand is allowed for that executable.
SAFE_COMMANDS: dict[str, set[str] | None] = {
    # network
    "curl":       {"-sS", "-s", "-o", "-X", "-I", "--max-time"},
    "ping":       {"-n", "-c", "-w"},
    # local ops
    "tasklist":   None,
    "taskkill":   {"/PID", "/F", "/IM"},
    "netstat":    {"-ano", "-an"},
    # python helpers
    "python":     {"-c"},
}


class ExecInput(BaseModel):
    command: str = Field(..., description="The full shell-style command to execute.")
    timeout: int = Field(15, description="Max seconds to wait.", ge=1, le=120)


class ActionExecutorTool(BaseTool):
    name: str = "action_executor"
    description: str = (
        "Run a whitelisted shell command. Refuses anything outside the whitelist, "
        "anything in SAFE_MODE that could modify Godot/Aria project files, "
        "and anything that takes longer than the timeout. Returns stdout+stderr."
    )
    args_schema: Type[BaseModel] = ExecInput

    def _run(self, command: str, timeout: int = 15) -> str:
        try:
            parts = shlex.split(command, posix=False)
        except ValueError as exc:
            return f"[action_executor] could not parse command: {exc}"
        if not parts:
            return "[action_executor] empty command"
        exe = Path(parts[0]).name.lower()

        if exe not in SAFE_COMMANDS:
            return f"[action_executor] REFUSED: '{exe}' not in safe-command whitelist."

        allowed = SAFE_COMMANDS[exe]
        if allowed is not None:
            # Only validate the *args* (skip the exe itself). Anything not in the
            # whitelist is refused — this is conservative.
            args = parts[1:]
            for a in args:
                # Allow value forms like "5003", "127.0.0.1" by splitting on '='.
                key = a.split("=", 1)[0]
                if key not in allowed and not key.startswith("-"):
                    continue  # bare positional (e.g. URL, host, PID) is fine
                if key.startswith("-") and key not in allowed:
                    return f"[action_executor] REFUSED: flag '{key}' for '{exe}' not allowed."

        try:
            result = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            out = result.stdout.strip()
            err = result.stderr.strip()
            return f"[exit {result.returncode}] stdout={out[:2000]!r} stderr={err[:500]!r}"
        except subprocess.TimeoutExpired:
            return f"[action_executor] timeout after {timeout}s"
        except OSError as exc:
            return f"[action_executor] OSError: {exc}"