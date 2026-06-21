# aria_brain — Aria Brain

Personality, memory, mood, and reflection engine for AriaAssistant.

The Brain is a FastAPI service that owns Aria's "mind": it has the persona prompt,
queries ChromaDB for long-term memory, tracks mood on a 1-5 scale, runs scheduled
reflections, and exposes a tiny HTTP/WebSocket surface for chat clients (tray,
chat window, voice, Telegram).

```
              ┌─────────── aria_brain ───────────┐
              │                                  │
              │  personality  →  prompt builder  │
              │  mood         →  state machine   │
              │  memory       →  ChromaDB        │──→ LM Studio (PC 2 :1010)
              │  reflection   →  APScheduler     │──→ TTS server (PC 1 :5003)
              │  brain        →  LLM orchestrator│──→ ChromaDB server (PC 2 :8000)
              │  server       →  FastAPI         │
              └──────────────────────────────────┘
                       ▲           ▲           ▲
                       │           │           │
                  chat window   tray icon   Telegram
                  (PyQt6)       (pystray)   bot
```

## Quick start

```bash
# 1. Install
cd "C:\Users\Tench\Documents\AI Learning\aria_brain"
uv sync

# 2. Copy env template
copy .env.example .env

# 3. Start the brain
uv run python -m aria_brain.main
# (in another shell, or use the entry point: uv run aria_brain)

# 4. Verify
curl http://127.0.0.1:8770/health

# 5. Chat via REST
curl -X POST http://127.0.0.1:8770/message \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"hey aria, how's it going?\"}"

# 6. Chat via the window (separate process)
uv run python -m aria_brain.chat_window

# 7. Tray icon
uv run python -m aria_brain.tray
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health`         | Liveness + memory stats + mood |
| GET  | `/mood`           | Current mood only |
| POST | `/message`        | Send a text message, get a text reply |
| WS   | `/chat`           | Same as /message but bidirectional streaming |
| POST | `/reflect`        | Force a reflection tick (used by the tray menu) |
| POST | `/shutdown`       | Graceful shutdown |
| POST | `/transcribe-bytes` | Accept raw WAV bytes, return `{text: str}` (Whisper STT) |

## Architecture notes

### Memory
- Three ChromaDB collections: `aria_episodic` (conversations), `aria_facts` (preferences/facts), `aria_thoughts` (reflections)
- Default: HTTP client to `CHROMADB_URL=http://192.168.68.88:8000` (PC 2 server mode)
- Fallback: local DuckDB+Parquet persistent client (PC 1) when PC 2 unreachable — dev keeps working
- Embedding: ChromaDB's default (all-MiniLM-L6-v2, ~80MB, downloads once and caches)

### Mood
- 1-5 scale, JSON-backed at `MOOD_STATE_PATH`
- Decays at `MOOD_DECAY_PER_HOUR` after `MOOD_DECAY_AFTER_HOURS` of silence
- Boosts on positive sentiment, questions; drops on negative sentiment
- "Stuck" moods are corrected lazily on every read (no background timer)

### Reflection
- APScheduler, every `REFLECTION_CADENCE_MINUTES` (default 120)
- Prompt: "It's HH:MM on Day. Mood X.X. What are you thinking?"
- Result stored in `aria_thoughts` collection with timestamp + mood

### Personality
- Strict Aria persona: never breaks character, short punchy sentences, has opinions
- Mood-aware: prompt builder injects current mood label + system context
- The persona lives in `src/aria_brain/personality.py` — edit CAREFULLY

### Phase 3 additions
- `voice.py` — `faster-whisper` STT + push-to-talk (`Ctrl+Shift+Space`)
- `telegram_bot.py` — long-polling bot, env-driven allowlist of chat ids
- `chat_window.py` — PyQt6 chat window with mood indicator
- `tray.py` — `pystray` system tray, right-click menu

## File layout

```
aria_brain/
├── pyproject.toml
├── .env.example
├── README.md
├── smoke_test.py            # module-level smoke
├── smoke_test_server.py     # full FastAPI server smoke
├── setup_chromadb_pc2.ps1   # PC 2 ChromaDB installer (run on PC 2 once)
└── src/aria_brain/
    ├── main.py              # entry point — uvicorn
    ├── config.py            # paths, ports, persona, mood, reflection knobs
    ├── personality.py       # persona prompt + dynamic builder
    ├── mood.py              # mood state machine
    ├── memory.py            # ChromaDB client (sync + async wrappers)
    ├── llm.py               # LM Studio client (async)
    ├── tts.py               # TTS client (async)
    ├── reflection.py        # APScheduler reflection loop
    ├── brain.py             # core orchestrator (handle_message, handle_reflection)
    ├── server.py            # FastAPI app + routes
    ├── chat_window.py       # PyQt6 chat window (process)
    ├── tray.py              # pystray icon (process)
    ├── voice.py             # faster-whisper + push-to-talk
    └── telegram_bot.py      # long-polling bot (process)
```

## What was NOT tested
- Telegram bot needs `TELEGRAM_BOT_TOKEN` from @BotFather before it'll start
- Voice transcription needs `faster-whisper` model download (74MB for `base`, 244MB for `small`)
- Push-to-talk hotkey may need admin privileges on Windows
- AriaBrain is currently using local DuckDB+Parquet fallback — for production set up ChromaDB on PC 2 with `setup_chromadb_pc2.ps1`