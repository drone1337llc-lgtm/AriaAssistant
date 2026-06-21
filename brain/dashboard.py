"""Aria Brain — Streamlit dashboard.

Run from within the brain/ directory:
    streamlit run dashboard.py

Or from the project root:
    streamlit run brain/dashboard.py

Opens automatically from the system tray → "Open Dashboard".
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make aria_brain importable (brain/src/ → sys.path)
_src = Path(__file__).parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import os
import httpx
import streamlit as st
from dotenv import set_key, dotenv_values

from aria_brain.config import (
    LM_STUDIO_BASE_URL,
    LM_STUDIO_CHAT_MODEL,
    LM_STUDIO_PARSER_MODEL,
    LM_STUDIO_CODER_MODEL,
    LM_STUDIO_VISION_MODEL,
    LM_STUDIO_EMBED_MODEL,
    ARIA_BRAIN_HOST,
    ARIA_BRAIN_PORT,
    TTS_URL,
)

_ENV_PATH = Path(__file__).parent / ".env"
_BRAIN_URL = f"http://{ARIA_BRAIN_HOST}:{ARIA_BRAIN_PORT}"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Aria Dashboard",
    page_icon="🔮",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Data fetchers (cached so refresh button is the escape hatch)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30, show_spinner=False)
def fetch_lm_models() -> tuple[list[str], str | None]:
    """Return (model_ids, error_msg). model_ids is [] on failure."""
    try:
        base = LM_STUDIO_BASE_URL.rstrip("/")
        r = httpx.get(f"{base}/models", timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            ids = [m["id"] for m in data.get("data", [])]
            return sorted(ids), None
        return [], f"HTTP {r.status_code}"
    except Exception as exc:
        return [], str(exc)


@st.cache_data(ttl=10, show_spinner=False)
def fetch_brain_health() -> dict | None:
    try:
        r = httpx.get(f"{_BRAIN_URL}/health", timeout=3.0)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


@st.cache_data(ttl=5, show_spinner=False)
def ping_tts() -> bool:
    # Try a lightweight OPTIONS/HEAD, fall back to a tiny GET to the base URL.
    base = TTS_URL.rsplit("/", 1)[0]  # strip /tts path
    try:
        r = httpx.get(base, timeout=2.0)
        return r.status_code < 500
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🔮 Aria Brain Dashboard")

# ---------------------------------------------------------------------------
# Status row
# ---------------------------------------------------------------------------
models, model_err = fetch_lm_models()
health = fetch_brain_health()
tts_ok = ping_tts()

col_lm, col_brain, col_tts, col_refresh = st.columns([2, 2, 2, 1])

with col_lm:
    if model_err:
        st.error(f"**LM Studio** ✗  {model_err}")
    else:
        st.success(f"**LM Studio** ✓  {len(models)} model{'s' if len(models) != 1 else ''}")

with col_brain:
    if health:
        mood = health.get("mood", {})
        label = mood.get("label", "online") if isinstance(mood, dict) else "online"
        st.success(f"**Brain** ✓  mood: {label}")
    else:
        st.warning("**Brain** ✗  offline")

with col_tts:
    if tts_ok:
        st.success("**TTS** ✓  reachable")
    else:
        st.warning("**TTS** ✗  offline")

with col_refresh:
    st.write("")  # vertical align
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Model role assignment
# ---------------------------------------------------------------------------
st.subheader("Model Roles")
st.caption(
    f"Fetched from `{LM_STUDIO_BASE_URL}`. "
    "Select the model for each role then click **Save**."
)

if model_err:
    st.warning(
        f"⚠ Could not reach LM Studio ({model_err}). "
        "Dropdowns show current config values only — you can still edit and save."
    )

# Role definitions: display name, env-var key, current value, description
ROLES = [
    ("Chat",   "LM_STUDIO_CHAT_MODEL",   LM_STUDIO_CHAT_MODEL,
     "Aria's conversational voice — persona, mood, short punchy replies"),
    ("Parser", "LM_STUDIO_PARSER_MODEL", LM_STUDIO_PARSER_MODEL,
     "Structured output, fast JSON calls, cheap"),
    ("Coder",  "LM_STUDIO_CODER_MODEL",  LM_STUDIO_CODER_MODEL,
     "Heavy reasoning and code generation"),
    ("Vision", "LM_STUDIO_VISION_MODEL", LM_STUDIO_VISION_MODEL,
     "Image, screenshot, and video understanding (needs a multimodal model)"),
    ("Embed",  "LM_STUDIO_EMBED_MODEL",  LM_STUDIO_EMBED_MODEL,
     "ChromaDB vector embeddings (needs an embedding model)"),
]


def _options_for(current: str) -> list[str]:
    """Build option list: live models, prepending current if absent."""
    opts = list(models)  # copy sorted live list
    if current and current not in opts:
        opts.insert(0, current)  # keep configured value visible
    if not opts:
        opts = [current or "(none)"]
    return opts


def _index_of(value: str, opts: list[str]) -> int:
    try:
        return opts.index(value)
    except ValueError:
        return 0


selections: dict[str, str] = {}

for label, env_key, current, help_text in ROLES:
    opts = _options_for(current)
    selections[env_key] = st.selectbox(
        f"**{label}**",
        options=opts,
        index=_index_of(current, opts),
        help=help_text,
        key=f"sel_{env_key}",
    )

st.divider()

# ---------------------------------------------------------------------------
# Save button
# ---------------------------------------------------------------------------
save_col, reload_col = st.columns([1, 1])

with save_col:
    if st.button("💾 Save to brain/.env", type="primary", use_container_width=True):
        _ENV_PATH.touch()
        changed: list[str] = []
        for env_key, chosen in selections.items():
            if chosen and chosen not in ("(none)",):
                set_key(str(_ENV_PATH), env_key, chosen)
                changed.append(f"  {env_key} = {chosen}")
        if changed:
            st.success("**Saved** — restart the brain server to apply:\n\n" + "\n\n".join(changed))
        else:
            st.info("Nothing changed.")

with reload_col:
    # Only show if brain is running; /reload-config is optional, fall back gracefully.
    if health:
        if st.button("♻️ Hot-reload brain config", use_container_width=True,
                     help="Calls /reload-config on the brain server. "
                          "Not all config values can be hot-reloaded."):
            try:
                r = httpx.post(f"{_BRAIN_URL}/reload-config", timeout=5.0)
                if r.status_code == 200:
                    st.success("Brain reloaded!")
                else:
                    st.info(
                        f"Brain returned {r.status_code} — "
                        "this endpoint may not exist yet. Restart the server manually."
                    )
            except Exception as exc:
                st.warning(f"Reload failed: {exc}")

st.divider()

# ---------------------------------------------------------------------------
# Mood / brain health detail
# ---------------------------------------------------------------------------
st.subheader("Brain Health")

if health:
    mood = health.get("mood", {})
    mem  = health.get("memory", {})

    m1, m2, m3 = st.columns(3)
    with m1:
        v = mood.get("value", 3.0) if isinstance(mood, dict) else 3.0
        st.metric("Mood", f"{v:.1f} / 5", mood.get("label", "") if isinstance(mood, dict) else "")
    with m2:
        hrs = mood.get("hours_since_interaction", 0) if isinstance(mood, dict) else 0
        st.metric("Idle (hours)", f"{hrs:.1f}")
    with m3:
        epi = mem.get("episodic_count", "?") if isinstance(mem, dict) else "?"
        st.metric("Memories", epi)

    with st.expander("Full health payload"):
        st.json(health)
else:
    st.info("Brain server is offline — start it with `aria_brain` or the system tray.")

# ---------------------------------------------------------------------------
# Current .env snapshot
# ---------------------------------------------------------------------------
st.subheader("brain/.env snapshot")

env_vals = dotenv_values(str(_ENV_PATH)) if _ENV_PATH.exists() else {}
if env_vals:
    for k, v in sorted(env_vals.items()):
        st.text(f"{k}={v}")
else:
    st.info(
        f"`{_ENV_PATH}` does not exist yet — defaults from `config.py` are in use. "
        "Click **Save** above to create it."
    )
