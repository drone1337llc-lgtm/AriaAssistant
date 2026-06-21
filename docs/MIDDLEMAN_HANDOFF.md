# Aria Assistant — Middleman Handoff

> User is stepping away from the PC. Smart AI is the middleman — handles routine
> checks, bug reports, and small fixes. Escalate to the user only for irreversible
> actions or things that need their judgement.

## Project Layout (CORRECT location)
- **Live project root:** `C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion`
- This is the **"IK + FloodDiffusion motion" derivative** of the base `AriaAssistantApp`.
  Two other Aria-related dirs exist in `Documents\` and are NOT the live project:
  - `AriaAssistant` (175 items, last touched 2 days ago — has 2-day-old CHANGELOG)
  - `AriaAssistantApp` (base, has the original `start_aria.ps1`)
  - `AriaAssistantAppIKdiffusion` (← THIS ONE — current work, edited today 7:21 PM)
  - `AriaTest` (small testbed, ignore)
  - Don't touch any of the sibling dirs unless the user says so.

### What's actually in this project
| Folder | What it does |
|---|---|
| `aria/` | Godot 4.6.3 Mono project. VRM character, animation state machine, LLM bridge, TTS bridge, window detection. The "body" of Aria. |
| `aria_brain/` | Python FastAPI service — Aria's "mind": strict persona, mood (1–5), ChromaDB long-term memory, reflection scheduler, TTS client, Whisper STT, Telegram bot, PyQt6 chat window, pystray. |
| `aisistant/` | Python CrewAI watchdog — 5 agents (Watcher, Diagnostician, Fixer, Verifier, Knowledge Manager) monitor services every 30s. |
| `astro_assistant/` | Python AI brain for the **Sarah** persona (separate from Aria). Also owns the `motion_library.json` (533 anim specs) that Aria reads at startup. |
| `Coqui-TTS-XTTS-v2-/` | Vendored Coqui TTS. Custom Jessica voice fine-tune lives here. |
| `FloodDiffusion/` | Optional text-to-motion diffusion server. Aria can poll it for new clips via `AriaMotionClient.cs`. |
| `scripts/` | PowerShell launchers: `start-aria-stack.ps1` (orchestrate all 7+ processes), `setup-ssh-to-ai-pc.ps1` (one-time SSH key setup). |
| `tools/` | Training + self-review scripts + shared ffmpeg DLLs. |
| `README.md` | Canonical project README (top-level). Read this first. |
| `docs/` | Handoff notes, status, changelogs, archived outdated READMEs (in `_archive/`). |

### Two-PC architecture
```
PC 1 (this machine)                        PC 2 (AI server, separate box)
  Godot (Aria character)          <--LAN-->   LM Studio (LLM, :1010)
  astro_assistant/client.py                  astro_assistant/server.py (:8765)
  TTS client                                 Coqui TTS server (:5003)
                                            Streamlit dashboard (:8501)
                                            (optional) FloodDiffusion motion server
