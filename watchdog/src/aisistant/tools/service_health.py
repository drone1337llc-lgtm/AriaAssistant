"""Service health probe tool.

Pings a service over HTTP, WebSocket, or raw TCP and returns a structured result.
"""
from __future__ import annotations

import socket
from typing import Type

import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aisistant.config import load_services


class HealthCheckInput(BaseModel):
    """Input schema for ServiceHealthTool."""
    name: str = Field(..., description="Service name (must match an entry in services.yaml).")


class HealthCheckOutput(BaseModel):
    name: str
    ok: bool
    detail: str
    latency_ms: float | None = None


class ServiceHealthTool(BaseTool):
    name: str = "service_health"
    description: str = (
        "Probe a named service for liveness. Supports http, ws, and tcp. "
        "Returns ok=True/False with a detail string and latency. "
        "Use this when the Watcher asks 'is service X up?'."
    )
    args_schema: Type[BaseModel] = HealthCheckInput

    def _run(self, name: str) -> str:
        services = {s.name: s for s in load_services()}
        if name not in services:
            return HealthCheckOutput(
                name=name, ok=False, detail=f"unknown service '{name}'"
            ).model_dump_json()

        svc = services[name]
        timeout = 5.0
        try:
            if svc.proto == "http":
                url = f"http://{svc.host}:{svc.port}{svc.health_path}"
                with httpx.Client(timeout=timeout) as client:
                    r = client.get(url)
                ok = r.status_code < 500
                return HealthCheckOutput(
                    name=name, ok=ok,
                    detail=f"HTTP {r.status_code} ({len(r.content)} bytes)",
                    latency_ms=r.elapsed.total_seconds() * 1000,
                ).model_dump_json()
            elif svc.proto == "ws":
                # Raw TCP connect — full WS handshake is overkill for a liveness check.
                with socket.create_connection((svc.host, svc.port), timeout=timeout):
                    return HealthCheckOutput(
                        name=name, ok=True,
                        detail=f"tcp connect OK ({svc.host}:{svc.port})",
                    ).model_dump_json()
            else:  # tcp
                with socket.create_connection((svc.host, svc.port), timeout=timeout):
                    return HealthCheckOutput(
                        name=name, ok=True,
                        detail=f"tcp connect OK ({svc.host}:{svc.port})",
                    ).model_dump_json()
        except (httpx.HTTPError, socket.error, OSError) as exc:
            return HealthCheckOutput(
                name=name, ok=False, detail=f"{type(exc).__name__}: {exc}"
            ).model_dump_json()
        except Exception as exc:  # last-resort guard
            return HealthCheckOutput(
                name=name, ok=False, detail=f"unexpected: {type(exc).__name__}: {exc}"
            ).model_dump_json()


class BrainDetailInput(BaseModel):
    pass


class BrainHealthTool(BaseTool):
    """Aria Brain specific health check — pulls /health from the Brain and returns
    memory backend, counts, mood. The Diagnostician uses this when 'aria_brain' is
    failing to decide whether it's a port-down, a memory backend error, or a mood
    that's stuck.
    """
    name: str = "aria_brain_health"
    description: str = (
        "Detailed health check for the Aria Brain service. Calls /health and returns "
        "memory backend (remote/local), memory counts, current mood value + label, "
        "hours since last user interaction. Use when the Watcher reports aria_brain "
        "is failing, or when 'Aria seems off' needs investigation."
    )
    args_schema: Type[BaseModel] = BrainDetailInput

    def _run(self) -> str:
        try:
            from aria_brain.config import ARIA_BRAIN_HOST, ARIA_BRAIN_PORT
            url = f"http://{ARIA_BRAIN_HOST}:{ARIA_BRAIN_PORT}/health"
        except ImportError:
            # If aria_brain isn't on the Python path, default to localhost
            url = "http://127.0.0.1:8770/health"
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(url)
            if r.status_code != 200:
                return f"aria_brain: HTTP {r.status_code}"
            data = r.json()
            return (
                f"backend={data.get('memory', {}).get('backend', '?')} "
                f"episodic={data.get('memory', {}).get('episodic_count', 0)} "
                f"facts={data.get('memory', {}).get('facts_count', 0)} "
                f"thoughts={data.get('memory', {}).get('thoughts_count', 0)} "
                f"mood={data.get('mood', {}).get('value', 0):.1f} "
                f"({data.get('mood', {}).get('label', '?')}) "
                f"since={data.get('mood', {}).get('hours_since_interaction', 0):.1f}h"
            )
        except (httpx.HTTPError, OSError) as exc:
            return f"aria_brain unreachable: {type(exc).__name__}: {exc}"