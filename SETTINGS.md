# Aria — Settings Reference

Every knob in the Aria stack, where it lives, what it controls, and the default.

---

## 1. Aria Brain (`brain/`)

Personality, mood, memory, reflection, voice, Telegram — the "mind" of Aria.

### `brain/.env`
| Variable | Default | What it does |
|---|---|---|
| `LM_STUDIO_BASE_URL` | `http://192.168.68.88:1010/v1` | LM Studio OpenAI-compatible endpoint |
| `LM_STUDIO_API_KEY` | `lm-studio` | Auth header (LM Studio doesn't check, any string works) |
| `LM_STUDIO_CHAT_MODEL` | `humanish-roleplay-llama-3.1-8b-i1` | Aria's conversational voice |
| `LM_STUDIO_PARSER_MODEL` | `qwen2.5-3b-instruct` | Fast, structured-output calls |
| `LM_STUDIO_CODER_MODEL` | `qwen3.5-27b-claude-4.6-opus-reasoning-distilled@q4_k_m` | Heavy reasoning |
| `LM_STUDIO_VISION_MODEL` | `qwen3.5-27b-claude-4.6-opus-reasoning-distilled@q4_k_m` | Image / video / screenshot understanding |
| `LM_STUDIO_EMBED_MODEL` | `text-embedding-qwen3-embedding-0.6b` | ChromaDB embeddings |
| `TTS_URL` | `http://127.0.0.1:5003/tts` | Custom XTTS server endpoint |
| `TTS_VOICE` | `aria_default` | Voice identifier passed to the TTS server |
| `CHROMADB_URL` | `http://192.168.68.88:8000` | ChromaDB server (falls back to local if down) |
| `CHROMADB_FALLBACK_DIR` | `brain/chroma_local/` | Local DuckDB+Parquet persistent fallback |
| `ARIA_BRAIN_HOST` | `127.0.0.1` | Brain service bind host |
| `ARIA_BRAIN_PORT` | `8770` | Brain service port |
| `MOOD_SCALE_MIN` | `1` | Minimum mood value |
| `MOOD_SCALE_MAX` | `5` | Maximum mood value |
| `MOOD_INITIAL` | `3` | Mood at startup |
| `MOOD_DECAY_PER_HOUR` | `-0.083` | Mood drops this much per hour (≈0.5/6h) |
| `MOOD_DECAY_AFTER_HOURS` | `0.5` | Start decaying after 30min of silence |
| `MOOD_BOOST_POSITIVE` | `1.0` | Mood boost on positive sentiment |
| `MOOD_BOOST_QUESTION` | `0.5` | Mood boost on engaged questions |
| `MOOD_BOOST_NEGATIVE` | `-0.5` | Mood drop on negative sentiment |
| `REFLECTION_CADENCE_MINUTES` | `120` | APScheduler interval for Aria's self-reflection |
| `REFLECTION_ENABLED` | `true` | Toggle reflection scheduler |
| `PERSONA_NAME` | `Aria` | Display name in the persona prompt |
| `REPLY_LANGUAGE` | `english` | Language hint injected into every prompt |
| `ARIA_HEALTH_LOG_DIR` | project root | Where `aria_health.log` lives |
| `ARIA_HEALTH_LOG` | `aria_health.log` | File name |
| `MOOD_STATE_PATH` | `brain/mood.json` | Where mood state is persisted |

### `brain/src/aria_brain/personality.py`
Hardcoded persona prompt + drift detector. Edit CAREFULLY — this shapes every interaction.

| Constant | Default | What it does |
|---|---|---|
| `PERSONA_BASE` | (long prompt) | The strict Aria persona. Defines identity, values, dislikes, mood expression, reply format |
| `_DRIFT_RATIO_THRESHOLD` | `0.05` | Reject replies where >5% of letters are non-Latin |
| `detect_drift()` | function | Detects CJK / Cyrillic / Arabic / Hebrew / etc. in replies |

### `brain/src/aria_brain/brain.py`
| Setting | Default | What it does |
|---|---|---|
| `max_drift_retries` | `2` | Max retries when LLM replies in non-English |

---

## 2. Aria Watchdog (`watchdog/`)

CrewAI agent crew that watches services + diagnoses failures.

### `watchdog/.env`
| Variable | Default | What it does |
|---|---|---|
| `LM_STUDIO_BASE_URL` | `http://192.168.68.88:1010/v1` | LM Studio endpoint |
| `LM_STUDIO_API_KEY` | `lm-studio` | Auth header |
| `AISISTANT_MODEL` | `openai/qwen2.5-3b-instruct` | Watcher + Fixer default |
| `AISISTANT_STRONG_MODEL` | `openai/qwen3.5-27b-claude-4.6-opus-reasoning-distilled@q4_k_m` | Diagnostician + Knowledge Manager |
| `AISISTANT_EMBED_MODEL` | `openai/text-embedding-qwen3-embedding-0.6b` | Knowledge base embeddings |
| `AISISTANT_SAFE_MODE` | `true` | Refuse taskkill/reconfigure/Godot edits; escalate instead |
| `AISISTANT_TICK_SECONDS` | `30` | How often the crew runs |
| `ARIA_HEALTH_LOG_DIR` | project root | Where `aria_health.log` lives |

### `watchdog/knowledge/services.yaml`
The service map the Watcher probes each tick. Each entry: `name`, `host`, `port`, `proto` (`http|ws|tcp`), `health_path`, `critical` (bool).

Current default services:
- `aria_chat_server` (Godot embedded, port 8767)
- `tts_server` (PC 1, port 5003)
- `lm_studio` (PC 2, port 1010)
- `astro_server` (PC 2, port 8765) — Sarah's WebSocket; Aria doesn't strictly need it
- `motion_server` (PC 2, port 8766) — FloodDiffusion motion server
- `aria_brain` (PC 1, port 8770)

### `watchdog/knowledge/known_fixes.yaml`
Auto-grown KB of past fixes. Empty initially; Knowledge Manager appends after verified fixes.

---

## 3. Aria Godot Game (`aria/`)

The character itself.

### `aria/scripts/Main.cs` (Inspector-exposed fields)
| Field | Default | What it does |
|---|---|---|
| `TtsUrl` | `http://127.0.0.1:5003/tts` | TTS endpoint |
| `TtsUseJsonPost` | `true` | POST JSON vs GET query |
| `TtsSpeaker` | `""` | XTTS speaker ID |
| `TtsLanguage` | `"en"` | TTS language |
| `MotionServerUrl` | `http://192.168.68.88:8766/motion` | Optional motion-diffusion server |
| `MotionQueueCapacity` | `100` | Max queued motion requests |
| `MotionPollIntervalSec` | `2` | How often to poll motion status |
| `MotionAuthToken` | `""` | Optional auth for motion server |
| `ChatServerPort` | `8767` | Aria's HTTP chat server (for Streamlit dashboard) |
| `MotionLibraryPath` | `res://../motion_lib/motion_library.json` | Where Aria reads motion library |
| `MotionLibraryPollSec` | `300` | How often to re-mirror motion library |
| `VoiceEnabled` | `true` | Master toggle for Aria's voice |
| `VrmNodePath` | (path) | Path to the VRM/Aria node |
| `SpeechLabelPath` | `UI/SpeechLabel` | Path to the speech bubble UI |

### `aria/scripts/SpringBoneSimulator.cs` (Inspector-exposed)
| Field | Default | What it does |
|---|---|---|
| `Enabled` | `true` | Master toggle |
| `GravityY` | `-9.8` | Gravity acceleration (m/s²) |
| `SkirtStiffness` | `8` | Spring force constant for skirt bones |
| `SkirtDamping` | `0.5` | Velocity damping for skirt |
| `HairStiffness` | `5` | Spring force constant for hair bones |
| `HairDamping` | `0.3` | Velocity damping for hair |
| `BustStiffness` | `25` | Spring force constant for bust bones |
| `BustDamping` | `1.5` | Velocity damping for bust |
| `MaxOffset` | `1.5` | Max spring displacement (world units) |
| `MaxVelocity` | `14` | Max spring velocity cap |
| `InertiaScale` | `2.5` | Multiplier on body-translation inertia coupling |
| `RotationalInertiaScale` | `3.0` | Multiplier on body-rotation inertia coupling |
| `ThighCollisionEnabled` | `true` | Push skirt springs out of thigh capsules |
| `ThighRadius` | `0.10` | Thigh capsule radius for skirt collision |
| `LogEverySec` | `1.0` | How often the modifier logs to stdout |

---

## 4. TTS (`tts/`)

The vendored Coqui-XTTS-v2 repo + Jessica/Ana voice models + the custom XTTS wrapper script that serves audio on port 5003.

### Models (in `tts/run/training/`)
- `XTTS_v2_Jessica_Voice-June-08-2026_05+55PM-dbf1a08a/` — Jessica voice (current TTS model)
- `XTTS_v2_Ana_Voice-June-08-2026_04+18PM-dbf1a08a/` — Ana voice (earlier TTS, may still be used by Sarah scripts if any survived)
- `XTTS_v2_original_model_files/` — base XTTS-v2 model (required for inference)
- `XTTS_v2_AstroBud_Voice-June-08-2026_10+59AM-dbf1a08a/` — latest AstroBud/Sarah voice (kept for historical reference; Aria doesn't use it)

### Live TTS server: `aria/scripts/tts_server_jessica.py`
Port 5003. Custom wrapper that loads the Jessica model and serves audio. Edit the model path inside to point at the Jessica training dir.

---

## 5. Motion library (`motion_lib/`)

Holds the motion library that Aria reads at startup.

### `motion_lib/motion_library.json`
~500 KB, 533 anim specs (duration, isInPlace, travel speed, cut-short, boneSet, etc.). Aria mirrors this into a C# dict every 5 minutes.

### `motion_lib/motion_library.py`
Generates `motion_library.json`. Run standalone to refresh.

### `motion_lib/ingest_motion_library.py`
Populates the library from external sources (e.g. motion server output).

### `motion_lib/motion_server.py` (FloodDiffusion-based, optional)
Port 8766. Single-job queue, max 100 items. Aria can poll it for new motion generations.

---

## 6. Scripts (`scripts/`)

### `scripts/start-aria-stack.ps1`
PowerShell orchestrator. Edit `$Processes` to match your stack.

### `scripts/setup-ssh-to-ai-pc.ps1`
One-time SSH key setup for passwordless access from PC 1 to PC 2.

---

## 7. External (not in this folder)

| Tool | Default | Why |
|---|---|---|
| Python | 3.12+ | Runtime |
| uv | latest | Package manager |
| Godot | 4.6.3 Mono | Runs `aria/` |
| .NET SDK | 8.0 | Godot Mono + Aria's C# |
| LM Studio | latest | LLM inference on PC 2 |
| OpenSSH Client + Server | (Windows Optional Feature) | PC 2 management |

---

## Quick sanity check

After any changes, verify:

```powershell
# Brain reachable
curl http://127.0.0.1:8770/health

# Watchdog sees all services
cd watchdog; uv run python -m aisistant.main doctor

# Aria loads in Godot — click taskbar shortcut, watch for [AnimBuilder] Done. N animations baked
```

If any of those fail, check the relevant section's settings above.