# Aria Assistant — PC 2 (the AI server)

This is the dedicated AI machine. It runs the brain that Aria on PC 1
talks to over the network.

> **Bridge + persistence (2026-06):** PC1 reaches these services through the
> `bridge` mesh tunnels (localhost on PC1 → PC2). Persist the backend with
> `scripts\install-aria-pc2-autostart.ps1` (run elevated here). Provisioning
> notes that matter on this box — SSH admin-key auth, C++ Build Tools,
> `coqui-tts` + `transformers==4.57.*`, chromadb without the `[server]` extra,
> Coqui moved off the USB into the project folder — are all in
> **[docs/BRIDGE_AND_PERSISTENCE.md](docs/BRIDGE_AND_PERSISTENCE.md)**.

PC 2 runs:
- LM Studio (or any OpenAI-compatible server) — the LLM
- The Astro server (`astro_assistant/server.py`) — WebSocket bridge to PC 1
- The Coqui TTS server (`Coqui-TTS-XTTS-v2-/scripts/tts_server_jessica.py`) — Jessica's voice
- The Streamlit dashboard — for switching models + viewing logs
- (Optional) ChromaDB nightly memory job

It does **NOT** run the Godot project — Aria lives on PC 1 only.

## Quick install (recommended)

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
.\install_pc2_ai.ps1
```

The install script handles Python 3.11+ venv, Coqui TTS + Jessica,
optional FloodDiffusion model dir, LM Studio, FFmpeg 8 shared, ALL the
inbound firewall rules PC 1 needs (TTS 5003, motion 8766, dashboard
8501, AstroServer 8765, LM Studio 1010), and a smoke test. Asks before
each external install; idempotent.

The rest of this README is the **detailed manual walkthrough** for users
who want to install by hand or troubleshoot.

```
                PC 2 (this machine)
   ┌─────────────────────────────┐
   │                             │
   │   LM Studio (port 1010)     │
   │       ↑                     │
   │   astro_assistant/server.py │
   │       ↑  WebSocket :8765    │
   │       ↑                     │
   │   tts_server_jessica.py     │
   │       ↑  HTTP :5003         │
   │                             │
   │   Streamlit (port 8501)     │
   │                             │
   └─────────────────────────────┘
            ║  gigabit Ethernet
            ║
            ▽  PC 1 (the desktop where Aria lives)
```

See **[README_PC1.md](README_PC1.md)** for the matching setup on PC 1.

---

## 1. Install system prerequisites (PC 2)

| What | Where | Notes |
|------|-------|-------|
| Windows 10/11 | microsoft.com | Fully updated, rebooted |
| Python 3.10+ (3.12 recommended) | python.org | **Check "Add python.exe to PATH"** |
| Git for Windows | git-scm.com | Optional |
| .NET 8 SDK | dotnet.microsoft.com/download/dotnet/8.0 | The C# build chain (Coqui wheels need it) |
| Visual Studio Build Tools | visualstudio.microsoft.com/visual-cpp-build-tools | Check "Desktop development with C++" |
| **LM Studio 0.3.0+** | lmstudio.ai | The LLM server |
| Tesseract OCR | [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) | 64-bit installer, default path: `C:\Program Files\Tesseract-OCR\` |

PC 2 does **NOT** need Godot. The Godot project lives on PC 1 only.

---

## 2. Place the project

Same as PC 1 — clone or unzip to `C:\Users\Tench\Documents\AriaAssistantApp\`.

---

## 3. Create the venv and install dependencies (PC 2)

```powershell
cd C:\Users\Tench\Documents\AriaAssistantApp
python -m venv .venv
.\.venv\Scripts\Activate.ps1

cd astro_assistant
pip install -r requirements.txt

