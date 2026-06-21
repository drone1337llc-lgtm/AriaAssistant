# PersonaPlex integration — design & plan

Status: **design locked, Phase 1 not yet run.** Grounded in the actual PersonaPlex
source (`moshi/moshi/server.py`, `offline.py`) as of 2026-06-20.

## Goal (user's architecture)

PersonaPlex is the **fast layer**: an always-on, full-duplex speech-to-speech voice
that talks and listens in real time, in **Jessica's voice**. The existing brain is the
**slow/deliberate layer**: it eavesdrops on the live conversation, and when a request
needs a specialist (coder / vision / memory recall) it works in the background while
PersonaPlex keeps the user company, then hands a finished line back for PersonaPlex to
speak. The brain is the conductor; PersonaPlex is the voice.

Crucially: PersonaPlex generates its OWN words by default (that's where the natural
turn-taking/backchannel/interruption behavior comes from). The brain does NOT author
every word — it only **injects a prepared line when a specialist result is ready**, and
otherwise lets PersonaPlex free-run.

## What the source confirms

- **Jessica voice is supported.** `LMGen.load_voice_prompt(path)` accepts a **WAV**
  reference (only `.pt` are pre-baked embeddings). `save_voice_prompt_embeddings=True`
  bakes a WAV into a reusable `Jessica.pt`. We already have clean Jessica reference clips
  from the XTTS clone.
- **Aria's live transcript already streams out.** In `server.handle_chat.opus_loop`,
  each generated text token is sent to the client as `b"\x02" + utf8`. The brain can
  observe Aria's side with zero server changes.
- **Single injection point.** Everything funnels through `tokens = lm_gen.step(codes)`;
  `tokens[0,0,0]` is the agent text token, `tokens[:,1:9]` the agent audio codebooks.
- **Single session.** One `LMGen`, one `asyncio.Lock` — exactly one live conversation.

## Wire protocol (existing)

WebSocket `GET /api/chat?text_prompt=<persona>&voice_prompt=<file>&seed=<n>`
- client → server: `0x01` + Opus(user mic)
- server → client: `0x00` handshake · `0x01` + Opus(Aria voice) · `0x02` + utf8(Aria text)

## The three seams we add

