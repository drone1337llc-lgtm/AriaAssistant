"""Network check tool — TCP-connect to a host:port to verify reachability."""
from __future__ import annotations

import socket
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class NetCheckInput(BaseModel):
    host: str = Field(..., description="Hostname or IP to test.")
    port: int = Field(..., description="TCP port.", ge=1, le=65535)
    timeout: float = Field(3.0, description="Seconds to wait.", ge=0.1, le=30.0)


class NetCheckTool(BaseTool):
    name: str = "net_check"
    description: str = (
        "Try a TCP connection to host:port. Returns 'reachable' or an error string. "
        "Use this when 'is PC 2 reachable from PC 1?' is the question."
    )
    args_schema: Type[BaseModel] = NetCheckInput

    def _run(self, host: str, port: int, timeout: float = 3.0) -> str:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return f"reachable: {host}:{port}"
        except (socket.timeout, socket.error) as exc:
            return f"unreachable: {host}:{port} — {type(exc).__name__}: {exc}"