```

User can also run single-PC mode (everything on one box) — see `README_SINGLE_PC.md`.

## State at handoff (2026-06-15)

✅ **Verified at handoff:**
- [x] **C# compiles clean.** `dotnet build aria/AriaAssistant.csproj` → 0/0/0.
- [x] **Project structure matches `start_aria.ps1` expectations** — it expects to be launched from this folder.

⏳ **Unverified (runtime not tested in this env):**
- Python services (TTS, Astro client/server, dashboard, FloodDiffusion) haven't been smoke-tested.
- Aria herself hasn't been launched — first launch is the verification pass.
- The user said in a previous session that Aria works, just needs the project cleaned up.

## What the middleman should do

### Routine checks (low-effort, do without asking)
- **Compile sanity:** `dotnet build aria/AriaAssistant.csproj`. If it breaks, look at the diff and figure out why.
- **Python syntax check:** if the user touches `astro_assistant/*.py`, run `python -c "import ast; ast.parse(open('file.py').read())"` to catch syntax errors.
- **Changelog discipline:** any user-facing change needs a new `docs/CHANGELOG_<DATE>.md` (one paragraph per change, what + why + how to verify).
- **Bug fixes with single-target changes** in the C# or Python code. Read the relevant file, find the smallest fix, write a test if the change is non-trivial, document.
- **Animation state wiring** in `aria/scripts/*.cs` if the user asks for a new state.
- **VRM expression name mapping** in `aria/scripts/ExpressionController.cs` if a new emotion needs a face.
- **TTS voice tweaks** in `astro_assistant/tts_client.py` (timing, voice, sample rate).
- **Inspect logs** if they exist: `astro_assistant/logs/*.log`, Godot Output panel breadcrumbs.

### Things the user does NOT need to be asked about
- Fixing compile errors
- Adding missing imports / using statements
- Refactoring helper functions within a single file
- Updating the project README when scope changes
- Adding a new animation if the scene has a slot for it
- Adding new emotion states (mapping to existing VRM blend shapes)
- Performance tuning of the existing code
- Logging discipline (better breadcrumb output)

### Things the user SHOULD be asked about
- Any change to `aria/project.godot` (engine version, window mode, autoload, autostart scripts)
- Editing `aria/Main.tscn` node graph (visual / structural changes)
- Touching the VRM model (`Aria.vrm`) or its import settings
- Restarting Godot / launching the Godot app
- Restarting the TTS server / Astro server / dashboard
- Sending real LLM traffic to the user's API endpoints (LM Studio, etc.)
- Push/merge/reset on the git repo
- Deleting log files
- Modifying the Coqui TTS fine-tune or training data
- Touching the sibling Aria* dirs in `Documents\`
- Hardware changes (USB, GPU, etc.)

## How to run / verify

**One-shot launch (PC 1 only — full single-PC mode):**
```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
.\start_aria.ps1
```
This creates the Python venv, installs all deps, opens the firewall, and launches every service in its own window. ~35s warm-up, then a health check prints PASS/FAIL per service.

**Compile check (fastest sanity test):**
```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
dotnet build aria/AriaAssistant.csproj
```

**Two-PC setup:** run `start_aria_server.ps1` on PC 2 first, then `start_aria.ps1` on PC 1. Both READMEs (`README_PC1.md`, `README_PC2.md`) walk through the setup.

**If something doesn't start:**
- TTS / motion / dashboard FAILED → check that service's cmd window for the Python error. Most often a missing dep; re-run `.\start_aria.ps1 --all` to reinstall.
- Chat FAILED (port 8767) → the chat server is bundled with Godot. Open the Godot window, check the Output panel at the bottom.
- Godot not found → install Godot 4.6.3 Mono (not the regular one) from https://godotengine.org/download. The script auto-detects on next run.

## Triage ladder (when user reports a bug)

1. **Read the relevant file.** Project is small, ~8 C# scripts and ~10 Python modules.
2. **Tail the matching log** if it exists. Godot Output panel and Python service terminals are breadcrumbs.
3. **Reproduce minimally** — what input causes it? Where in the code path?
4. **Make the smallest fix** that addresses the root cause. Not "fix A or B" — ONE targeted change.
5. **Verify by rebuilding** (`dotnet build`) or restarting the affected service.
6. **Document in `docs/CHANGELOG_<DATE>.md`** — short and to the point. What broke, what fixed it, how to verify.

If you fix something, you should be able to describe it in 2 sentences without rereading the code. If you can't, you don't understand the fix yet — read more.

## Hard loop rule (for workers)

If you attempt the **same fix category on the same root cause 3 times** without success, STOP and report:

> "I've tried the same fix 3 times. None worked:
> - Attempt 1: <what I changed, what happened>
> - Attempt 2: <what I changed, what happened>
> - Attempt 3: <what I changed, what happened>
> Root cause hypothesis: <one sentence>
> What I want to try next (or what I need from you): <one option>"

Going in circles is your failure, not the user's.

## Communication style

- Be terse. State the result, not the process.
- Acknowledge in one line, then do the work.
- If you finish a task, say what you did and where to look.
- If a task is too big, say "this is bigger than I can do in one pass — let me break it down" and propose a plan.
- Don't ask the user to confirm small decisions.
- Ask one question at a time, and only when you really need their judgement.
