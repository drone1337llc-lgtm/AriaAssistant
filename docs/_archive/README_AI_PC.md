# AstroBud — AI Server PC Setup (PC 2)

This PC runs the AI pipeline: LM Studio inference, Whisper STT, Jessica TTS, ChromaDB
memory, OCR, and the Streamlit dashboard. PC 1 (your gaming PC) connects to it over the
local network and acts as a thin I/O client.

---

## Role of this machine

```
PC 1 (gaming PC)           →  WebSocket  →  PC 2 (this machine)
  screen frames (1 FPS)                      • Tesseract OCR
  mic audio (on hotkey)                      • LM Studio LLM inference
                                             • Whisper STT
                         ←  WebSocket  ←    • Piper / Jessica TTS
  TTS audio (plays here)                     • ChromaDB memory
```

PC 1 can also run standalone using `main_astro.py` — see `README_MAIN_PC.md`. This
document covers only the server mode (`server.py`).

---

## 1. One-time setup

### 1.1 Python environment

```powershell
cd "C:\Users\Tench\Documents\AI Learning\astro_assistant"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

### 1.2 LM Studio

1. Install [LM Studio 0.3.0+](https://lmstudio.ai/).
2. Load the models listed in Section 2 below.
3. Developer tab → **Start Server** (default: `http://localhost:1234/v1`).

Optional smoke test:

```powershell
curl http://localhost:1234/v1/models
```

### 1.3 Tesseract OCR

Download the 64-bit Windows installer from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
Install to the default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`.

If you install elsewhere, set this in `.env`:

```
TESSERACT_CMD=D:\Tools\Tesseract-OCR\tesseract.exe
```

### 1.4 Piper TTS (fallback voice)

Piper is a lightweight offline TTS used as a fallback when Jessica's XTTS model isn't loaded.

```powershell
pip install piper-tts
```

Download a voice model and its JSON sidecar from [Piper voice releases](https://github.com/rhasspy/piper/releases):
- Recommended: `en_US-lessac-medium.onnx` + `en_US-lessac-medium.onnx.json`

Drop both files into this project folder (or set `PIPER_MODEL` in `.env`).

### 1.5 Jessica TTS (primary voice)

Jessica's XTTS v2 model was trained in the Coqui project folder. The server references
it through `voice_speak.py`. No additional install is needed here — the deps
(torch, TTS) must be in the venv:

```powershell
pip install torch torchaudio
pip install -e "C:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-"
```

Verify:

```powershell
python -c "from voice_speak import AstroVoice; print('OK')"
```

---

## 2. Model load-out

Load these in LM Studio before starting `server.py`. You don't need all five loaded at
once — the triage + chat + vision set covers most sessions.

| Role | config.json key | Model | Size | Notes |
|------|-----------------|-------|------|-------|
| Chat | `chat_model` | Lexi-Llama-3-8B-Uncensored | 4.7 GB | Fast, uncensored; handles routine turns |
| Code | `code_model` | Qwen3-Coder-30B-A3B-Instruct | 23.4 GB | MoE, 3B active params; fires on real code tasks |
| Triage | `triage_model` | Qwen2.5-Coder-1.5B-Instruct | 1.8 GB | Fast yes/no classifier; runs every scan cycle |
| Vision | `vision_model` | NousResearch_Nous-Hermes-2-Vision | 3.8 GB | LLaVA-based screen understanding |
| Embeddings | `embedding_model` | nomic-embed-text-v2-moe | 0.5 GB | Used by nightly_memory.py only |

### Upgrade options

| Model | Use case |
|-------|----------|
| Qwen3.6-27B-Uncensored-HauhauCS | Swap as `chat_model` for better reasoning with more VRAM |
| Qwen2.5-3B-Instruct | Lighter chat alternative |
| Qwen3.6-40B-IMatrix | Highest quality; also supports vision (has mmproj) |
| Darwin-28B-Coder | Alternative to Qwen3-Coder-30B |
| DeepSeek-Coder-V2-Lite | Alternative code model |

Change models in the dashboard or directly in `config.json`. The server re-reads the
config on every loop — no restart needed.

---

## 3. Network setup (one-time)

### Option A — Direct Ethernet cable (recommended, < 1 ms latency)

1. Plug a Cat 6 cable between both PCs.
2. On **this PC**: Settings → Network & Internet → Ethernet → adapter properties → IPv4 →
   Use the following IP address:
   - IP: `192.168.10.2`
   - Subnet: `255.255.255.0`
   - Gateway: *(leave blank)*
3. On **PC 1** (gaming): same steps but IP `192.168.10.1`.
4. Open Windows Firewall for the AstroBud port on **this PC**:

```powershell
New-NetFirewallRule -DisplayName "AstroBud Server" -Direction Inbound `
    -LocalPort 8765 -Protocol TCP -Action Allow
```

5. Test from PC 1: `ping 192.168.10.2` — should reply in under 1 ms.

### Option B — Existing LAN (Wi-Fi or switch)

