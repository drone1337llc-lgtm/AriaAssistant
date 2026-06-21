# Aria — a desktop AI companion

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](http://creativecommons.org/licenses/by-nc-sa/4.0/)

Aria is a self-hosted, locally-run AI companion that lives on the desktop as a 3D
animated character. She has a persistent personality, long-term memory, mood, a voice,
and a body that walks, climbs, gestures, and emotes on top of whatever you're doing. All
of the intelligence runs on your own hardware across a small private cluster — no cloud
inference, no per-token billing.

This repository is the whole system: the Godot front-end (the character you see), the
Python "brain" (personality, memory, mood, reasoning), a Go networking layer that meshes
the machines together, the voice stack (speech-in, speech-out), and the self-healing
tooling that keeps it all alive.

> **Status:** actively developed, single-author hobby/research project. The networking
> mesh, brain, and persistence are stable; the streaming-voice pipeline is freshly built
> and in shakedown; PersonaPlex full-duplex voice is researched and parked (see
> `PERSONAPLEX_NOTES.md`). Full detail: [Project status](#project-status).

---

## Table of contents
- [What Aria is](#what-aria-is)
- [Topology — the two-PC + NAS cluster](#topology)
- [Architecture](#architecture)
- [Subsystems](#subsystems)
- [Model roster](#model-roster)
- [Services & ports](#services--ports)
- [Repository layout](#repository-layout)
- [Running it](#running-it)
- [Project status](#project-status)
- [Credits & Citations](#credits--citations)
- [License](#license)

---

## What Aria is

Aria combines five things most "AI assistant" projects keep separate:

1. **A body.** A VRoid anime character rendered by Godot as a transparent, always-on-top
   desktop overlay. She walks, scales window edges, sits on ledges, gestures, blinks, and
   lip-syncs — driven by baked animations, procedural IK, and secondary-motion physics.
2. **A brain.** A FastAPI service giving her a fixed personality, a mood that drifts over
   time, long-term vector-searchable memory, periodic self-reflection, and the judgment to
   route real tasks (code, vision, analysis) to specialist models.
3. **A voice.** Text-to-speech in a custom-cloned voice ("Jessica", an XTTS-v2 fine-tune)
   plus speech-to-text (Whisper) — now being upgraded to a low-latency **streaming**
   pipeline with push-to-talk barge-in.
4. **Local model hosting.** Five role-specialized LLMs served through LM Studio (chat,
   triage, code, vision, embeddings) — the right model for the right job.
5. **A private cluster.** A custom Go mesh ("the bridge") links the workstation, the AI
   box, and a NAS over a self-healing full-mesh WebSocket network with TCP-over-WebSocket
   tunnels, so the front-end on one machine transparently reaches services on another.

---

## Topology

Aria runs across three nodes on the LAN, joined by the bridge mesh:

| Node | Hostname | Role | Notable hardware |
|------|----------|------|------------------|
| **PC1** | `Sergio WilliamsMain` (.15) | Front-end / workstation: Godot character, chat tray, mic & speakers | RTX 4080 SUPER (16 GB) |
| **PC2** | `AIassistant` (.88) | Always-on backend: brain, LLM host, TTS, STT, motion, memory | RTX 3090 (24 GB) |
| **NAS** | `DeepSpace` (.64) | Storage / third mesh node | TrueNAS |

The backend on PC2 is **persistent** (a supervised, auto-starting service set), so as long
as the machines are on, Aria's mind is available; the front-end on PC1 is launched on
demand. The character on PC1 reaches the backend on PC2 entirely through the bridge's local
tunnels (e.g. `127.0.0.1:8770` on PC1 forwards to the brain on PC2).

---

## Architecture

```
        PC1 (Sergio WilliamsMain)                         PC2 (AIassistant)
 ┌────────────────────────────┐        ┌──────────────────────────────────┐
 │ Godot front-end (C#)        │        │ Aria Brain (FastAPI)             │
 │  • CharacterController      │        │  • personality / mood / memory   │
 │  • IK + spring-bone physics │  mesh  │  • task routing → specialists    │
 │  • Expression / lip-sync    │ tunnels│  • /message, /chat, /voice-stream│
 │  • TTSBridge / LLMBridge    │◄──────►│ LM Studio  ── 5 role models      │
 │  • VoiceInput (PTT)         │  (Go   │ Coqui XTTS-v2 ── "Jessica" voice │
 │  • chat tray (PyQt)         │ bridge)│ faster-whisper ── STT            │
 └────────────────────────────┘        │ motion server ── 533+ anims      │
                                        │ ChromaDB ── vector memory        │
        NAS (DeepSpace) ── mesh node    │ CrewAI watchdog ── self-healing  │
                                        └──────────────────────────────────┘
```

Communication is layered:
- **Bridge mesh (Go):** every node dials every other node over WebSocket (dial-if-greater-IP
  rule with a canonical-connection tie-break so links never flap). On top of the mesh it
  multiplexes **TCP-over-WebSocket tunnels**, so a local port on one machine maps to a
  service port on another.
- **Brain API (HTTP/WS):** the front-end and tray hit `/message`, `/chat`, and the new
  `/voice-stream` WebSocket; the brain calls LM Studio, ChromaDB, Whisper, and the TTS
  server locally on PC2.

---

## Subsystems

### The bridge (Go)
A full-mesh networking daemon. One writer per connection (per-connection write mutex to
satisfy gorilla/websocket's concurrency rule), a deterministic canonical-connection
tie-break to prevent duplicate-link flapping, multiplexed TCP-over-WebSocket tunnels
(open/data/close framing), a Windows Service (SCM) host so it runs headless at boot, and a
multi-node web GUI. Config lives outside the repo at `~/.bridge/config.yaml` (peers +
tunnels) and differs per machine (PC1 defines the tunnels; PC2 does not).

### The brain (Python / FastAPI)
The orchestrator. Each reply is built from a strict persona prompt + current mood +
retrieved memories + system context; every exchange is stored in vector memory; mood drifts
over time; and the brain reflects on its own when idle. It **routes**: casual conversation
stays on the fast chat model, while real tasks (code, debugging, analysis — detected
heuristically) go to the capable coder model with a longer budget and a "do the work, don't
refuse" task-mode prompt. Endpoints: `/message`, `/chat` (WS), `/voice-stream` (WS),
`/transcribe-bytes`, `/reflect`, `/health`.

### The front-end (Godot 4.6.3, Mono/C#)
A transparent, click-through, always-on-top overlay. Highlights: a locomotion + climb state
machine (`CharacterController`), procedural inverse-kinematics chains (`AriaIKController` /
FABRIK), secondary-motion spring physics for hair/skirt/bust (`SpringBoneSimulator`),
blendshape expressions and lip-sync (`ExpressionController`), and bridges to the brain
(`LLMBridge`), voice (`TTSBridge`, `VoiceInput`), and the motion library
(`AriaMotionClient`). Mixamo `.fbx` clips are baked and retargeted onto the VRoid rig at
load. Win32 tricks (WndProc hook, hit-test, transparent/layered window) make her a true
desktop pet.

### Voice
- **TTS:** a persistent Coqui **XTTS-v2** server speaking a custom-cloned voice ("Jessica"),
  fine-tuned by the author on their own voice data; a streaming endpoint (`/tts_stream`)
  emits audio as it is generated.
- **STT:** **faster-whisper** transcribes microphone input.
- **Streaming pipeline (new):** the brain streams its reply token-by-token, chunks it into
  sentences, and pipes each finished sentence to streaming TTS so Aria starts speaking ~one
  sentence after you finish — with a same-button **push-to-talk barge-in** (press =
  interrupt + listen, release = send). See `docs/STREAMING_VOICE.md`.

### Memory
**ChromaDB** stores episodic memories, facts, and reflective "thoughts" as embeddings (via
the Qwen3 embedding model), retrieved by semantic similarity each turn. An on-disk local
fallback keeps memory working even if the shared server is down.

### Motion library
A motion server feeds the front-end a large catalog of animations (the baked Mixamo set
plus a JSON-described library the character reads at startup). **FloodDiffusion**, an
optional text-to-motion diffusion server, can generate new clips on demand; it is usually
not running.

### Watchdog (CrewAI)
An optional self-healing layer: a small crew of CrewAI agents (watcher → diagnostician →
fixer → verifier → knowledge-manager) that polls the services and attempts automatic
recovery. The primary persistence mechanism is the PC2 **supervisor + scheduled task**; the
watchdog is a higher-level auto-diagnosis complement.

---

## Model roster

All LLMs are served locally through **LM Studio** and addressed by role; the role→model
mapping lives in `brain/.env` (machine-local, not in git):

| Role | Model | Purpose |
|------|-------|---------|
| **chat** | `humanish-roleplay-llama-3.1-8b-i1` | Aria's conversational voice |
| **triage / parser** | `qwen2.5-coder-1.5b-instruct` | fast structured routing/classification |
| **coder** | `nvidia_nvidia-nemotron-nano-9b-v2` | heavy reasoning, code, analysis |
| **vision** | `qwen/qwen2.5-vl-7b` | image / screenshot / video understanding |
| **embed** | `text-embedding-qwen3-embedding-0.6b` | ChromaDB vector embeddings |

---

## Services & ports

Each service runs on PC2 (except the Godot-embedded chat server) and is reached from PC1
through the bridge tunnels at `127.0.0.1`:

| Port | Service | Host |
|------|---------|------|
| 1010 | LM Studio (LLM + embeddings) | PC2 |
| 5003 | XTTS "Jessica" TTS server (`/tts`, `/tts_stream`) | PC2 |
| 8000 | ChromaDB | PC2 |
| 8766 | Motion server (FloodDiffusion, optional) | PC2 |
| 8767 | Aria chat server (HTTP, dashboard) | PC1 (Godot) |
| 8770 | Aria Brain (FastAPI) | PC2 |

---

## Repository layout

```
bridge/            Go mesh-networking daemon + TCP-over-WS tunnels (Windows service)
brain/             Aria Brain — FastAPI: personality, memory, mood, reflection, voice
  src/aria_brain/  llm, brain orchestrator, memory, mood, personality, server, voice, tts
aria/              Godot 4.6.3 project (the character)
  scripts/         C#: CharacterController, IK, SpringBoneSimulator, bridges, VoiceInput …
  addons/          godot-vrm, MToon shader, mixamo_animation_batcher
  ani/             Mixamo .fbx animation clips
motion_lib/        Motion server + library the front-end mirrors
watchdog/          CrewAI self-healing agents (optional)
FloodDiffusion/    Optional text-to-motion diffusion server (gitignored / machine-local)
scripts/           PC2 supervisor, autostart installer, sync/health tooling, TTS server
docs/              Architecture, ops, resume notes, streaming-voice + PersonaPlex design
SETTINGS.md        Every configurable knob in the stack
PERSONAPLEX_NOTES.md   Findings + revival plan for the parked full-duplex voice route
```

---

## Running it

Detailed, machine-labeled runbooks live in `docs/` — start with `docs/RESUME_HERE.md`
(current state + exact next steps) and `docs/BRIDGE_AND_PERSISTENCE.md`; `SETTINGS.md`
lists every knob. In brief:

- **PC2 (backend, always-on):** Python venv for the brain, the Coqui XTTS venv + Jessica
  model, ChromaDB, the motion server, and LM Studio with the five models loaded. The
  supervisor + a scheduled task keep them running; `scripts/` has the installers and a
  health check (`bridge-health.ps1`).
- **PC1 (front-end, on demand):** open the `aria/` project in Godot 4.6.3 (Mono) and run.
  The bridge tunnels make the PC2 services reachable at localhost ports.
- **Bridge:** runs on all three nodes; config at `~/.bridge/config.yaml`.

> **Git note:** one repo, per-machine branches (`main-pc1`, `main-pc2`). Virtual
> environments, the Chroma store, logs, and Godot's `.godot` cache are **gitignored** and
> machine-local — and so is `brain/.env`, so model/voice config is set per machine.

---

## Project status

- ✅ **Bridge mesh + tunnels** — stable across all three nodes.
- ✅ **Brain** — personality / memory / mood / reflection + task routing; persistent on PC2.
- ✅ **Voice (turn-based)** — XTTS "Jessica" TTS + Whisper STT, working.
- 🔶 **Streaming voice** — code complete (brain `/voice-stream`, streaming TTS, Godot
  `VoiceInput`); in shakedown / in-editor testing.
- 🔶 **Secondary-motion physics** — hair/skirt/bust spring sim depends on the imported
  model's skin weights; under investigation (see `docs/RESUME_HERE.md`).
- ⏸️ **PersonaPlex full-duplex voice** — researched, ran on the 3090, parked pending a
  dedicated GPU (see `PERSONAPLEX_NOTES.md`).

---

## Credits & Citations

This project is built by **Sergio Williams** ([github.com/drone1337llc-lgtm](https://github.com/drone1337llc-lgtm/AriaAssistant))
and stands on a large amount of open-source software and published research. Everything
below is either an upstream component (cited to its authors/source) or original work (cited
to the author).

### Original work — © Sergio Williams, 2026
Original to this project and authored by Sergio Williams: the bridge full-mesh networking +
TCP-over-WebSocket tunneling and Windows-service host; the Aria Brain orchestrator
(personality system, memory wiring, mood model, reflection loop, task routing, and the
streaming-voice orchestration); the Godot front-end C# (locomotion/climb state machine, IK
chains, spring-bone simulator, expression/lip-sync controller, the LLM/TTS/motion/voice
bridges, and the streaming `VoiceInput` client); the streaming-TTS server wrapper; the PC2
supervisor/persistence tooling; the CrewAI watchdog configuration; and the **"Jessica"
XTTS voice fine-tune**, trained by the author on their own voice data.

> **How to cite this project:**
> Sergio Williams. *Aria — a desktop AI companion.* 2026. https://github.com/drone1337llc-lgtm/AriaAssistant

### Engine, framework & Godot addons
- **Godot Engine 4.6.3** (Mono/C#) — Juan Linietsky, Ariel Manzur & contributors. MIT. https://godotengine.org
- **godot-vrm** (VRM import + spring bones) — V-Sekai / Godot contributors. MIT. https://github.com/V-Sekai/godot-vrm
- **MToon shader** (toon material for VRM) — based on MToon by Santarh, ported to Godot. MIT. https://github.com/Santarh/MToon
- **mixamo_animation_batcher** — Godot editor addon for batch-importing Mixamo animations (third-party addon).

### Networking — Go (`bridge/`)
- **gorilla/websocket** — BSD-2-Clause. https://github.com/gorilla/websocket
- **gin-gonic/gin** — MIT. https://github.com/gin-gonic/gin
- **spf13/viper** — MIT. https://github.com/spf13/viper
- **shirou/gopsutil** — BSD-3-Clause. https://github.com/shirou/gopsutil
- **go-yaml/yaml v3** — MIT / Apache-2.0. https://github.com/go-yaml/yaml
- **golang.org/x/sys** (Windows service / SCM) — BSD-3-Clause. https://pkg.go.dev/golang.org/x/sys

### Brain & tooling — Python (`brain/`, `watchdog/`)
- **FastAPI** — Sebastián Ramírez. MIT. https://github.com/fastapi/fastapi
- **Uvicorn** / **Starlette** — Encode. BSD-3-Clause. https://www.uvicorn.org
- **httpx** — Encode. BSD-3-Clause. https://www.python-httpx.org
- **Pydantic** — MIT. https://github.com/pydantic/pydantic
- **APScheduler** — MIT. https://github.com/agronholm/apscheduler
- **python-dotenv** — BSD-3-Clause. https://github.com/theskumar/python-dotenv
- **ChromaDB** — Apache-2.0. https://github.com/chroma-core/chroma
- **CrewAI** — crewAIInc. MIT. https://github.com/crewAIInc/crewAI
- **NumPy** — Harris, C.R., et al. (2020). *Array programming with NumPy.* Nature 585, 357–362. BSD-3-Clause. https://numpy.org
- **Pillow** — HPND License. https://github.com/python-pillow/Pillow
- **PyQt6** — Riverbank Computing. GPL-3.0 / commercial. https://www.riverbankcomputing.com/software/pyqt/
- **pystray** — LGPL-3.0. https://github.com/moses-palmer/pystray
- **sounddevice** (+ PortAudio) — MIT. https://github.com/spatialaudio/python-sounddevice
- **keyboard** — Boppreh. MIT. https://github.com/boppreh/keyboard
- **python-telegram-bot** — LGPL-3.0. https://github.com/python-telegram-bot/python-telegram-bot

### Speech (TTS / STT)
- **Coqui TTS / XTTS-v2** — Casanova, E., et al. (2024). *XTTS: a Massively Multilingual
  Zero-Shot Text-to-Speech Model.* Interspeech 2024. arXiv:[2406.04904](https://arxiv.org/abs/2406.04904).
  Coqui TTS, MPL-2.0. https://github.com/coqui-ai/TTS
- **faster-whisper** — SYSTRAN. MIT. https://github.com/SYSTRAN/faster-whisper
- **OpenAI Whisper** — Radford, A., Kim, J.W., Xu, T., Brockman, G., McLeavey, C., &
  Sutskever, I. (2022). *Robust Speech Recognition via Large-Scale Weak Supervision.*
  arXiv:[2212.04356](https://arxiv.org/abs/2212.04356). MIT.

### Language & embedding models (served via LM Studio)
- **LM Studio** — local LLM host/runtime. https://lmstudio.ai
- **NVIDIA Nemotron-Nano-9B-v2** (coder) — NVIDIA (2025). *NVIDIA Nemotron Nano 2: An
  Accurate and Efficient Hybrid Mamba-Transformer Reasoning Model.*
  arXiv:[2508.14444](https://arxiv.org/abs/2508.14444). NVIDIA Open Model License.
  https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2
- **Qwen2.5-VL-7B** (vision) — Qwen Team, Alibaba (2025). *Qwen2.5-VL Technical Report.*
  arXiv:[2502.13923](https://arxiv.org/abs/2502.13923). Apache-2.0.
  https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct
- **Qwen2.5-Coder-1.5B-Instruct** (triage) — Hui, B., et al. (2024). *Qwen2.5-Coder
  Technical Report.* arXiv:[2409.12186](https://arxiv.org/abs/2409.12186). Apache-2.0.
  https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct
- **Qwen3-Embedding-0.6B** (embeddings) — Zhang, Y., et al. (2025). *Qwen3 Embedding:
  Advancing Text Embedding and Reranking Through Foundation Models.*
  arXiv:[2506.05176](https://arxiv.org/abs/2506.05176). Apache-2.0.
  https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- **Humanish-Roleplay-Llama-3.1-8B-i1** (chat) — i1 **GGUF quantization by mradermacher**
  of the *Humanish-Roleplay-Llama-3.1-8B* fine-tune, itself based on Meta's Llama 3.1 8B.
  https://huggingface.co/mradermacher/Humanish-Roleplay-Llama-3.1-8B-i1-GGUF · Base model:
  Grattafiori, A., et al. (2024). *The Llama 3 Herd of Models.*
  arXiv:[2407.21783](https://arxiv.org/abs/2407.21783). Used under the Llama 3.1 Community License.

### Researched / parked — full-duplex voice
- **NVIDIA PersonaPlex** — Roy, R., Raiman, J., Lee, S., Ene, T.-D., Kirby, R., Kim, S.,
  Kim, J., & Catanzaro, B. (2026). *PersonaPlex: Voice and Role Control for Full Duplex
  Conversational Speech Models.* arXiv:[2602.06053](https://arxiv.org/abs/2602.06053).
  Code MIT; weights NVIDIA Open Model License. https://github.com/NVIDIA/personaplex
- **Moshi** (PersonaPlex backbone) — Défossez, A., Mazaré, L., Orsini, M., Royer, A.,
  Kharitonov, E., Hadjeres, G., Zeghidour, N., et al. (2024). *Moshi: a speech-text
  foundation model for real-time dialogue.* arXiv:[2410.00037](https://arxiv.org/abs/2410.00037). Kyutai.

### Assets & infrastructure
- **VRoid Studio** (pixiv Inc.) — the character was created in VRoid Studio and exported in
  the **VRM** format (VRM Consortium). https://vroid.com
- **Adobe Mixamo** — animation clips (`aria/ani/*.fbx`) sourced from Mixamo and used under
  Adobe's license. https://www.mixamo.com
- **TrueNAS** (iXsystems) — storage node of the cluster. https://www.truenas.com
- **FloodDiffusion** (optional text-to-motion) — Shanda AI Research Tokyo (2025). Apache-2.0.
  © 2025 Shanda AI Research Tokyo. https://github.com/ShandaAI/FloodDiffusion — includes code
  from third-party sources under separate licenses (see the project's `THIRD_PARTY_LICENSES.md`).

> Citations reflect best-available information at time of writing; for exact license terms,
> consult each project's repository or model card. If any attribution here is incomplete or
> incorrect, it is unintentional — please open an issue and it will be fixed.

---

## License

[![CC BY-NC-SA 4.0][cc-by-nc-sa-shield]][cc-by-nc-sa]

The original work in this repository is © Sergio Williams, 2026, and is licensed under a
[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License][cc-by-nc-sa]
(**CC BY-NC-SA 4.0**) — you may share and adapt it for **non-commercial** purposes with
attribution, and must distribute any derivatives under the same license.

Third-party components remain under their respective licenses as listed above. Several
bundled assets and models carry their own terms — notably: Mixamo animations under Adobe's
license; Llama 3.1 under the Llama 3.1 Community License; NVIDIA models under the NVIDIA Open
Model License; Coqui TTS under MPL-2.0; FloodDiffusion under Apache-2.0; PyQt6 under GPL.
Review those before any redistribution or commercial use.

[![CC BY-NC-SA 4.0][cc-by-nc-sa-image]][cc-by-nc-sa]

[cc-by-nc-sa]: http://creativecommons.org/licenses/by-nc-sa/4.0/
[cc-by-nc-sa-image]: https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png
[cc-by-nc-sa-shield]: https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg
