"""Centralized configuration for Aria Brain."""
from __future__ import annotations

import os
from pathlib import Path

# Load .env from the project root (brain/.env) BEFORE any os.environ.get() calls below.
# Optional — the module still works without python-dotenv (e.g. in CI) as long as the
# env vars are set some other way.
try:
    from dotenv import load_dotenv
    _ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
except ImportError:
    pass  # python-dotenv not installed; rely on process env

# --- Paths ------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src" / "aria_brain"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
ARIA_HEALTH_LOG_DIR = Path(os.environ.get("ARIA_HEALTH_LOG_DIR", str(PROJECT_ROOT.parent)))
ARIA_HEALTH_LOG_PATH = ARIA_HEALTH_LOG_DIR / os.environ.get("ARIA_HEALTH_LOG", "aria_health.log")
MOOD_STATE_PATH = Path(os.environ.get(
    "MOOD_STATE_PATH",
    str(PROJECT_ROOT / "mood.json"),
))

# --- Brain service ----------------------------------------------------------
ARIA_BRAIN_HOST = os.environ.get("ARIA_BRAIN_HOST", "127.0.0.1")
ARIA_BRAIN_PORT = int(os.environ.get("ARIA_BRAIN_PORT", "8770"))

# --- LLM (LM Studio on PC 2) ------------------------------------------------
LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://192.168.68.88:1010/v1")
LM_STUDIO_API_KEY = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")

# Five distinct model roles:
#   chat    — Aria's conversational voice (persona + mood + short punchy replies)
#   parser  — structured output, fast, JSON-friendly, cheap
#   coder   — heavy reasoning, code
#   vision  — image / video / screenshot understanding
#   embed   — vector embeddings for ChromaDB
LM_STUDIO_CHAT_MODEL   = os.environ.get("LM_STUDIO_CHAT_MODEL",   "humanish-roleplay-llama-3.1-8b-i1")
LM_STUDIO_PARSER_MODEL = os.environ.get("LM_STUDIO_PARSER_MODEL", "qwen2.5-coder-1.5b-instruct")
LM_STUDIO_CODER_MODEL  = os.environ.get("LM_STUDIO_CODER_MODEL",  "nvidia_nvidia-nemotron-nano-9b-v2")
LM_STUDIO_VISION_MODEL = os.environ.get("LM_STUDIO_VISION_MODEL", "qwen/qwen2.5-vl-7b")
LM_STUDIO_EMBED_MODEL  = os.environ.get("LM_STUDIO_EMBED_MODEL",  "text-embedding-qwen3-embedding-0.6b")

# Backwards-compat aliases (some modules still reference the old names)
LM_STUDIO_MODEL        = os.environ.get("LM_STUDIO_MODEL",        LM_STUDIO_CHAT_MODEL)
LM_STUDIO_STRONG_MODEL = os.environ.get("LM_STUDIO_STRONG_MODEL", LM_STUDIO_CODER_MODEL)

# --- TTS (PC 1 local) -------------------------------------------------------
TTS_URL = os.environ.get("TTS_URL", "http://127.0.0.1:5003/tts")
TTS_VOICE = os.environ.get("TTS_VOICE", "aria_default")

# --- ChromaDB ---------------------------------------------------------------
CHROMADB_URL = os.environ.get("CHROMADB_URL", "http://192.168.68.88:8000")
CHROMADB_FALLBACK_DIR = os.environ.get(
    "CHROMADB_FALLBACK_DIR",
    str(PROJECT_ROOT / "chroma_local"),
)

# --- Mood -------------------------------------------------------------------
MOOD_SCALE_MIN = int(os.environ.get("MOOD_SCALE_MIN", "1"))
MOOD_SCALE_MAX = int(os.environ.get("MOOD_SCALE_MAX", "5"))
MOOD_INITIAL = int(os.environ.get("MOOD_INITIAL", "3"))
MOOD_DECAY_PER_HOUR = float(os.environ.get("MOOD_DECAY_PER_HOUR", "-0.083"))
MOOD_DECAY_AFTER_HOURS = float(os.environ.get("MOOD_DECAY_AFTER_HOURS", "0.5"))
MOOD_BOOST_POSITIVE = float(os.environ.get("MOOD_BOOST_POSITIVE", "1.0"))
MOOD_BOOST_QUESTION = float(os.environ.get("MOOD_BOOST_QUESTION", "0.5"))
MOOD_BOOST_NEGATIVE = float(os.environ.get("MOOD_BOOST_NEGATIVE", "-0.5"))

# --- Reflection -------------------------------------------------------------
REFLECTION_CADENCE_MINUTES = int(os.environ.get("REFLECTION_CADENCE_MINUTES", "120"))
REFLECTION_ENABLED = os.environ.get("REFLECTION_ENABLED", "true").lower() in ("1", "true", "yes")

# --- Personality ------------------------------------------------------------
PERSONA_NAME = os.environ.get("PERSONA_NAME", "Aria")

# Force a language hint for the LLM. Set REPLY_LANGUAGE=none to disable.
REPLY_LANGUAGE = os.environ.get("REPLY_LANGUAGE", "english")


# --- Helpers ----------------------------------------------------------------
def _bool(env_name: str, default: bool) -> bool:
    raw = os.environ.get(env_name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")