Skip the static IP setup. Edit `config.json` on PC 1 and set `server_url` to this
machine's LAN IP:

```json
"server_url": "ws://192.168.1.X:8765"
```

Still open port 8765 in the firewall as above.

---

## 4. Running the server

### Start the AI server

```powershell
.venv\Scripts\activate
python server.py
```

On startup it prints a LM Studio connectivity check. The server binds to
`0.0.0.0:8765` and waits for PC 1 to connect. You'll see:

```
[Server] LM Studio reachable. Chat model: Lexi-Llama-3-8B-Uncensored
[Server] Listening on ws://0.0.0.0:8765
```

### Start the dashboard (optional, same machine)

```powershell
streamlit run dashboard.py
```

Access from PC 1's browser at `http://192.168.10.2:8501`. From the dashboard you can
switch models, toggle sleep mode, view bug logs, and manage storage — all without
restarting the server.

### Auto-start on boot (optional)

Schedule `server.py` to run at login using Task Scheduler:

1. Task Scheduler → Create Basic Task
2. Trigger: When the computer starts (or at log on)
3. Action: Start a program
   - Program: `C:\Users\Tench\Documents\AI Learning\astro_assistant\.venv\Scripts\python.exe`
   - Arguments: `"C:\Users\Tench\Documents\AI Learning\astro_assistant\server.py"`
   - Start in: `C:\Users\Tench\Documents\AI Learning\astro_assistant`

---

## 5. Nightly memory job

Compiles the day's interactions into ChromaDB so AstroBud remembers past sessions.
Runs at 3 AM daily via Task Scheduler.

### Setup (run once)

1. Task Scheduler → Create Basic Task
2. Name: `AstroBud NightlyMemory`
3. Trigger: Daily, 3:00 AM
4. Action: Start a program
   - Program: `.venv\Scripts\python.exe` (full path)
   - Arguments: `"C:\Users\Tench\Documents\AI Learning\astro_assistant\nightly_memory.py"`
   - Start in: `C:\Users\Tench\Documents\AI Learning\astro_assistant`
5. Run with highest privileges: Yes

**Requirement:** LM Studio must be open with the embedding model (`nomic-embed-text-v2-moe`)
loaded when the job fires. If it isn't, the job skips that night cleanly — the log is
never corrupted and the same entries will be picked up tomorrow.

---

## 6. Optional: Nightly voice training

Retrains Jessica's voice on new samples and transfers the checkpoint to PC 1.

### Setup (run once)

```powershell
.venv\Scripts\activate
python voice_schedule.py
```

This registers a Task Scheduler job at 3:00 AM daily that:
1. Runs `voice_train.py` (in the Coqui project folder)
2. On success, runs `voice_transfer.py` to push the new checkpoint to PC 1

### Adding ElevenLabs training samples

1. Export WAV clips from ElevenLabs (full sentences / paragraphs — longer is better)
2. Drop them into:
   `C:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\data\jessica_voice\wavs\`
3. Add matching rows to `metadata.csv` (format: `filename|text|text`)
4. The nightly job picks them up automatically

### Manual test run

```powershell
python voice_schedule.py --test
```

### Remove the schedule

```powershell
python voice_schedule.py --remove
```

---

## 7. Latency reference

| Step | Typical time |
|------|-------------|
| Screen capture + compress (PC 1) | 30–50 ms |
| Network transfer (Gigabit Ethernet) | 5–15 ms |
| Tesseract OCR (CPU, this PC) | 50–150 ms |
| Vision model (NousResearch LLaVA) | 200–800 ms |
| LLM reply (Qwen3-Coder-30B, VRAM) | 500–2000 ms |
| Jessica TTS generation | 500–1500 ms |
| Network + playback (PC 1) | 50–100 ms |
| **Total round-trip** | **~1–4 seconds** |

To reduce latency: drop client FPS to 0.5 in the dashboard, or use the 8B chat model
instead of the 30B for most turns (code model only fires when triage detects a code task).

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `LM Studio server not reachable` | Developer tab → Start Server. Confirm port 1234. |
| PC 1 can't connect to server | Check `ping 192.168.10.1` from this PC. Confirm port 8765 is open in Windows Firewall. |
| `pytesseract` crash | Tesseract not installed or wrong path. Set `TESSERACT_CMD` in `.env`. |
| Jessica voice not found | Check `MODEL_DIR` in `voice_speak.py` matches the training checkpoint folder name exactly. |
| Nightly memory skips every night | LM Studio must have the embedding model loaded at 3 AM. Add it to the Auto-load list in the dashboard. |
| Voice training fails | Make sure `metadata.csv` rows match actual wav filenames. Run `python voice_schedule.py --test` to see the error. |
| Dashboard says "Registry error" | Run `streamlit run dashboard.py` as Administrator. |
| Two-PC audio choppy | Switch from Wi-Fi to Ethernet, or reduce `client_jpeg_quality` in config.json. |
