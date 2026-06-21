"""Reflection scheduler — uses APScheduler to trigger brain.handle_reflection() periodically.

Runs in-process alongside the FastAPI app. Started by main.py.
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from aria_brain import brain
from aria_brain.config import REFLECTION_CADENCE_MINUTES, REFLECTION_ENABLED

log = logging.getLogger("aria_brain.reflection")

_scheduler: AsyncIOScheduler | None = None


async def _tick() -> None:
    try:
        result = await brain.handle_reflection()
        if result.get("thought"):
            log.info(
                f"reflection @ mood={result['mood']:.1f} "
                f"since={result['hours_since_interaction']:.1f}h :: {result['thought'][:120]}"
            )
    except Exception as exc:
        log.warning(f"reflection tick failed: {type(exc).__name__}: {exc}")


def start() -> None:
    """Start the reflection scheduler. Idempotent."""
    global _scheduler
    if _scheduler is not None:
        return
    if not REFLECTION_ENABLED:
        log.info("reflection scheduler: disabled (REFLECTION_ENABLED=false)")
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _tick,
        IntervalTrigger(minutes=REFLECTION_CADENCE_MINUTES),
        id="aria_reflection",
        max_instances=1,
        coalesce=True,
        next_run_time=None,  # don't fire on startup; wait the first interval
    )
    _scheduler.start()
    log.info(f"reflection scheduler: started (every {REFLECTION_CADENCE_MINUTES} min)")


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("reflection scheduler: stopped")


def trigger_now() -> None:
    """Fire one reflection tick immediately (used by tests and the tray menu)."""
    asyncio.get_event_loop().create_task(_tick()) if asyncio.get_event_loop().is_running() else None