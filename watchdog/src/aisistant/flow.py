"""Persistent Flow for the Aria autonomous backend crew.

Each tick of the outer runner calls `AriaFlow().kickoff(inputs={...})`.
The Flow:
  1. start()         — build the per-tick input payload (services, tick_number, etc.)
  2. run_crew()      — actually kickoff the crew with those inputs
  3. record_result() — append the result to the live state and to aria_health.log

State is persisted via @persist (SQLite under .crewai/flow_state.db by default),
so an interrupted run picks up where it left off.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from crewai.flow.flow import Flow, listen, start
from crewai.flow.persistence import persist

from aisistant.config import ARIA_HEALTH_LOG, KNOWN_FIXES_PATH, SAFE_MODE, load_services
from aisistant.crew import AisistantCrew
from aisistant.schemas import (
    ActionsReport,
    AriaMaintenanceState,
    DiagnosesReport,
    LearningSummary,
    VerificationsReport,
    WatchReport,
)


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _health_log(line: str) -> None:
    """Append a single line to aria_health.log (best-effort, never raises)."""
    try:
        Path(ARIA_HEALTH_LOG).parent.mkdir(parents=True, exist_ok=True)
        with open(ARIA_HEALTH_LOG, "a", encoding="utf-8") as f:
            f.write(f"{_now_iso()}\taisistant\t{line}\n")
    except OSError:
        pass


@persist(verbose=False)
class AriaFlow(Flow[AriaMaintenanceState]):
    """One tick = one Flow run."""

    @start()
    def gather_inputs(self) -> dict:
        self.state.tick_number += 1
        services = load_services()
        last = self.state.last_watch
        last_summary = (
            f"previous tick had {len(last.failing) if last else 0} failing services"
        )
        payload = {
            "tick_number": self.state.tick_number,
            "services": [s.model_dump() for s in services],
            "log_path": str(ARIA_HEALTH_LOG),
            "kb_path": str(KNOWN_FIXES_PATH),
            "safe_mode": SAFE_MODE,
            "last_summary": last_summary,
            # task-specific payloads, filled in below
            "watch_report_json": "{}",
            "diagnoses_json": "[]",
            "actions_json": "[]",
            "verifications_json": "[]",
        }
        _health_log(f"tick {self.state.tick_number} start (safe_mode={SAFE_MODE}, services={len(services)})")
        return payload

    @listen(gather_inputs)
    async def run_crew(self, payload: dict) -> dict:
        # Run the crew with the per-tick inputs. We pass all 5 tasks' interpolation
        # variables up front so tasks.yaml can reference them.
        inputs = dict(payload)
        # Run synchronously — async wrapping is unnecessary at 30s tick.
        result = AisistantCrew().crew().kickoff(inputs=inputs)
        # Extract per-task structured outputs if present.
        outputs = getattr(result, "tasks_output", []) or []
        watch_report_json = "{}"
        diagnoses_json = "[]"
        actions_json = "[]"
        verifications_json = "[]"
        learning_summary = LearningSummary(kb_path=str(KNOWN_FIXES_PATH))
        # Map by pydantic model class
        from pydantic import BaseModel
        for t in outputs:
            po = getattr(t, "pydantic", None)
            if isinstance(po, WatchReport):
                watch_report_json = po.model_dump_json()
                self.state.last_watch = po
            elif isinstance(po, DiagnosesReport):
                diagnoses_json = po.model_dump_json()
                self.state.last_diagnoses = po.items
            elif isinstance(po, ActionsReport):
                actions_json = po.model_dump_json()
                self.state.last_actions = po.items
            elif isinstance(po, VerificationsReport):
                verifications_json = po.model_dump_json()
                self.state.last_verifications = po.items
            elif isinstance(po, LearningSummary):
                learning_summary = po
                self.state.last_learning = po
        return {
            "watch_report_json": watch_report_json,
            "diagnoses_json": diagnoses_json,
            "actions_json": actions_json,
            "verifications_json": verifications_json,
            "learning_summary": learning_summary,
        }

    @listen(run_crew)
    def record_result(self, result: dict) -> str:
        # Pull the watch report out of state for the log line.
        if self.state.last_watch:
            wr = self.state.last_watch
            _health_log(
                f"tick {self.state.tick_number} done: "
                f"healthy={len(wr.healthy)} failing={len(wr.failing)} "
                f"warnings={len(wr.warnings)}"
            )
            if wr.escalation_needed:
                self.state.escalation_pending.append(
                    f"tick {self.state.tick_number}: critical failures in {[f.name for f in wr.failing]}"
                )
        ls = result.get("learning_summary")
        if ls and getattr(ls, "kb_entries_added", 0) > 0:
            _health_log(f"tick {self.state.tick_number} KB grew by {ls.kb_entries_added}")
        return "ok"