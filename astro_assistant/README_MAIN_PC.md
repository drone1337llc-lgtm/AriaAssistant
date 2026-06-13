# AstroBud — Main / Gaming PC Setup (PC 1)

This PC runs the client side of AstroBud. Because you also have LM Studio installed here,
you can choose which mode to use each session.

---

## Which mode should I use?

```
Do you want to offload AI to your dedicated AI PC (PC 2)?
  ├── YES → Mode B: Thin Client (client.py). PC 2 does all the heavy lifting.
  └── NO  → Mode A: Single PC (main_astro.py). Everything runs right here.
```

Both modes use the same hotkeys, the same config.json, and Jessica's voice. The only
difference is where the LLM inference happens.

---

## Mode A — Single PC (main_astro.py)

Everything runs on this machine: LM Studio, Whisper STT, Jessica TTS, ChromaDB memory,
screen capture, and hotkeys.

### Prerequisites

| What | Where to get it |
|------|-----------------|
| Python 3.11+ | python.org |
| LM Studio 0.3.0+ with server running | lmstudio.ai → Developer tab → Start Server |
| Tesseract OCR | [UB-Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) — install to default path |
| Coqui TTS deps (for Jessica's voice) | Already in your venv — see Jessica TTS section below |

### One-time setup

```powershell
cd "C:\Users\Tench\Documents\AI Learning\astro_assistant"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Load these models in LM Studio before starting:

| Role | Model | Notes |
|------|-------|-------|
| Chat | Lexi-Llama-3-8B-Uncensored | Fast, uncensored — handles routine turns |
| Code | Qwen3-Coder-30B-A3B-Instruct | Fires only when triage detects a real code problem |
| Triage | Qwen2.5-Coder-1.5B-Instruct | Tiny yes/no classifier — runs every scan cycle |
| Vision | NousResearch_Nous-Hermes-2-Vision | Screen understanding |
| Embeddings | nomic-embed-text-v2-moe | Memory search (needed for nightly_memory.py) |

You don't need all five loaded simultaneously. The triage + chat + vision trio covers
90% of usage. Load the code model when you're actively coding.

### Run

```powershell
run.bat
```

Or manually:

```powershell
.venv\Scripts\activate
python main_astro.py
```

On startup, AstroBud prints a smoke test result for the LM Studio server. If a model
isn't loaded, it tries `lms load <model>` automatically (requires `lms` on PATH), then
asks you to load it manually if that fails.

---

## Mode B — Thin Client (client.py)

This PC streams your screen (1 FPS, JPEG) and mic audio to the AI PC over your local
network. The AI PC does all inference, then sends TTS audio back here to play.

No LM Studio, Whisper, or ChromaDB needed on this machine in this mode.

### Prerequisites

- Python + venv (same as Mode A)
- The AI PC (PC 2) must be running `server.py` and reachable on the network

### One-time setup

```powershell
cd "C:\Users\Tench\Documents\AI Learning\astro_assistant"
.venv\Scripts\activate
pip install mss opencv-python numpy sounddevice soundfile scipy websockets keyboard pyautogui
```

Edit `config.json` and set the server URL to PC 2's IP:

```json
"server_url": "ws://192.168.10.2:8765"
```

### Run

```powershell
.venv\Scripts\activate
python client.py
```

Prints `[Client] Connected.` when the AI PC is reachable. Press **Enter** in the terminal
to talk (or use F1 if running as Administrator).

### Network setup (one-time)

You need a direct Ethernet cable between the two PCs, or both on the same LAN.

For a direct cable (fastest, <1ms latency):

1. Plug a Cat 6 cable into both PCs.
2. On each PC: Settings → Network & Internet → Ethernet → adapter properties → IPv4 →
   Use the following IP address:
   - This PC (gaming): `192.168.10.1`, subnet `255.255.255.0`, no gateway
   - AI PC: `192.168.10.2`, subnet `255.255.255.0`, no gateway
3. Test: `ping 192.168.10.2` from this PC — should reply in < 1 ms.

---

## Jessica TTS (XTTS v2)

AstroBud uses your fine-tuned Jessica voice model for speech. The model lives in the
Coqui project folder, and `voice_speak.py` in this project bridges to it.

### Model location

```
C:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\run\training\
    XTTS_v2_Jessica_Voice-June-08-2026_05+55PM-dbf1a08a\
        best_model.pth     ← fine-tuned weights (563 MB)
        config.json        ← inference config
```

### Running the voice standalone

```powershell
cd "C:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-"
python scripts/tts_jessica.py
```

Or from within astro_assistant:

```python
from voice_speak import AstroVoice
voice = AstroVoice()
voice.say("Hey, I found something interesting on your screen.")
```

The model loads on first call (~5–15 seconds). Subsequent calls are fast.

### Voice modes

| Mode | Reference clip |
|------|----------------|
| neutral | jessica_0123.wav |
| enthusiastic | jessica_0187.wav |
| flirty | jessica_0083.wav |
| intimate | jessica_0216.wav |
| calm | jessica_0149.wav |

Switch mode from code: `voice.set_mode("calm")`

### Retraining with ElevenLabs samples

When you have longer ElevenLabs samples ready:
1. Add WAV files to `C:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\data\jessica_voice\wavs\`
2. Update `metadata.csv` with the new entries (format: `filename|text|text`)
3. Run `python scripts/train_jessica_voice.py` from the Coqui folder
4. Update `MODEL_DIR` in `voice_speak.py` to point to the new checkpoint folder

---

## Model routing explained

AstroBud uses three models in a tiered pipeline — you're not paying the cost of the big
model on every screen scan:

```
Every scan cycle (default: every 10s)
  → Qwen2.5-Coder-1.5B (triage): "Is there something worth reacting to?"
      → YES (error/bug/question detected)
          → Lexi-Llama-3-8B (chat): Handle it. If it's a code task...
              → Qwen3-Coder-30B (code): Write/fix the code
      → NO → Silent. Nothing spoken, no VRAM wasted.
```

This means in Reactive mode, the 30B model fires maybe 10% of the time. The rest is the
1.5B triage model doing a quick scan.

### Upgrade options (change in dashboard or config.json)

| Model | Use case |
|-------|----------|
| Qwen3.6-27B-Uncensored-HauhauCS | Better reasoning than 8B, still uncensored — swap as chat_model |
| Qwen2.5-3B-Instruct | Even lighter than 8B — if you need lower VRAM overhead |
| Darwin-28B-Coder | Alternative to Qwen3-Coder-30B for code tasks |
| Qwen3.6-40B-IMatrix | Highest quality; also has vision (mmproj) — needs more VRAM |

---

## Global hotkeys

All combos use **Ctrl+Shift+** to avoid clashing with game keybindings.
**Must run as Administrator for global hooks to work.**

| Keys | Action |
|------|--------|
| Ctrl+Shift+F1 | Summon AstroBud — start a voice turn regardless of mode |
| Ctrl+Shift+F2 | Mute / unmute TTS (Jessica's voice) |
| Ctrl+Shift+F3 | One-shot screen description — print OCR + vision summary |
| Ctrl+Shift+F4 | Flag a bug — capture frame, run auto-triage, save to beta_feedback/ |
| Ctrl+Shift+F5 | Export recent bugs as Markdown — copies to clipboard |

If you don't want to run as Admin, press **Enter** in the terminal to talk instead.

---

## Helpfulness modes

Change in the dashboard (`streamlit run dashboard.py`) or directly in `config.json`.
The main loop reads config on every cycle — changes take effect without restart.

| Mode | Behavior | Best for |
|------|----------|----------|
| Passive (Voice Prompts Only) | Silent until you press Enter / Ctrl+Shift+F1 | Meetings, movies, focused work |
| **Reactive (Watches Errors)** *(default)* | Triage model checks every 10s; speaks only when a real error/bug is detected | Dev and coding — chatty on bugs, silent otherwise |
| Proactive (Scans Constantly) | Full LLM check every N seconds, always responds | Demos, exploration |
| Active Entertainment | Every 20–60s, checks if there's anything interesting to comment on | Gaming, watching video |

---

## Dashboard

```powershell
run_dashboard.bat
```

Opens at `http://localhost:8501`. From here you can:
- Switch models without editing config.json
- Toggle sleep mode, auto-start, auto-load models
- View and export bug logs
- Purge temp files and check storage usage

---

## Nightly memory job (optional)

Sets up a 3 AM Task Scheduler job that compiles the day's interactions into ChromaDB
so AstroBud can remember past sessions.

1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily, 3:00 AM
3. Action: Start a program
   - Program: `.venv\Scripts\python.exe` (full path)
   - Arguments: `"C:\Users\Tench\Documents\AI Learning\astro_assistant\nightly_memory.py"`
4. Make sure LM Studio is running with the embedding model loaded when it fires.
   If not, it skips that night and tries again tomorrow (the log is never corrupted).

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `LM Studio server not reachable` | Developer tab → Start Server. Check port 1234 isn't blocked. |
| Model not loaded on startup | Load it in LM Studio, or enable Auto-load models in the dashboard. |
| Whisper STT silent / no mic | Check mic permissions in Windows Settings → Privacy → Microphone. |
| `pytesseract` crash | Tesseract not installed or wrong path. Install from UB-Mannheim; set `TESSERACT_CMD` in `.env` if path differs. |
| Jessica voice not found | Check `MODEL_DIR` in `voice_speak.py` matches your training checkpoint folder name. |
| Global hotkeys don't fire | Run the script as Administrator (right-click → Run as administrator). |
| `keyboard` import error | `pip install keyboard` then re-run as admin. |
| Client can't reach AI PC | Ping `192.168.10.2`. Check firewall on AI PC (port 8765). |
