"""Persistent runner — kicks the Flow every TICK_SECONDS forever.

Usage:
    uv run python -m aisistant.runner
or
    python -m aisistant.runner

Stops on Ctrl-C. State is persisted to .crewai/flow_state.db (Flow's @persist),
so a restart picks up where we left off.
"""
from __future__ import annotations

import asyncio
import signal
import sys
import time
import traceback
from datetime import datetime

from aisistant.config import TICK_SECONDS
from aisistant.flow import _health_log, AriaFlow


_running = True


def _install_signal_handlers() -> None:
    def _stop(_signum, _frame):
        global _running
        _running = False
        _health_log("aisistant runner stopping (signal)")
    signal.signal(signal.SIGINT, _stop)
    try:
        signal.signal(signal.SIGTERM, _stop)
    except (AttributeError, ValueError):
        pass  # not all platforms have SIGTERM


async def _tick(flow: AriaFlow) -> None:
    started = time.monotonic()
    try:
        await flow.kickoff_async(inputs={})
    except Exception:
        _health_log(f"tick error: {traceback.format_exc(limit=4).strip()}")
    elapsed = time.monotonic() - started
    _health_log(f"tick wall-clock: {elapsed:.2f}s")


async def _main() -> None:
    _install_signal_handlers()
    flow = AriaFlow()
    _health_log(f"aisistant runner online (tick_seconds={TICK_SECONDS})")
    while _running:
        loop_start = time.monotonic()
        await _tick(flow)
        # Sleep the remainder of the tick window, but break early on signal.
        remaining = TICK_SECONDS - (time.monotonic() - loop_start)
        while _running and remaining > 0:
            await asyncio.sleep(min(remaining, 1.0))
            remaining = TICK_SECONDS - (time.monotonic() - loop_start)
    _health_log("aisistant runner stopped")


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        _health_log("aisistant runner stopped (KeyboardInterrupt)")


if __name__ == "__main__":
    main()