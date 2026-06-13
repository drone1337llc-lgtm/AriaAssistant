# 🤖 AstroBud — Local Desktop AI Assistant

A fully-offline, screen-aware, voice-driven AI helper for your Windows desktop.
Persona: a cheerful, productivity-obsessed little robot who lives in your system
tray, watches your screen, remembers what you worked on, and speaks to you in
`*bloop*` chirps and mechanical `*whir*`s.

> **Runtime:** LM Studio (replaces the original spec's Ollama). Talks to
> LM Studio's OpenAI-compatible server on `localhost:1234`.

---

## What you get

| File | What it does |
|---|---|
| `main_astro.py` | Daytime engine. Listens to your mic, watches your screen, talks back. |
| `server.py` | Two-PC mode — runs the AI pipeline on PC 2, accepts WebSocket clients. |
| `client.py` | Two-PC mode — runs on PC 1, streams screen + mic, plays TTS. |
| `transport.py` | Shared WebSocket message protocol for client ↔ server. |
| `nightly_memory.py` | 3 AM job. Embeds the day's interactions into ChromaDB and clears the log. |
| `dashboard.py` | Streamlit control panel at `http://localhost:8501`. |
| `hotkeys.py` | Global hotkey handler (F1/F2/F3) with TTS mute state. |
| `cleanup.py` | Wipes temp files + runs `gc.collect()`. |
| `storage_watchdog.py` | Auto-purges old media if the project folder > 500 MB. |
| `lmstudio_client.py` | Tiny wrapper around `openai.OpenAI` for LM Studio. |
| `tools.py` | OpenAI-standard tool schemas + tool execution. |

---

## 1. One-time setup

### 1.1 LM Studio
1. Install [LM Studio](https://lmstudio.ai/) (0.3.0+ recommended; older versions
   may not have the `lms` CLI).
2. In LM Studio, download or load the models you want. The roster that fits
   your hardware is in `config.json`:
   - **Chat brain:** `Lexi-Llama-3-8B-Uncensored` (Q4_K_M, 4.7 GB) — fits in 16 GB VRAM.
   - **Code brain:** `Qwen3-Coder-30B-A3B-Instruct` (Q6_K, 24 GB) — MoE, 3B active params.
   - **Triage / fast classifier:** `Qwen2.5-Coder-1.5B-Instruct` — small, fast YES/NO.
   - **Vision:** `NousResearch_Nous-Hermes-2-Vision` (LLaVA-based, with mmproj).
   - **Embeddings:** `nomic-embed-text-v2-moe` (Q8_0, 488 MB).
3. Open the **Developer** tab and click **Start Server**. Default URL:
   `http://localhost:1234/v1`.
4. (Optional) Test from a terminal:
   ```powershell
   curl http://localhost:1234/v1/models
   ```

### 1.2 Tesseract OCR
AstroBud uses Tesseract for fast CPU-side text extraction from your screen.
- Download: <https://github.com/UB-Mannheim/tesseract/wiki> (use the 64-bit
  Windows installer).
- Default install path: `C:\Program Files\Tesseract-OCR\tesseract.exe`. If you
  install it elsewhere, set `TESSERACT_CMD` in your `.env`.

