"""Known-fixes KB search tool."""
from __future__ import annotations

from typing import Type

import yaml
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aisistant.config import KNOWN_FIXES_PATH


class KBSearchInput(BaseModel):
    query: str = Field(..., description="Text to search for in symptom/cause/action.")
    service: str = Field("", description="If set, restrict to entries for this service.")


class KBSearchTool(BaseTool):
    name: str = "kb_search"
    description: str = (
        "Search the known-fixes KB (knowledge/known_fixes.yaml) for prior fixes that match a symptom. "
        "Use this when the Diagnostician wants to check 'have we seen this before?'."
    )
    args_schema: Type[BaseModel] = KBSearchInput

    def _run(self, query: str, service: str = "") -> str:
        if not KNOWN_FIXES_PATH.exists():
            return "[kb_search] KB empty."
        try:
            with open(KNOWN_FIXES_PATH, "r", encoding="utf-8") as f:
                entries = yaml.safe_load(f) or []
        except yaml.YAMLError as exc:
            return f"[kb_search] YAML error: {exc}"
        needle = query.lower()
        results = []
        for e in entries:
            if service and e.get("service") != service:
                continue
            haystack = " ".join(str(e.get(k, "")) for k in ("symptom", "cause", "action", "id")).lower()
            if needle in haystack:
                results.append(e)
        if not results:
            return f"[kb_search] no entries match '{query}' (service='{service}')"
        # Return concise summaries
        out = []
        for e in results[:10]:
            out.append(
                f"- id={e.get('id')} service={e.get('service')} action={e.get('action_class')} "
                f"occ={e.get('occurrences', 0)} :: {e.get('symptom','')}"
            )
        return "\n".join(out)