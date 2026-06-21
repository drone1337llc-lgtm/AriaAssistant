"""Known-fixes KB writer tool — append a new entry (or bump occurrences if duplicate).

Idempotent: writing an entry whose 'id' already exists increments `occurrences`
and updates `verified_at` rather than creating a duplicate.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Type

import yaml
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aisistant.config import KNOWN_FIXES_PATH


class KBWriteInput(BaseModel):
    id: str = Field(..., description="Unique slug, e.g. 'lm_studio_silent_unload'.")
    service: str = Field(..., description="Service name from services.yaml.")
    symptom: str = Field(..., description="Short description of what was observed.")
    cause: str = Field(..., description="Root cause.")
    action: str = Field(..., description="What to do.")
    action_class: str = Field(..., description="restart | kill_process | free_port | switch_model | reconfigure | escalate")


class KBWriterTool(BaseTool):
    name: str = "kb_writer"
    description: str = (
        "Append a fix entry to the known-fixes KB. Idempotent on 'id' — duplicates increment occurrences. "
        "Use this in the learn_task, after a verified fix."
    )
    args_schema: Type[BaseModel] = KBWriteInput

    def _run(self, id: str, service: str, symptom: str, cause: str, action: str, action_class: str) -> str:
        Path(KNOWN_FIXES_PATH).parent.mkdir(parents=True, exist_ok=True)
        if KNOWN_FIXES_PATH.exists():
            with open(KNOWN_FIXES_PATH, "r", encoding="utf-8") as f:
                entries = yaml.safe_load(f) or []
        else:
            entries = []
        now_iso = datetime.utcnow().isoformat() + "Z"
        existing_idx = next((i for i, e in enumerate(entries) if e.get("id") == id), -1)
        if existing_idx >= 0:
            e = entries[existing_idx]
            e["occurrences"] = int(e.get("occurrences", 0)) + 1
            e["verified_at"] = now_iso
            entries[existing_idx] = e
            outcome = "incremented"
        else:
            entries.append({
                "id": id,
                "service": service,
                "symptom": symptom,
                "cause": cause,
                "action": action,
                "action_class": action_class,
                "verified_at": now_iso,
                "occurrences": 1,
            })
            outcome = "added"
        with open(KNOWN_FIXES_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(entries, f, sort_keys=False, allow_unicode=True)
        return f"[kb_writer] {outcome} entry '{id}' (now occurrences={next(e['occurrences'] for e in entries if e['id']==id)})"