### 1.3 Piper TTS voice
Piper is used for offline neural text-to-speech.
1. `pip install piper-tts` (puts `piper` on your PATH).
2. Download a voice from the [Piper voice library](https://github.com/rhasspy/piper/releases)
   — recommended: `en_US-lessac-medium.onnx` and its `.onnx.json` sidecar.
3. Drop both files into this project folder (or update `PIPER_MODEL` in
   `tools.py`).

### 1.4 Python deps
```powershell
cd "C:\Users\Tench\Documents\AI Learning\astro_assistant"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

The first run of `main_astro.py` will download the Whisper `base` model
(~140 MB) and cache it in `~/.cache/whisper/`.

### 1.5 .env (optional)
```powershell
copy .env.example .env
```
Edit `.env` if your LM Studio server runs on a different port or you need to
point at a custom Tesseract path.

---

## 2. Running it

### Daytime engine
```powershell
run.bat
```
Or directly:
```powershell
.venv\Scripts\activate
python main_astro.py
```

The script prints a smoke test of the LM Studio server on startup. If the
chat model isn't currently loaded, it tries `lms load <model>` (if the
`lms` CLI is on your PATH) and otherwise asks you to load it manually.

### Dashboard
```powershell
run_dashboard.bat
```
Or:
```powershell
streamlit run dashboard.py
```
Opens at `http://localhost:8501`. Tweak models, sleep mode, helpfulness
level, scan interval, and storage cap from the UI. The daytime engine reads
`config.json` on every loop, so changes take effect without restart.

### Nightly memory job
Schedule it once via **Task Scheduler**:
- **Trigger:** Daily, 3:00 AM
- **Action:** Start a program
  - Program: `C:\Users\Tench\Documents\AI Learning\astro_assistant\.venv\Scripts\python.exe`
    (or just `python` if you don't use a venv)
  - Arguments: `"C:\Users\Tench\Documents\AI Learning\astro_assistant\nightly_memory.py"`

Before it runs, make sure LM Studio is open with the embedding model loaded.
If the embedding model isn't loaded when the job fires, it'll skip that
night's compile (it never corrupts the log — it'll just retry tomorrow).

---

## 3. Two-PC setup (PC 1 client → PC 2 AI server)

If your gaming PC can't spare the CPU/GPU for an AI assistant, run the AI
on a second PC. Your gaming machine becomes a thin **client** that ships
screen frames and mic audio over the local network and plays whatever TTS
comes back.

```
┌─────────────────────┐         ┌──────────────────────┐
│   PC 1 (gaming)     │         │   PC 2 (AI server)   │
│                     │         │                      │
│  python client.py   │ ──net──►│  python server.py    │
│  • screen capture   │         │  • LM Studio (LLM)   │
│  • mic capture      │         │  • vision + Whisper  │
│  • TTS playback     │ ◄────── │  • Piper TTS         │
│  • pyautogui typing │         │  • ChromaDB memory   │
│  • media keys       │         │  • Streamlit UI      │
└─────────────────────┘         └──────────────────────┘
```

### 3.1 Network setup (one-time)

1. **Plug a Cat 6 Ethernet cable into both PCs.** A 3–5 m cable is ~$8.
   (Wi-Fi works too but adds latency; direct Ethernet is the cleanest.)
2. **Set static IPs on both PCs** so they always find each other:
   - PC 1 (gaming): `192.168.10.1`, subnet `255.255.255.0`, no gateway
   - PC 2 (AI server): `192.168.10.2`, subnet `255.255.255.0`, no gateway
   - On Windows: Settings → Network & Internet → Ethernet → adapter
     properties → IPv4 → "Use the following IP address"
3. **Allow the AstroBud port** through Windows Firewall on PC 2:
   ```powershell
   New-NetFirewallRule -DisplayName "AstroBud Server" -Direction Inbound `
       -LocalPort 8765 -Protocol TCP -Action Allow
   ```
4. **Test the link** from PC 1's terminal:
   ```powershell
   ping 192.168.10.2
   ```
   You should see sub-millisecond round-trip times.

### 3.2 PC 2 setup (the AI server)

The same AstroBud project lives on PC 2, plus a few extras:

1. Install Python deps (same `requirements.txt` as before).
2. Install **Tesseract OCR** (path: `C:\Program Files\Tesseract-OCR\tesseract.exe`).
3. Install **Piper TTS** and drop the voice ONNX file into the project folder.
4. **Edit `config.json`** on PC 2:
   - Leave `server_url`, `server_port`, etc. as-is (default 8765 is fine).
5. Open LM Studio, load the chat / vision / embedding models, and start the
   local server (Developer tab → Start Server).
6. Run the AstroBud server:
   ```powershell
   python server.py
   ```
   It binds to `0.0.0.0:8765` and prints a LM Studio connectivity check.
7. (Optional) Run the Streamlit dashboard:
   ```powershell
   streamlit run dashboard.py
   ```
   Access it from PC 1's browser at `http://192.168.10.2:8501`.
8. **Schedule server.py to auto-start** with Task Scheduler (same pattern as
   the nightly job, just trigger on boot instead of 3 AM).

### 3.3 PC 1 setup (the client)

1. Copy just these files from the project to PC 1:
   - `client.py`
   - `transport.py`
   - `config.json` (and edit the `server_url` to match PC 2's IP)
   - `requirements.txt`
2. Install PC 1's smaller dep set:
   ```powershell
   pip install mss opencv-python numpy sounddevice soundfile scipy websockets keyboard pyautogui
   ```
   (You do **not** need LM Studio, Whisper, Piper, ChromaDB, Tesseract, or
   PyTorch on PC 1 — the client is a thin I/O pipe.)
3. **Edit `config.json`** on PC 1:
   ```json
   "server_url": "ws://192.168.10.2:8765"
   ```
4. Run the client:
   ```powershell
   python client.py
   ```
   It connects, prints `[Client] Connected.`, and starts streaming 1 FPS
   of screen frames to PC 2.
5. Press **F1** to talk (needs Admin on Windows for global hotkeys), or
   just press **Enter** in the client terminal.

### 3.4 Latency expectations

| Step | Time |
|---|---|
| Screen capture + JPEG compress (PC 1) | 30–50 ms |
| Network send (gigabit Ethernet) | 5–15 ms |
| Vision model (LLaVA / Hermes on PC 2) | 200–800 ms |
| LLM reply (Qwen3-Coder 30B Q6_K, fully VRAM) | 500–2000 ms |
| Piper TTS generation (PC 2) | 150–400 ms |
| Network receive + audio playback (PC 1) | 50–100 ms |
| **Total** | **~1–3 seconds** |

Plenty fast for "Astro, what does this error mean?" Tight enough for
entertainment-mode commentary at 30 s intervals. If you need faster, drop
the client FPS to 0.5 in the dashboard or switch the entertainment persona
to use the 1.5B triage model for routine checks.

### 3.5 Falling back to single-PC

If something goes wrong, you can always run `python main_astro.py` on
either machine — it doesn't use the network at all. Same project, same
config. Single-PC and two-PC are independent code paths.

---

## 4. Tool use

AstroBud can call these local tools (OpenAI-standard `tools` parameter — no
fragile JSON-blob parsing):

| Tool | Args | What it does |
|---|---|---|
| `open_application` | `app_name` | Launches Notepad / Calculator / Chrome / CMD / etc. |
| `control_media_volume` | `action` | mute / unmute / up / down (via pycaw). |
| `set_volume` | `level` (0–100) | Set Windows master volume to a specific percentage. |
| `play_pause_media` | — | Toggle media play/pause in the active player. |
| `next_track` / `previous_track` | — | Skip tracks in the active player. |
| `check_system_resources` | — | Reads CPU + RAM utilization. |
| `execute_and_verify_code` | `code_snippet` | Runs Python in a 5-second sandbox, returns stdout/stderr. |
| `type_code_to_ide` | `code_to_type` | Warns you, waits 3s, types into the active window. |
| `take_screenshot_to_clipboard` | — | Copies the primary monitor to the Windows clipboard. |
| `get_active_window_title` | — | Returns the title of the currently focused window. |

Add a new tool by writing the function in `tools.py`, registering it in
`TOOL_REGISTRY`, and adding its OpenAI schema in `get_all_tool_schemas()`.

---

## 5. Helpfulness modes

| Mode | Behavior | Best for |
|---|---|---|
| **Passive (Voice Prompts Only)** | Silent until you press Enter to speak (or F1 hotkey). | Movies, meetings, when you want full control. |
| **Reactive (Watches Errors)** *(default)* | Every 10s, runs a tiny triage model. Only the 30B code brain fires when the screen shows a real error. | Dev/coding work — chatty on bugs, silent otherwise. |
| **Proactive (Scans Constantly)** | Every N seconds, always asks the LLM. | Demos, exploration, when you want constant commentary. |
| **Active Entertainment (Co-pilot for Media/Games)** | Every 20–60s (configurable), the LLM gets full visual + OCR context and decides whether to chime in. Replies with `SKIP` if nothing's interesting. Uses a warmer, more conversational persona. | Watching a movie, playing a game — proactive but polite. |

Toggle between modes in the dashboard; the main loop re-reads `config.json` on
every cycle so changes take effect immediately.

---

## 6. Global hotkeys

All hotkeys use `Ctrl+Shift+` modifiers specifically to avoid colliding with
in-game bindings (which usually own bare F-keys) and OS shortcuts. The combo
passes through to the active application too — the game still sees the
keystrokes, AstroBud also fires.

| Key | Action | Notes |
|---|---|---|
| **Ctrl+Shift+F1** | Summon AstroBud | Runs a full voice turn, no matter what mode is active. |
| **Ctrl+Shift+F2** | Mute / unmute TTS | Silences AstroBud's voice without stopping the engine. |
| **Ctrl+Shift+F3** | One-shot screen description | Prints the current screen OCR + vision summary. |
| **Ctrl+Shift+F4** | Flag current screen as a bug | Captures a high-quality frame, runs OCR, the small triage model auto-categorizes + describes, entry is written to `beta_feedback/bugs.jsonl` with the PNG in `beta_feedback/screens/`. Designed for open-world RPG beta testing — press it the instant you see a glitch. |
| **Ctrl+Shift+F5** | Export recent bugs as Markdown | Exports the last N bug entries to `beta_feedback/exports/bugs_YYYYMMDD_HHMMSS_NN.md` and copies the rendered text to the clipboard so you can paste directly into your bug tracker. |

### Auto-triage on Ctrl+Shift+F4

When you flag a bug, the small triage model (Qwen2.5-Coder-1.5B by default)
gets the OCR text + visual context and returns a JSON object with:

```json
{
  "category": "Visual Glitch",   // or Audio Issue, Quest Bug, Performance, UI/Layout, Text/Localization, Combat, World/Environment, Other
  "description": "Texture flickering on the cliff face near the river crossing"
}
```

Both fields are stored on the bug entry and read back to you out loud so you
hear the triage result without looking at the dashboard. You can disable
auto-triage via `triage_enabled: false` in `config.json` (the F4 hotkey
still works — it just won't auto-categorize).

### Export (Ctrl+Shift+F5)

Generates a Markdown file like:

```markdown
# Bug Report Export — 2026-06-06 19:15

## bug_1749142000_1234 — 2026-06-06 19:14:32
- **Category:** Visual Glitch
- **Description:** Texture flickering on the cliff face near the river crossing
- **Active window:** `Honor of Kings: World`
- **Frame:** `screens/bug_1749142000_1234.png`
- **OCR text:**
  ```
  ...
  ```
- **Vision context:** A cliff face near a river crossing. The rocks show...

---
```

You can also export as JSON or CSV (for spreadsheet-based trackers). The
default count is the last 10 entries; change via `export_last_n` in
`config.json` or the dashboard.

Hotkeys are registered system-wide via the `keyboard` library. On Windows,
**the script must be run as Administrator** for global hotkeys to work
(Windows security default). If you don't want to run as admin, the
hotkeys are a no-op and you can still talk by pressing Enter in the terminal.

---

## 7. Hardware guards (recommended for gaming + coding)

- Cap game/engine FPS to 60–120 to leave VRAM headroom for the vision model.
- Pin Python processes to E-cores if your CPU has hybrid P/E cores (Task
  Manager → Details → right-click → Set affinity).
- Move your mouse to any screen corner to abort `pyautogui` typing
  (`pyautogui.FAILSAFE` is on).
- The auto-typing macro gives you a 3-second vocal countdown so you can click
  into your editor first.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `LM Studio server not reachable` | Open LM Studio → Developer tab → Start Server. |
| `Model 'X' is not loaded` | Load it in LM Studio, or enable *Auto-load models* in the dashboard. |
| Whisper STT is silent | Check mic permissions; verify `sounddevice` can see your input device. |
| pytesseract fails | Install Tesseract and either keep it at the default path or set `TESSERACT_CMD`. |
| Piper can't find the voice | Drop `en_US-lessac-medium.onnx` + `.onnx.json` into this folder, or update `PIPER_MODEL` in `tools.py`. |
| Dashboard says "Registry error" on auto-start | Run Streamlit as Administrator, or set the registry key manually. |
| Global hotkeys don't fire | Run the script as Administrator, or skip them and use Enter in the terminal. |
| `keyboard` import fails on non-Windows | That's fine — hotkeys are Windows-only and AstroBud still works. |

---

## 9. License

Personal project. Use freely.
