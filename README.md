# Aria — Self-Contained Project

> **Aria** — a Godot 4.6 desktop-pet character with an LM Studio brain, persistent
> ChromaDB memory, mood tracking, automatic reflection, Coqui XTTS-v2 voice, and a
> CrewAI watchdog that auto-diagnoses and fixes backend failures.

## Bridge + persistence (new, 2026-06)

Cross-PC traffic now rides a **persistent 3-node mesh** (`C:\Users\Tench\Documents\bridge`):
PC1 (.15), PC2 (.88), TrueNAS (.64). Aria's PC1 clients talk to **`127.0.0.1`**
ports that the bridge tunnels to PC2 — no more brittle direct LAN connections.
The PC2 backend (brain/TTS/motion) is kept alive by a supervisor + scheduled task.

- Full operations guide + every gotcha: **[docs/BRIDGE_AND_PERSISTENCE.md](docs/BRIDGE_AND_PERSISTENCE.md)**
- Health check from PC1: `.\scripts\bridge-health.ps1`
- Resume notes / current state: **[docs/RESUME_HERE.md](docs/RESUME_HERE.md)**

Drop this folder on any drive, `uv sync` each Python project, install the listed
external dependencies, and Aria runs end-to-end.

---

## Layout

```
AriaAssistantAppIKdiffusion\
├── aria\                # Godot 4.6 Mono project — the character herself
├── brain\               # FastAPI service — personality, memory, mood, TTS, voice I/O
├── watchdog\            # CrewAI — 5 agents, 9 tools, monitors services every 30s
├── motion_lib\          # motion_library.json + the code that produces + serves it
├── .venv\               # ⚠️ LEGACY — originally C:\Users\Tench\Documents\AriaAssistant\.venv
│                        # Created at the OLD path; pyvenv.cfg still says `command = ...AriaAssistant\.venv`
│                        # Used by the old astro_assistant scripts. Do NOT use for new work —
│                        # new Python projects (brain/, watchdog/) each have their own .venv.
├── Coqui-TTS-XTTS-v2-\  # ⚠️ LOCKED — can't rename to tts/ because Windows holds an open file handle
│                        # on something inside scripts/. Leave the name as-is.
├── astro_assistant\     # ⚠️ LOCKED EMPTY DIR — can't delete because old Python processes still
│                        # have it as CWD (their motion_server.py / dashboard.py was launched
│                        # from this folder). See "Zombie processes" below.
├── FloodDiffusion\      # Optional text-to-motion diffusion server
├── docs\                # Handoff notes + archived outdated READMEs
├── scripts\             # PowerShell launchers (start-aria-stack.ps1, ssh setup)
├── tools\               # Shared utilities (ffmpeg DLLs etc.)
├── logs\                # Shared runtime logs (aria_health.log)
├── README.md            # ← you are here
└── SETTINGS.md          # Every knob in the stack — read this to tweak anything
```

### Folder-by-folder