cd ..\Coqui-TTS-XTTS-v2-
pip install -e .
```

The `pip install -e .` for Coqui is required on PC 2 — it makes the
vendored Coqui repo importable, which is what the TTS server uses.

If `pip install -e .` for Coqui fails, fall back to the PyPI version:
```powershell
pip install TTS
```
Slightly older Coqui build, but everything still works.

---

## 4. Set up LM Studio

### 4.1 Download + load the chat model — Humanish Roleplay (i1 GGUF)

The default chat model is **`mradermacher/Humanish-Roleplay-Llama-3.1-8B-i1-GGUF`**
at Q4_K_M, which is a high-quality **imatrix-calibrated** GGUF of
**`vicgalle/Humanish-Roleplay-Llama-3.1-8B`** — a Llama 3.1 8B DPO
fine-tune designed to be "humanish" (avoids AI assistant slop,
writes more like a real human, supports roleplay action formatting).

**Why this exact repo and quant:**
- The **vicgalle** model is DPO-tuned for "humanish" personality
- The **mradermacher i1 GGUF** is the imatrix quant — slightly better
  quality than the standard Q4_K_M at the same ~4.92 GB file size
- The **Apache-2.0 license** allows full commercial use with no
  restrictions (no MAU cap, no usage limits) — the most permissive
  license tier available for an 8B roleplay model
- The local download is **free** — don't use the Featherless AI hosted
  inference route, that's a paid subscription

**In LM Studio:**
1. Click the **Search** icon (magnifying glass)
2. Type `mradermacher/Humanish-Roleplay-Llama-3.1-8B-i1-GGUF`
3. Pick the **i1-Q4_K_M** file (the "i1" denotes imatrix calibration)
4. Click **Download** (~4.92 GB)
5. When the download finishes, click the model card → **Load Model**
6. Wait for it to finish loading into VRAM (~10-30 seconds)

> **Filename in LM Studio:** the loaded model reports its filename as
> the `model` parameter sent in the API call. The default `config.json`
> already expects `Humanish-Roleplay-Llama-3.1-8B.i1-Q4_K_M` — if your
> filename is different, edit `astro_assistant/config.json` line 4
> (`"chat_model": ...`) to match.

The first load is slow (the 5 GB model file is read from disk into
VRAM). After that, the model is cached and loads in seconds.

> ⚠️ **Content note:** Humanish was trained on `NSFW_RP_Format_DPO`
> and unfiltered Claude Opus data. The base model can drift into
> romantic/RP mode. The system prompt in `LLMBridge.cs` keeps Aria
> on track, but if you want hard content guardrails, add them
> explicitly to the system prompt.

### 4.2 Bind the server to all interfaces

In LM Studio → **Developer** tab → settings:
- **Bind address**: `0.0.0.0` (NOT `localhost` — PC 1 needs to reach this)
- **Port**: `1010` (or whatever `config.json` says)

Click **Start Server**.

### 4.3 Smoke test

```powershell
curl http://localhost:1010/v1/models
```
You should get JSON listing the loaded model. If you used a different
port, use that.

---

## 5. Configure the Astro server (PC 2)

```powershell
cd C:\Users\Tench\Documents\AriaAssistantApp\astro_assistant
copy .env.example .env
```

Edit `config.json`:

```json
{
  "lmstudio_url": "http://0.0.0.0:1010/v1",
  "server_bind":  "0.0.0.0",
  "server_port":  8765
}
```

`0.0.0.0` makes the server listen on **all network interfaces** — what
you want for cross-PC communication. `localhost` would only accept
local connections.

`server_port: 8765` is the default. PC 1's `config.json` must match.

---

## 6. Set up the network (one-time)

### 6.1 Allow inbound port 8765 in Windows Firewall

```powershell
# Run as Administrator on PC 2
New-NetFirewallRule -DisplayName "AstroBud Server" -Direction Inbound `
    -LocalPort 8765 -Protocol TCP -Action Allow
```

If you change the server port in `config.json`, change `8765` in the
command above too.

### 6.2 Network choice

**Pick one:**

#### Option A — Direct Ethernet cable (recommended, <1 ms latency)

1. Plug a Cat 6 cable between the two PCs
2. On **PC 2** (this machine): Settings → Network & Internet → Ethernet
   → adapter properties → IPv4 → "Use the following IP address":
   - IP: `192.168.10.2`
   - Subnet: `255.255.255.0`
   - Gateway: *(leave blank)*
3. On **PC 1**: same steps but IP `192.168.10.1`
4. PC 1's `config.json` uses `192.168.10.2` for `server_url` and
   `lmstudio_url` (this is the default in the README)
5. Test from PC 1: `ping 192.168.10.2` → should reply in <1 ms

#### Option B — Existing LAN (Wi-Fi or switch)