1. **Event-out (no server change for Aria's side).** The app/front-end is the hub: it
   already holds the PersonaPlex WS, so it forwards (a) Aria's `0x02` text and (b) the
   user's mic to the brain. The brain transcribes the user with its existing Whisper
   path → brain now sees BOTH sides of the conversation as text.

2. **Control-in (new `POST /api/control` on the PersonaPlex server).** Small aiohttp
   handler on the same app that mutates shared `LMGen` state under a light lock:
   - `{"action":"hold"}` / `{"action":"resume"}` — stall/allow free generation.
   - `{"action":"relay","text":"<finished specialist line>"}` — enqueue a line to speak.
   A separate HTTP endpoint (not a 2nd WS client) avoids fighting the session lock.

3. **Selective injection (inside `LMGen.step`).** Add `inject_token_queue` + `hold` flag.
   When the queue is non-empty, teacher-force channel-0 (text) with the queued tokens so
   the audio codebooks vocalize the brain's line; when empty, sample normally. `hold`
   biases toward filler/short backchannels while a specialist runs. This is the only
   change that needs `lm.py`/`LMGen` internals — Phase 4.

## Topology

```
mic ─┬─► PersonaPlex WS (voice in)         PersonaPlex (PC2 3090)
     └─► brain /observe (Whisper STT)        ▲  │0x01 audio →► speakers
                                             │  │0x02 text  →► app ─► brain /observe
brain (PC2) ── POST /api/control ────────────┘   (relay / hold / resume)
   │  orchestrator: looks_like_task() + vision triggers (reuse existing routing)
   └─ specialist (nemotron coder / qwen-vl / ChromaDB) ── result ─► /api/control relay
```
Brain↔PersonaPlex control rides a **bridge mesh tunnel** (same mechanism as the other
services). PersonaPlex gets added to the PC2 supervisor + autostart once stable.

## Conductor logic (brain orchestrator)

1. Observe the rolling transcript (user + Aria).
2. On each completed user turn, run `looks_like_task()` / vision triggers.
3. If a specialist is warranted: `POST /api/control hold` (Aria softly stalls: "hang on,
   let me actually look at that"), run the specialist (coder/vision/memory), then
   `POST /api/control relay text=<answer>` and `resume`.
4. Always write the exchange to ChromaDB memory (so memory keeps growing even for the
   free-run chatter).
5. Optionally, refresh the persona/memory `text_prompt` at session start by building it
   from ChromaDB + mood (same `build_system_prompt` we already have, trimmed to a
   PersonaPlex `<system>` blurb).

## Hardware reality

PersonaPlex 7B + 2× Mimi wants ~16–20 GB resident and low latency → it effectively
**owns the 3090 during voice sessions.** The LM Studio specialist models contend, so in
practice voice mode and heavy text/code mode time-share the GPU (acceptable: the
conductor only fires a specialist occasionally, and can evict/reload). Confirm real
latency on the 3090 in Phase 1 before building anything else.

## Phased plan

- **Phase 1 — stand it up + Jessica voice (USER runs; needs GPU + HF).**
  Accept the model license on HF, install, run the server, bake `Jessica.pt`, judge
  latency + quality. Nothing else proceeds until this is good.
- **Phase 2 — design freeze (this doc).** Done.
- **Phase 3 — brain observer.** Brain `/observe` endpoint + Whisper on user audio +
  rolling transcript + memory writes. No injection yet (pure eavesdrop).
- **Phase 4 — control + injection.** Add `POST /api/control` and the `LMGen.step`
  teacher-forcing/hold. Needs `lm.py` internals + the running model to test.
- **Phase 5 — conductor.** Wire `looks_like_task`/vision → hold → specialist → relay.
- **Phase 6 — app + persistence.** Front-end mic routing, mesh tunnel, PC2 supervisor +
  autostart, reconcile with the current XTTS path (PersonaPlex becomes the voice; XTTS
  stays as a fallback / for non-conversational TTS).

## Phase 1 runbook (run on PC2 — the 3090 box)

Runtime decision: **no Docker on PC2 → native Windows venv** (consistent with the existing
brain/TTS venvs). WSL2 + CUDA is the fallback if `sphn`/opus won't install on native
Windows. **Do NOT `pip install moshi` from PyPI** — that is vanilla Kyutai Moshi without
PersonaPlex. Clone the repo and install its local `moshi/` package.

```powershell
# PC2 (the 3090 box), PowerShell. hostname should be AIassistant.

# 0. accept the license in a browser: https://huggingface.co/nvidia/personaplex-7b-v1

# 1. clone the PersonaPlex repo
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
git clone https://github.com/NVIDIA/personaplex.git
cd personaplex

# 2. dedicated venv + CUDA torch (3090 = Ampere → cu121, NOT the cu130 Blackwell note)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install .\moshi            # installs the PersonaPlex fork from the repo subdir

# 3. HF auth (after accepting the license above)
huggingface-cli login         # paste your HF token

# 4. run the server (auto-downloads weights + stock voices on first run; SSL for mic)
$ssl = New-Item -ItemType Directory -Force -Path "$env:TEMP\ppssl"
python -m moshi.server --ssl $ssl.FullName --host 0.0.0.0
#   → open https://<PC2-ip>:8998 in a browser, pick a stock voice, type an Aria persona,
#     and just talk. Judge latency + naturalness on the 3090 FIRST with a stock voice.

# 5. THEN add Jessica: drop a clean ~15s mono jessica.wav into a folder and point at it.
#    load_voice_prompt() accepts a WAV directly — no .pt baking needed for Phase 1.
mkdir voices_aria; copy <jessica_reference>.wav voices_aria\jessica.wav
python -m moshi.server --ssl $ssl.FullName --host 0.0.0.0 --voice-prompt-dir .\voices_aria
#    then request voice_prompt=jessica.wav from the UI/client.
```

If `sphn`/opus fails to install on native Windows → switch to WSL2 (`apt install
libopus-dev`, same pip steps inside WSL with CUDA). Judge: natural? latency tolerable on
the 3090? Jessica's voice present? If yes → Phase 3.
