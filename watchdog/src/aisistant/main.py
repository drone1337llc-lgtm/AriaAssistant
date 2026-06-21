#!/usr/bin/env python
"""Entry points for the Aria autonomous backend crew.

Usage:
    python -m aisistant.main run        # one tick, sync (kick the crew once)
    python -m aisistant.main loop       # persistent runner (Ctrl-C to stop)
    python -m aisistant.main doctor     # run service health checks directly (no LLM)
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime

from aisistant.config import SAFE_MODE, TICK_SECONDS, load_services
from aisistant.flow import AriaFlow
from aisistant.tools import ServiceHealthTool

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


def run() -> None:
    """Run one tick of the crew synchronously."""
    inputs = {
        "tick_number": 0,
        "services": [s.model_dump() for s in load_services()],
        "log_path": "",
        "kb_path": "",
        "safe_mode": SAFE_MODE,
        "last_summary": "first run",
        "watch_report_json": "{}",
        "diagnoses_json": "[]",
        "actions_json": "[]",
        "verifications_json": "[]",
    }
    from aisistant.crew import AisistantCrew
    AisistantCrew().crew().kickoff(inputs=inputs)


def loop() -> None:
    """Persistent loop — delegates to the runner module."""
    import asyncio
    from aisistant.runner import _main
    asyncio.run(_main())


def doctor() -> None:
    """Health-only check — no LLM, just probe every service and print JSON."""
    results = []
    tool = ServiceHealthTool()
    for s in load_services():
        raw = tool._run(name=s.name)
        results.append({"service": s.name, "host": s.host, "port": s.port, "result": raw})
    print(json.dumps(results, indent=2))


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd = argv[0]
    if cmd == "run":
        run()
    elif cmd == "loop":
        loop()
    elif cmd == "doctor":
        doctor()
    else:
        print(f"Unknown command: {cmd}\nUse 'run', 'loop', or 'doctor'.")


if __name__ == "__main__":
    main()