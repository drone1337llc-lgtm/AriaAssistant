"""Entry point — run the FastAPI app via uvicorn.

Handles SIGINT (Ctrl-C) and SIGTERM cleanly so the Brain shuts down in one
keystroke. The /shutdown endpoint sets `server.should_exit = True` which makes
uvicorn wind down its workers and exit.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

import uvicorn

from aria_brain.config import ARIA_BRAIN_HOST, ARIA_BRAIN_PORT


def _configure_logging() -> None:
    fmt = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt="%H:%M:%S")
    for noisy in ("httpx", "apscheduler.executors.default", "apscheduler.scheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def run() -> None:
    _configure_logging()
    config = uvicorn.Config(
        "aria_brain.server:app",
        host=ARIA_BRAIN_HOST,
        port=ARIA_BRAIN_PORT,
        log_level="info",
        reload=False,
    )
    server = uvicorn.Server(config)

    # Wire Ctrl-C / SIGTERM into uvicorn's clean shutdown path.
    # On Windows, SIGBREAK is what Ctrl-Break sends; SIGTERM is unreliable.
    def _shutdown(signum, frame):
        logging.getLogger("aria_brain.main").info(f"signal {signum} — shutting down")
        server.should_exit = True

    if sys.platform == "win32":
        signal.signal(signal.SIGINT, _shutdown)   # Ctrl-C in the console
        signal.signal(signal.SIGBREAK, _shutdown)  # Ctrl-Break
    else:
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

    # Make the /shutdown endpoint able to set should_exit on this server.
    import aria_brain.server as _srv_mod
    _srv_mod._uvicorn_server = server

    server.run()


if __name__ == "__main__":
    run()