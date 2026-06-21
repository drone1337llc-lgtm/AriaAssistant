# Aria Assistant — Middleman Status

> Last updated: 2026-06-15 (Smart AI middleman session)

## ✅ Verified at handoff
- [x] **C# compiles clean.** `dotnet build aria/AriaAssistant.csproj` → 0 warnings, 0 errors.
- [x] **Project structure correct** — confirmed `aria/`, `astro_assistant/`, `Coqui-TTS-XTTS-v2-/`, `start_aria.ps1` all in place.
- [x] **Launch script present** — `start_aria.ps1` ready to run from project root.
- [x] **Two-PC READMEs present** — `README_PC1.md` and `README_PC2.md` walked through.

## ⏳ Unverified (not yet runtime-tested)
- Aria herself hasn't been launched yet in this env. The first launch is the verification pass.
- Python services (TTS, Astro, dashboard, FloodDiffusion) not smoke-tested from the middleman.
- The Coqui TTS server (PC 2) not started. Needs `start_aria_server.ps1`.

## 📁 Key paths
- Live project: `C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion`
- Middleman handoff: `docs/MIDDLEMAN_HANDOFF.md`
- Project READMEs: `README.md`, `README_PC1.md`, `README_PC2.md`, `README_SINGLE_PC.md`
- Launch script: `start_aria.ps1` (PC 1) / `start_aria_server.ps1` (PC 2)
- C# project file: `aria/AriaAssistant.csproj`
- Vendor TTS: `Coqui-TTS-XTTS-v2-/`

## 🛠 Open handles (things middleman can do without asking)
- Compile + sanity checks
- Bug fixes with single-target changes
- Changelog updates (new `docs/CHANGELOG_<DATE>.md`)
- VRM expression name mapping tweaks
- Animation state wiring
- TTS client tweaks
- Python syntax validation
- Log file inspection

## ⚠️ Escalate to user
- Any change to `aria/project.godot`
- Touching the VRM model or its import settings
- Editing `aria/Main.tscn` node graph
- Restarting Godot / launching the app
- LLM traffic to user's API endpoints
- Git push/merge/reset
- Deleting log files
- Modifying the Coqui TTS fine-tune or training data
- Touching any of the sibling Aria* dirs in `Documents\` (`AriaAssistant`, `AriaAssistantApp`, `AriaTest`)

## How to resume the middleman role
When the user comes back, they (or a fresh session) should:
1. Read `docs/MIDDLEMAN_HANDOFF.md` (the playbook)
2. Skim this `docs/STATUS.md` (current verified state)
3. Pick up where this left off

If the user wants Aria running:
```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
.\start_aria.ps1
```
