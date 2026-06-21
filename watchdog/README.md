# aisistant — Aria Autonomous Backend Crew

A persistent, multi-agent CrewAI crew that watches Aria's two-PC backend, diagnoses failures,
applies safe fixes, and learns from them.

## What it watches

By default, services listed in [`knowledge/services.yaml`](knowledge/services.yaml):

| Service | Where | Port | Critical |
|---|---|---|---|
| AriaChatServer | PC 1 (`127.0.0.1`) | 8767 | yes |
| TTS server | PC 1 (`127.0.0.1`) | 5003 | yes |
| LM Studio | PC 2 (`192.168.68.88`) | 1010 | yes |
| Astro server (WS) | PC 2 | 8765 | no |
| Motion server | PC 2 | 8766 | no |

Edit `knowledge/services.yaml` to add or remove services.

## How it works

Every `AISISTANT_TICK_SECONDS` (default 30s), a Flow tick runs:

1. **Watcher** probes each service + tails `aria_health.log`.
2. **Diagnostician** correlates failures with the known-fixes KB + log context.
3. **Fixer** applies the safest remediation, or escalates if `safe_mode` blocks it.
4. **Verifier** re-checks every touched service.
5. **Knowledge Manager** appends verified fixes to `knowledge/known_fixes.yaml`.

## Quick start

```bash
# 1. Copy the env template
copy .env.example .env        # then edit if needed

# 2. Install deps (uv is the package manager)
uv sync

# 3. Smoke test — health probes, no LLM
uv run python -m aisistant.main doctor

# 4. Run one crew tick (uses LM Studio)
uv run python -m aisistant.main run

# 5. Start the persistent runner (Ctrl-C to stop)
uv run python -m aisistant.main loop
```

## Safety

`AISISTANT_SAFE_MODE=true` (default) makes the Fixer refuse:

- any `taskkill` against non-Aria processes
- any edit under `C:\Users\Tench\Documents\AriaAssistant*\`
- any edit to `.env` or `pyproject.toml`
- any switch of LM Studio model (requires the user to re-load in the UI)

Anything that's blocked becomes an escalation in the live state and the `escalations.log` file.

## Project layout

```
aisistant/
├── AGENTS.md                          # the canonical CrewAI reference
├── pyproject.toml                     # deps + entry points
├── .env.example                       # env template (copy to .env)
├── knowledge/
│   ├── services.yaml                  # what to watch (editable)
│   ├── known_fixes.yaml               # KB (auto-grown by Knowledge Manager)
│   └── user_preference.txt            # default sample
└── src/aisistant/
    ├── main.py                        # entry: run | loop | doctor
    ├── runner.py                      # persistent tick scheduler
    ├── flow.py                        # persistent Flow (@persist + state)
    ├── crew.py                        # 5 agents, 5 tasks, sequential
    ├── config.py                      # service map, paths, behavior flags
    ├── schemas.py                     # Pydantic models for task outputs
    ├── tools/                         # service_health, log_tail, process_check,
    │                                   #   port_check, network_check,
    │                                   #   action_executor, kb_search, kb_writer
    └── config/
        ├── agents.yaml                # agent roles, goals, backstories
        └── tasks.yaml                 # task descriptions and expected outputs
```

## Files we touched / created

All files under `C:\Users\Tench\Documents\AI Learning\aisistant\` are new. We did not modify
anything under `C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\` or
`C:\Users\Tench\Documents\AI Learning\astro_assistant\` — those projects are unrelated.

## Next steps

1. Run `uv run python -m aisistant.main doctor` — confirm LM Studio and the other services respond.
2. Run `uv run python -m aisistant.main run` — see the crew actually reason about a real failure.
3. Once you're satisfied, `uv run python -m aisistant.main loop` to start the watchdog.
4. Watch `aria_health.log` to see live ticks.