| Folder | Role | Depends on |
|---|---|---|
| `aria/` | Godot 4.6.3 Mono project. 3D character, animation retargeter, SpringBone physics (with inertia coupling), Win32 transparent window tricks, TTSBridge to XTTS, LLM bridge. **The body of Aria.** | Godot 4.6.3 Mono, .NET 8 SDK |
| `brain/` | FastAPI service. Aria's "mind" — strict persona, mood (1–5), ChromaDB long-term memory, reflection loop (every 2h), TTS client, Whisper STT, Telegram bot, PyQt6 chat window, system tray. **Renamed from `aria_brain/`.** | LM Studio (`:1010`), ChromaDB (`:8000` recommended, falls back to local), TTS server (`:5003`) |
| `watchdog/` | CrewAI watchdog. 5 agents (Watcher → Diagnostician → Fixer → Verifier → Knowledge Manager) poll every 30s. **Renamed from `aisistant/`.** | LM Studio (`:1010`) |
| `motion_lib/` | `motion_library.json` (533 anim specs that Aria reads at startup) + the Python code that produces + serves it. Aria's only dependency on what used to be `astro_assistant`. | LM Studio (for ingest) |
| `tts/` | Vendored Coqui-XTTS-v2 repo + fine-tuned voice models: `Ana_Voice` and `Jessica_Voice` (Aria's voice). The custom `tts_server_jessica.py` in `aria/scripts/` wraps this and serves audio on `:5003`. **Renamed from `Coqui-TTS-XTTS-v2-`.** | Coqui TTS deps in a venv |
| `FloodDiffusion/` | Text-to-motion diffusion model. Optional. Aria's `AriaMotionClient.cs` can poll it for new clips on `:8766`. Usually not running. | PyTorch + CUDA |
| `docs/` | Handoff notes, status, changelogs, archived outdated READMEs (in `_archive/`). | n/a |
| `scripts/` | PowerShell launchers: `start-aria-stack.ps1` (orchestrate 7+ processes), `setup-ssh-to-ai-pc.ps1` (one-time SSH key setup). | SSH client for PC 2 |
| `tools/` | Shared utilities (ffmpeg-shared DLLs, etc.). | n/a |

### External (NOT in this folder — install on the host)

| What | Where | Why |
|---|---|---|
| **Python 3.12+** | python.org or via `uv` | Runtime for all Python services |
| **uv** | astral.sh/uv | Python package manager (handles all 3 venvs) |
| **Godot 4.6.3 Mono** | godotengine.org | Runs the `aria/` project |
| **.NET 8 SDK** | dotnet.microsoft.com | Godot Mono + Aria's C# scripts |
| **LM Studio** | lmstudio.ai | LLM inference on PC 2 |
| **OpenSSH Client + Server** | Windows Optional Feature | `start-aria-stack.ps1` uses SSH to manage PC 2 services |

### On the AI PC (PC 2, 192.168.68.88)

- **LM Studio** running with at least `qwen2.5-3b-instruct` loaded (and `humanish-roleplay-llama-3.1-8b-i1` for chat, `minimax-m2.7` for reasoning — unload everything else to free VRAM)
- Optional: **ChromaDB** server on `:8000` — `brain/` falls back to local DuckDB+Parquet if it's down

---

## Quick start (assumes the host already has the external dependencies)

```powershell
# 1. Install all Python deps in the three venvs
cd "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\brain"
uv sync

cd "..\watchdog"
uv sync

# 2. (optional) Set up SSH key auth to PC 2 (one time)
cd "..\scripts"
.\setup-ssh-to-ai-pc.ps1

# 3. Start everything
.\start-aria-stack.ps1 start
# (status: .\start-aria-stack.ps1 status ; tail logs: .\start-aria-stack.ps1 tail ; auto-restart: .\start-aria-stack.ps1 watch)

# 4. Open Godot 4.6.3 (Mono), import the project at this folder's aria\ subdir, F5 to play
```

---

## Services & ports

| Port | Service | Where it runs | Started by |
|---|---|---|---|
| 1010 | LM Studio (LLM + embeddings) | PC 2 | Manual (LM Studio GUI) |
| 5003 | Custom XTTS Jessica voice server | PC 1 | `aria/scripts/tts_server_jessica.py` |
| 8000 | ChromaDB (recommended) | PC 2 | `brain/setup_chromadb_pc2.ps1` once |
| 8766 | Motion server (FloodDiffusion) | PC 2 (optional) | `motion_lib/motion_server.py` |
| 8767 | Aria chat server (HTTP for dashboard) | PC 1 (Godot) | auto, embedded in `aria/` |
| 8770 | Aria Brain (FastAPI) | PC 1 | `brain/.venv\Scripts\python.exe -m aria_brain.main` |

---

## Where to start

1. **New to Aria?** Read `SETTINGS.md` — it lists every knob and where to find it.
2. **Want to tweak a model?** See "Model routing" in `SETTINGS.md` (Brain section + Watchdog section).
3. **Something not working?** Run `watchdog/uv run python -m aisistant.main doctor` to see which services are down.
4. **Customize Aria's personality?** Edit `brain/src/aria_brain/personality.py` (the persona prompt + drift detector).
5. **Adjust SpringBone physics?** Edit the inspector-exposed fields on the SpringBoneSimulator node in `aria/scenes/Main.tscn` (or directly in `aria/scripts/SpringBoneSimulator.cs`).

---

## Recent changes (last week)

- **Folder renames** (cleaner organization):
  - `aria_brain/` → `brain/`
  - `aisistant/` → `watchdog/`
  - `astro_assistant/` → trimmed to `motion_lib/` (Sarah content deleted)
  - `Coqui-TTS-XTTS-v2-/` → `tts/` (note: `astro_assistant` + `Coqui-TTS-XTTS-v2-` rename failed due to OS file locks; kept the old names — internal references updated to use `motion_lib/`)
- **Sarah character deleted** from `astro_assistant/` (model files, dashboard, server.py, voice_speak.py, astrobud_overlay.py, all diagnostic scripts)
- **`brain/` added** (was in workspace, now part of the project) — Aria's personality, memory, mood, reflection, voice I/O
- **`watchdog/` upgraded** from scaffold to the full CrewAI watchdog with 9 custom tools
- **`scripts/` added** — `start-aria-stack.ps1`, `setup-ssh-to-ai-pc.ps1`
- **`SpringBoneSimulator.cs`** — added inertia tracking so Aria's hair/skirt/bust react to walking and turning
- **`brain/personality.py`** — drift detection rejects non-Latin-script replies and retries with stronger English constraint
- **Voice in chat window** — added 🎤 hold-to-talk + "speak" checkbox (QSoundEffect plays TTS)
- **Coqui cleanup** — freed 40 GB by trashing 3 old AstroBud voice trainings + 1 empty run + samples/

---

## Zombie processes — important

When you ran the old Sarah/AstroBud stack before this reorganization, the Python
processes for `motion_server.py`, `tts_server_jessica.py`, and `dashboard.py`
were started with their CWD = the old `astro_assistant/` folder. The OS holds
that folder as long as the processes are alive, which is why the empty
`astro_assistant/` directory can't be deleted (it's still in use as a CWD).

