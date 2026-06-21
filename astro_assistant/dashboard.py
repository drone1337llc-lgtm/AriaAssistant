"""Aria Dashboard — lightweight HTTP server on port 8501.

Serves the React/design-system UI (index.html, panels.jsx, app.jsx, assets).
Provides two local API endpoints the browser calls:
  GET  /api/defaults  → current model config values (from brain/.env + env)
  POST /api/save      → write model selections to brain/.env

All other API calls (brain health/mood, LM Studio models) go directly from
the browser to those servers — no proxy needed (brain has CORS open).

Launched by start_aria.ps1 -WithDashboard or -All:
  python dashboard.py
"""
from __future__ import annotations

import http.server
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE     = Path(__file__).resolve().parent
BRAIN_ROOT = HERE.parent / "brain"
ENV_PATH   = BRAIN_ROOT / ".env"
SRC_PATH   = BRAIN_ROOT / "src"
PORT       = 8501

# ---------------------------------------------------------------------------
# Read current model config (from brain .env + fallback to defaults)
# ---------------------------------------------------------------------------
def _load_defaults() -> dict[str, str]:
    """Return the five model role values from brain/.env (or process env)."""
    # Try importing aria_brain.config for the canonical defaults
    if str(SRC_PATH) not in sys.path:
        sys.path.insert(0, str(SRC_PATH))
    try:
        from aria_brain.config import (
            LM_STUDIO_CHAT_MODEL,
            LM_STUDIO_PARSER_MODEL,
            LM_STUDIO_CODER_MODEL,
            LM_STUDIO_VISION_MODEL,
            LM_STUDIO_EMBED_MODEL,
        )
        return {
            "LM_STUDIO_CHAT_MODEL":   LM_STUDIO_CHAT_MODEL,
            "LM_STUDIO_PARSER_MODEL": LM_STUDIO_PARSER_MODEL,
            "LM_STUDIO_CODER_MODEL":  LM_STUDIO_CODER_MODEL,
            "LM_STUDIO_VISION_MODEL": LM_STUDIO_VISION_MODEL,
            "LM_STUDIO_EMBED_MODEL":  LM_STUDIO_EMBED_MODEL,
        }
    except Exception:
        return {}


def _write_env(selections: dict[str, str]) -> None:
    """Write/update model keys in brain/.env using python-dotenv."""
    ENV_PATH.touch()
    try:
        from dotenv import set_key
        for k, v in selections.items():
            if v and v not in ("(none)", ""):
                set_key(str(ENV_PATH), k, v)
    except ImportError:
        # Fallback: read lines, patch, rewrite
        lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
        updated = {k: False for k in selections}
        new_lines = []
        for line in lines:
            if "=" in line and not line.startswith("#"):
                key = line.split("=", 1)[0].strip()
                if key in selections and selections[key]:
                    new_lines.append(f'{key}="{selections[key]}"')
                    updated[key] = True
                    continue
            new_lines.append(line)
        for k, v in selections.items():
            if not updated[k] and v and v not in ("(none)", ""):
                new_lines.append(f'{k}="{v}"')
        ENV_PATH.write_text("\n".join(new_lines) + "\n")


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class DashboardHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def do_GET(self):
        if self.path == "/api/defaults":
            self._json(_load_defaults())
        elif self.path in ("/", ""):
            self.path = "/index.html"
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/save":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                data = json.loads(body)
                _write_env(data)
                self._json({"ok": True})
            except Exception as exc:
                self._error(500, str(exc))
        else:
            self._error(404, "Not found")

    def _json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: int, msg: str):
        body = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Quiet by default — only errors
        if args and str(args[1]) not in ("200", "304"):
            super().log_message(fmt, *args)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import socketserver
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"[Aria Dashboard] http://127.0.0.1:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("[Aria Dashboard] stopped.")