Skip the static IP setup. Use whatever IPs DHCP assigns. Edit PC 1's
`config.json` and put PC 2's actual LAN IP in:
```json
{
  "server_url":   "http://192.168.1.X:8765",
  "lmstudio_url": "http://192.168.1.X:1010/v1"
}
```

The firewall rule (Section 6.1) still applies.

---

## 7. Start the AI server (PC 2)

```powershell
cd C:\Users\Tench\Documents\AriaAssistantApp
.\start_aria_server.ps1
```

This opens two PowerShell windows:
- **Astro server** — `python server.py` listening on `0.0.0.0:8765`
- **Dashboard** — Streamlit on `http://localhost:8501`

You can access the dashboard from PC 1's browser at
`http://192.168.10.2:8501` (or whatever PC 2's IP is) to switch
models, see logs, etc.

**Make sure LM Studio is running on PC 2 with at least the chat model
loaded.** The server refuses to start otherwise.

---

## 8. Day-to-day

1. Boot PC 2 first, start LM Studio, run `start_aria_server.ps1`
2. Boot PC 1, run `start_aria.ps1`
3. Aria appears on PC 1's desktop
4. Talk to her / right-click her / let her roam — or use the **💬 Chat with Aria** panel in this dashboard (the dashboard POSTs to PC 1's chat server on port 8767, which routes into the same LLM/animation pipeline)
5. When done: close Godot on PC 1, then stop `start_aria_server.ps1` on PC 2

If PC 2 goes down, Aria on PC 1 keeps running — she just falls back
to no-LLM responses (scripted lines) until PC 2 comes back.

### 8.1 Chat with Aria from the dashboard

The Streamlit dashboard has a top-of-page **💬 Chat with Aria (PC 1)**
expander. Type a message, press Send (or Ctrl+Enter in the text area),
and Aria responds — speech bubble, voice, body animation, all of it.

This goes via a small HTTP server embedded in Aria's Godot app
(`AriaChatServer.cs`, listens on port 8767). The dashboard POSTs
`{"text": "..."}` to `http://<PC 1 LAN IP>:8767/chat`. The Godot
app forwards the text into `LLMBridge.SendMessage`, which is the same
path that right-clicks and F2 input use.

The `start_aria.ps1` script on PC 1 auto-creates a Windows firewall
rule (`AriaChatServer-PC1-8767`) to allow inbound TCP 8767 from the
LAN. If the rule fails (group policy), the script prints the
one-line `netsh` fix you can run manually.

---

## 9. Optional: nightlies

### 9.1 Nightly memory aggregation

A 3 AM Task Scheduler job that compiles the day's interactions into
ChromaDB so Aria remembers past sessions. Inside `astro_assistant/`:

```powershell
python voice_schedule.py
```

Or set it up manually in Task Scheduler:
- Program: `C:\Users\Tench\Documents\AriaAssistantApp\.venv\Scripts\python.exe`
- Arguments: `voice_schedule.py` (with the right working dir)
- Trigger: Daily, 3:00 AM

LM Studio must be open with the embedding model loaded at 3 AM, or
the job skips that night cleanly (no corrupted logs).

### 9.2 Nightly voice retrain

(Only if you have new ElevenLabs samples to train on.)

```powershell
cd C:\Users\Tench\Documents\AriaAssistantApp\astro_assistant
python voice_schedule.py    # registers the schedule
python voice_schedule.py --test    # manual test run
```

---

## 10. Optional: FloodDiffusion motion server

This section is for the `AriaAssistantAppIKdiffusion` build (a derivative
of the main project with the procedural-IK + motion-diffusion stack).
Skip it if you're running the plain `AriaAssistantApp`.

The motion server lets Aria request **new animation clips on demand**
from the LLM. When the brain decides a needed motion isn't in the baked
Mixamo library, it sends a `request_motion` directive with a text
prompt; the server generates the clip, retargets it to Aria's Mixamo
rig, and the Godot client auto-installs it into the AnimationLibrary.

**Architecture:**
```
   PC 1 (Godot)                    PC 2 (this machine)
                                    
   AriaMotionClient  ───HTTP───►   motion_server.py
   (enqueues, polls)               (FloodDiffusion inference)
                                    
              ◄──── JSON motion ────  (per-bone rotation timeline)
```

### 10.1 Install FloodDiffusion dependencies

In the same venv (or a new one — your choice):

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\astro_assistant
pip install -r motion_requirements.txt
```

The full model (`ShandaAI/FloodDiffusion`, ~16 GB VRAM) is the default.
For an 8 GB card (e.g. RTX 3060), use the tiny version:

```powershell
# Pre-download the tiny model weights so the server is ready to go
huggingface-cli download ShandaAI/FloodDiffusionTiny
```

The server auto-detects which one you have. Override at startup with
`--model ShandaAI/FloodDiffusion` or `--model ShandaAI/FloodDiffusionTiny`.

> **Memory note:** FloodDiffusion holds a CUDA context and concurrent
> inference is OOM-prone, so the server runs **ONE generation at a time**
> and queues the rest in FIFO order. The queue is capped at 100 — anything
> beyond returns HTTP 429 to the client (the Godot side logs it as a
> `MotionFailed` and tells the LLM the queue is full).

### 10.2 Allow inbound port 8766 in Windows Firewall

The motion server binds to **port 8766** (8765 is the Astro server, 8766
keeps them separate). Add a firewall rule:

```powershell
# Run as Administrator on PC 2
New-NetFirewallRule -DisplayName "FloodDiffusion Motion Server" -Direction Inbound `
    -LocalPort 8766 -Protocol TCP -Action Allow
```

### 10.3 Start it

The motion server auto-starts with `start_aria_server.ps1`. To start it
manually:

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\astro_assistant
python motion_server.py --port 8766 --capacity 100
```

Useful flags:
- `--model ShandaAI/FloodDiffusionTiny`  (8 GB VRAM)
- `--preload`                            (load the model at startup, not on first request)
- `--capacity 200`                       (bigger queue, if you have the VRAM headroom)
- `--fps 30`                             (output frame rate, default 30)
- `--bind 0.0.0.0`                       (default, don't change)
- `--log-level DEBUG`                    (verbose)

To **skip the motion server** at startup, use `start_aria_server.ps1 -NoMotion`.

### 10.4 Verify it's working

From PC 1 (or any machine on the LAN):

```powershell
curl http://192.168.10.2:8766/healthz
# {"ok": true, "model_loaded": true}      ← after first request
# {"ok": true, "model_loaded": false}     ← before first request

curl http://192.168.10.2:8766/motion/cap
# {"capacity": 100, "depth": 0, "running": null, "next_id": null}
```

Enqueue a test request:

```powershell
$body = '{"prompt": "Aria waves from the hip with a big smile", "frames": 60, "suggested_name": "wave_hip"}'
curl -X POST http://192.168.10.2:8766/motion -H "Content-Type: application/json" -d $body
# {"id": "a1b2c3d4e5f6", "position": 1, "queue_depth": 1}
```

Poll for status:

```powershell
curl -X POST http://192.168.10.2:8766/motion/status -H "Content-Type: application/json" -d '{"ids":["a1b2c3d4e5f6"]}'
# {"results": [{"id": "a1b2c3d4e5f6", "status": "pending|running|done|failed", ...}]}
```

When `status` becomes `done`, the Godot client fetches `/motion/get?id=…`
and installs the clip. You can see the install in the Godot output panel:
`[Motion] installed 'wave_hip' (60 frames @ 30 fps, 22 bone tracks)`.

### 10.5 How the LLM uses it

The brain knows about motion generation through the `request_motion`
directive. With `AriaAssistantAppIKdiffusion` running on PC 1, try:

> "Aria, teach yourself to do a happy spin with arms out"

She should respond with something like:

```json
{
  "say": "Give me a sec to learn that.",
  "emotion": "fun",
  "action": "none",
  "move": "stay",
  "directives": [
    {"action": "request_motion",
     "prompt": "Aria does a happy spin with arms out",
     "frames": 80,
     "name": "spin_happy"}
  ]
}
```

The clip takes 5–60 seconds to generate (depending on the model size
and GPU). When it arrives, it's auto-baked into the AnimationLibrary
and becomes a regular gesture she can use.

### 10.6 Queue + cap behaviour

- **Cap 100** (configurable via `--capacity N`).
- Beyond the cap, new requests get `HTTP 429` and the Godot client
  surfaces the error to the LLM via a `MotionFailed` signal. The LLM
  can react ("the queue is full, try later") instead of silently dropping.
- The LLM's WorldState payload includes `motion_queue_depth` and
  `motion_queue_capacity` on every turn, so the brain sees the queue
  state without polling.
- **Don't queue more than 5 `request_motion` directives in a single
  reply** — the system prompt enforces this, but if you build custom
  tooling, respect it.

### 10.7 Skeleton retarget quality

FloodDiffusion outputs SMPL 22-joint positions; Aria uses a Mixamo
52-bone skeleton. The Godot client (the `MotionRetargeter` class in
`aria/scripts/MotionRetargeter.cs`) does an **IK-based retarget** on
the Mixamo rig using the same FABRIK solver the live IK controller
uses. For each frame, it:

1. Reads the per-chain joint positions in Aria's world space
2. Runs FABRIK for spine / both arms / both legs to match the SMPL
   tip positions
3. Writes the resulting bone rotations to the AnimationLibrary as a
   real Godot clip

The retarget preserves Aria's specific body proportions, so the
generated motion looks like HER moving, not a different character.
The Python server also ships a legacy rotation-only retarget as a
fallback (`bones` field) in case the IK retarget fails on the client.

### 10.8 Stress test the queue

`astro_assistant/motion_stress_test.py` hammers the server with N
requests and verifies:
- The cap is honored (N-cap rejected with HTTP 429)
- Only one job runs at a time (FIFO single-worker)
- The queue drains monotonically
- Final depth = 0

Useful when changing the queue code, the worker, or the cap logic:

```powershell
# Start the server in mock mode (no GPU needed, fast, fake motions)
python motion_server.py --port 18765 --mock --capacity 5

# In another shell, fire 8 requests against the cap-of-5
python motion_stress_test.py --url http://127.0.0.1:18765 --n 8 --cap 5 --drain-timeout 15
# Expected:
#   [OK] queue-cap honored (expected 3 rejections, got 3)
#   [OK] single-job semantic maintained (never > 1 running)
#   [OK] depth monotonically decreased (or plateaued)
#   [OK] final depth = 0
#   === ALL STRESS CHECKS PASSED ===
```

---

## Troubleshooting

### PC 1 can't reach PC 2

From PC 1, in order:
```powershell
ping 192.168.10.2
Test-NetConnection 192.168.10.2 -Port 8765
curl http://192.168.10.2:1010/v1/models
```

- `ping` fails → cable / IP config problem. Re-check Section 6.2.
- `ping` OK, port test fails → firewall on PC 2 (Section 6.1).
- Port OK, `curl` fails → LM Studio not running, or not bound to `0.0.0.0`
  (Section 4.2).

### "WebSocket connection failed"
`server_bind` in `config.json` is `localhost` instead of `0.0.0.0`. Fix
to `0.0.0.0` and restart the server.

### Client connects then disconnects
PC 2's Astro server probably crashed. Check its PowerShell window.
Common cause: LM Studio went down — restart LM Studio, the server
reconnects on the next client request.

### Latency is 5+ seconds per response
1. In LM Studio, switch from 27B to 8B for chit-chat. Save 30B for code.
2. Increase `scan_interval` in `config.json` (e.g. `30` instead of `15`).
3. Wi-Fi → Ethernet if you haven't already. Even 50 ms of Wi-Fi
   jitter compounds.

### TTS server unreachable
The Coqui TTS server isn't running on PC 2. PC 1's Astro client falls
back to silent output. Start it manually:
```powershell
cd C:\Users\Tench\Documents\AriaAssistantApp\Coqui-TTS-XTTS-v2-\scripts
python tts_server_jessica.py
```

### "Out of VRAM" on PC 2
XTTS + LM Studio chat + 30B code = ~25 GB VRAM. Your GPU has to be
bigger than that, or unload models. In the Streamlit dashboard, mark
which models auto-load at startup so LM Studio doesn't load them all.

### Jessica voice silent
Probably the XTTS model path. Default:
`Coqui-TTS-XTTS-v2-/run/training/XTTS_v2_Jessica_Voice-June-08-2026_05+55PM-dbf1a08a`
If you've retrained and the folder name is different, either rename
the folder or set `XTTS_MODEL_DIR` in `.env` to the new path.

### Server start_aria_server.ps1 complains "no .venv"
You didn't run `python -m venv .venv` yet. See Section 3.
