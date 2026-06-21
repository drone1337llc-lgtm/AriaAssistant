"""Port-in-use tool — check if a local TCP port is bound, and by whom."""
from __future__ import annotations

from typing import Type

import psutil
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class PortCheckInput(BaseModel):
    port: int = Field(..., description="Local TCP port to inspect.", ge=1, le=65535)


class PortCheckTool(BaseTool):
    name: str = "port_check"
    description: str = (
        "Check whether a local TCP port is currently bound, and by which PID. "
        "Use this when a service refuses to start because 'port already in use'."
    )
    args_schema: Type[BaseModel] = PortCheckInput

    def _run(self, port: int) -> str:
        try:
            conns = psutil.net_connections(kind="tcp")
            for c in conns:
                if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN:
                    pid = c.pid or -1
                    name = ""
                    try:
                        if pid > 0:
                            name = psutil.Process(pid).name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    return f"port {port}: LISTEN pid={pid} name={name}"
            return f"port {port}: free"
        except psutil.AccessDenied:
            return f"port {port}: access denied (run as admin for full visibility)"