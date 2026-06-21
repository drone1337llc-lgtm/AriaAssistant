"""Process check tool — list running processes and (with safe_mode gate) kill one by PID."""
from __future__ import annotations

import os
from typing import Type

import psutil
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aisistant.config import SAFE_MODE


class ProcessListInput(BaseModel):
    name_filter: str = Field("", description="Substring match on process name (case-insensitive). Empty = all.")


class ProcessKillInput(BaseModel):
    pid: int = Field(..., description="PID to terminate.", ge=1)
    force: bool = Field(False, description="If True, SIGKILL; else SIGTERM.")


class ProcessListTool(BaseTool):
    name: str = "process_list"
    description: str = (
        "List running processes. Optionally filter by name substring. "
        "Returns pid, name, cmdline[0], username. Use this for 'is Godot running?' or 'who owns port X?'."
    )
    args_schema: Type[BaseModel] = ProcessListInput

    def _run(self, name_filter: str = "") -> str:
        needle = name_filter.lower()
        rows = []
        for p in psutil.process_iter(["pid", "name", "cmdline", "username"]):
            try:
                info = p.info
                name = (info.get("name") or "").lower()
                if needle and needle not in name:
                    continue
                cmd = (info.get("cmdline") or [""])[0]
                rows.append(f"pid={info['pid']:>6} name={info['name']:<30} cmd={cmd}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if not rows:
            return f"[process_list] no processes match '{name_filter}'"
        return "\n".join(rows[:100])


class ProcessKillTool(BaseTool):
    name: str = "process_kill"
    description: str = (
        "Terminate a process by PID. Disabled when SAFE_MODE is on (returns refusal). "
        "Use this only when the Diagnostician has classified a failure as kill_process / free_port."
    )
    args_schema: Type[BaseModel] = ProcessKillInput

    def _run(self, pid: int, force: bool = False) -> str:
        if SAFE_MODE:
            return "[process_kill] REFUSED: AISISTANT_SAFE_MODE is on. Set it to false to allow process termination."
        try:
            p = psutil.Process(pid)
            p.terminate() if not force else p.kill()
            p.wait(timeout=5)
            return f"[process_kill] pid {pid} terminated."
        except psutil.NoSuchProcess:
            return f"[process_kill] pid {pid} did not exist."
        except psutil.AccessDenied as exc:
            return f"[process_kill] access denied for pid {pid}: {exc}"
        except psutil.TimeoutExpired:
            return f"[process_kill] pid {pid} did not exit within 5s."
        except OSError as exc:
            return f"[process_kill] OSError: {exc}"