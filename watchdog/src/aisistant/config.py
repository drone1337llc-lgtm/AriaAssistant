"""Centralized configuration for the Aria maintenance crew.

Edit this file (or override via .env) to add new services or change behavior.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

# Load .env from the project root (watchdog/.env) BEFORE any os.environ.get() calls below.
# python-dotenv comes in transitively via crewai[tools]; this block is safe if it's missing.
try:
    from dotenv import load_dotenv
    _ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
except ImportError:
    pass  # python-dotenv not installed; rely on process env

# --- Paths ------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src" / "aisistant"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
LOG_DIR = Path(os.environ.get("ARIA_HEALTH_LOG_DIR", str(PROJECT_ROOT)))
ARIA_HEALTH_LOG = LOG_DIR / "aria_health.log"
KNOWN_FIXES_PATH = KNOWLEDGE_DIR / "known_fixes.yaml"
SERVICES_PATH = KNOWLEDGE_DIR / "services.yaml"


# --- Behavior flags ---------------------------------------------------------

SAFE_MODE: bool = os.environ.get("AISISTANT_SAFE_MODE", "true").lower() in ("1", "true", "yes")
TICK_SECONDS: int = int(os.environ.get("AISISTANT_TICK_SECONDS", "30"))
LM_STUDIO_BASE_URL: str = os.environ.get("LM_STUDIO_BASE_URL", "http://192.168.68.88:1010/v1")
LM_STUDIO_API_KEY: str = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")

# Four role-based models (matches aria_brain/config.py):
#   chat    — Aria's voice (used by Aria Brain, not the crew)
#   parser  — structured-output, JSON-friendly, fast (Watcher + Fixer)
#   coder   — heavy reasoning (Diagnostician + Knowledge Manager)
#   embed   — vector embeddings for the knowledge base
DEFAULT_MODEL: str = os.environ.get("AISISTANT_MODEL",        "openai/qwen2.5-3b-instruct")                                          # parser
STRONG_MODEL: str = os.environ.get("AISISTANT_STRONG_MODEL", "openai/qwen3.5-27b-claude-4.6-opus-reasoning-distilled@q4_k_m")    # coder
EMBED_MODEL: str = os.environ.get("AISISTANT_EMBED_MODEL",   "openai/text-embedding-qwen3-embedding-0.6b")                       # embed

ESCALATION_LOG: Path = PROJECT_ROOT / "escalations.log"


# --- Service map ------------------------------------------------------------

class Service(BaseModel):
    name: str
    host: str
    port: int
    proto: str = "http"        # http | ws | tcp
    health_path: str = "/"     # for http; for ws/tcp just used to check connect
    critical: bool = True      # if True, a failure escalates immediately


def load_services() -> list[Service]:
    """Load the service map. services.yaml in knowledge/ overrides defaults."""
    if SERVICES_PATH.exists():
        with open(SERVICES_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
        return [Service(**s) for s in raw]
    # Fallback default — derived from aria-architecture-state.md
    return [
        # PC 1 — this machine
        Service(name="aria_chat_server", host="127.0.0.1", port=8767, health_path="/"),
        Service(name="tts_server",       host="127.0.0.1", port=5003, health_path="/"),
        # PC 2 — AI box
        Service(name="lm_studio",        host="192.168.68.88", port=1010, health_path="/v1/models"),
        Service(name="astro_server",     host="192.168.68.88", port=8765, proto="ws"),
        Service(name="motion_server",    host="192.168.68.88", port=8766, health_path="/"),
    ]