On a typical day after this reorganization, you may have:

| What | How many | How to tell legit from zombie |
|---|---|---|
| `tts_server_jessica.py --port 5003` | up to 4 | Only the one with `Listen` state on port 5003 is actually serving. The others are bind-failed-but-still-running. |
| `motion_server.py --port 8766` | up to 3 | Same — only the actual `Listen` PID matters. |
| `streamlit run dashboard.py --server.port 8501` | up to 2 | Sarah's AstroBud dashboard. **NOT used by Aria. Kill both.** |

**Cleanup one-liner** (run in PowerShell, then close any open Streamlit browser tabs):

```powershell
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    $cmd -and ($cmd -match "dashboard\.py|dashboard\.streamlit")
} | Stop-Process -Force

# Then kill any extras keeping port 5003 / 8766 busy
Get-NetTCPConnection -LocalPort 5003 -State Listen | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 8766 -State Listen | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
```

After the cleanup, the empty `astro_assistant/` directory should be deletable.
If it still says "in use", restart the machine — the OS is more stubborn about
releasing CWD handles than about file handles.

---

## Archived (old / wrong / outdated)

These live in `docs/_archive/` for archaeology — do NOT use them as current documentation.

- `aria/README.md` (was actually the VRM addon README — V-Sekai team, not Aria)
- `astro_assistant/README.md` (same VRM addon README duplicated)
- `aria/README_SETUP.md` (referenced `AriaCompanion` path that no longer exists)
- `aria/README_MAIN_PC.md`, `aria/README_AI_PC.md` (were AstroBud/Sarah setup, not Aria)
- `aria/README.ja.md` (outdated Japanese translation)
- `aria/start_aria.ps1.trashed` (a previous launcher's trashed version)

---

## Operational notes

- **Logs**: `logs/aria_health.log` is the unified health log; multiple services append to it.
- **Migrations / backups**: ChromaDB stores long-term memories in DuckDB+Parquet at
  `brain/chroma_local/` if PC 2's ChromaDB is down. To back up Aria's memories,
  tar up that folder.
- **Git**: this folder has a `.git/` but the history is messy. Treat it as a working snapshot,
  not a clean history. If you commit, `git add -A && git commit -m "..."` works fine.

---

## License

See `LICENSE` in `aria/`. Mixed — Aria's original assets + V-Sekai VRM addon + Coqui TTS MPL-2.0.
For personal use; redistribution requires honoring each component's license.