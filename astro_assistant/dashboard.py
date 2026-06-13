"""
AstroBud Streamlit control dashboard.

Run: streamlit run dashboard.py
Opens at http://localhost:8501

Panels:
    - Server status (LM Studio connectivity, loaded models)
    - Core Neural Profiles (chat / code / vision / embedding model pickers)
    - System Directives (sleep mode, auto-start at boot)
    - Assistance Matrix (helpfulness level, scan interval)
    - Live Vector Sandbox Logs (last 3 daily_log entries)
    - Memory & Storage Optimization (purge temp files, flush VRAM hint)
    - Dynamic Storage Threshold Metrics
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import cleanup  # noqa: E402
import lmstudio_client as lms  # noqa: E402
import storage_watchdog  # noqa: E402


CONFIG_FILE = PROJECT_ROOT / "config.json"
LOG_FILE = PROJECT_ROOT / "daily_log.json"

# Installed model catalog — mirrors ~/.lmstudio/models. Update when you add new models.
TEXT_MODELS = [
    "Lexi-Llama-3-8B-Uncensored",           # fast chat (default chat_model)
    "Qwen2.5-3B-Instruct",                  # lighter chat alternative
    "Qwen3.6-27B-Uncensored-HauhauCS",      # upgrade: better reasoning, uncensored
    "Qwen3.6-40B-IMatrix",                  # premium: highest quality (needs more VRAM)
    "Qwen3-Coder-30B-A3B-Instruct",         # code brain (default code_model)
    "Qwen2.5-Coder-1.5B-Instruct",          # triage fast yes/no (default triage_model)
    "DeepSeek-Coder-V2-Lite-Instruct",      # code alternative
    "Darwin-28B-Coder",                     # code alternative
]
VISION_MODELS = [
    "NousResearch_Nous-Hermes-2-Vision",    # LLaVA-based vision model
    "Qwen3.6-40B-IMatrix",                  # multimodal (has mmproj, needs VRAM)
]
EMBEDDING_MODELS = [
    "nomic-embed-text-v2-moe",
]


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        default = {
            "chat_model": TEXT_MODELS[0],
            "code_model": TEXT_MODELS[1],
            "triage_model": TEXT_MODELS[4],
            "vision_model": VISION_MODELS[0],
            "embedding_model": EMBEDDING_MODELS[0],
            "helpfulness_level": "Reactive (Watches Errors)",
            "scan_interval": 10,
            "sleep_mode": False,
            "auto_start_boot": False,
            "auto_load_models": True,
            "max_storage_allowed": 500.0,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)


def manage_windows_startup(enable: bool, main_script: str) -> tuple[bool, str]:
    """Adds/removes AstroBud from HKCU\\...\\Run."""
    if sys.platform != "win32":
        return False, "Auto-start only supported on Windows."
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "AstroBudAssistant"
        script_path = f'"{sys.executable}" "{os.path.abspath(main_script)}"'
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, script_path)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True, "Registry updated."
    except Exception as e:
        return False, f"Registry error: {e}"


# =====================================================================
# UI
# =====================================================================

st.set_page_config(page_title="AstroBud Control Matrix", page_icon="🤖", layout="wide")

st.title("🤖 AstroBud Assistant Control Matrix")
st.markdown("---")

# Server status (always at top so the user knows if LM Studio is alive)
with st.expander("🔌 LM Studio Server Status", expanded=True):
    try:
        client = lms.get_client()
        info = lms.smoke_test(client)
    except Exception as e:
        info = {"server_reachable": False, "models": [], "error": str(e)}

    c1, c2 = st.columns([1, 3])
    with c1:
        st.metric("Server", "🟢 Online" if info["server_reachable"] else "🔴 Offline")
    with c2:
        if info["server_reachable"]:
            st.write("Loaded models:", ", ".join(info["models"]) or "(none)")
        else:
            st.error(f"LM Studio unreachable. {info.get('error', '')}")

    if st.button("🔄 Reload status", use_container_width=False):
        st.rerun()

# AstroBud server status (separate from LM Studio — this is the WebSocket bridge)
with st.expander("🌐 AstroBud Two-PC Network", expanded=False):
    st.markdown(
        "If you're running AstroBud across two PCs (AI server on PC 2, "
        "client on PC 1), this is the WebSocket bridge that carries screen "
        "frames and audio between them."
    )
    st.caption("This dashboard runs on the AI server (PC 2).")
    n1, n2 = st.columns([1, 1])
    with n1:
        st.markdown("**Server (PC 2 — this machine)**")
        st.code(f"python server.py --port {config.get('server_port', 8765)}", language="bash")
        st.caption(
            "Run this on PC 2. It binds to "
            f"`{config.get('server_bind', '0.0.0.0')}:{config.get('server_port', 8765)}`."
        )
    with n2:
        st.markdown("**Client (PC 1 — your gaming PC)**")
        st.code(
            f"python client.py --server {config.get('server_url', 'ws://<server-ip>:8765')}",
            language="bash",
        )
        st.caption("Run this on PC 1. It streams screen + mic to the server.")
    st.markdown("---")
    st.markdown("**Network settings**")
    config["server_url"] = st.text_input(
        "Server WebSocket URL (used by client.py)",
        value=config.get("server_url", "ws://192.168.10.2:8765"),
        help="The URL the PC 1 client connects to. Use the PC 2's static LAN IP.",
    )
    config["server_port"] = st.number_input(
        "Server port",
        min_value=1024, max_value=65535,
        value=int(config.get("server_port", 8765)),
    )
    config["server_bind"] = st.text_input(
        "Server bind address",
        value=config.get("server_bind", "0.0.0.0"),
        help="0.0.0.0 = accept connections from any interface. Change to a specific IP for tighter security.",
    )
    config["client_frame_fps"] = st.slider(
        "Client screen frame rate (FPS)",
        min_value=0.2, max_value=5.0,
        value=float(config.get("client_frame_fps", 1.0)),
        step=0.2,
        help="How many screen frames per second the client sends to the server. 1 FPS is usually plenty.",
    )
    config["client_jpeg_quality"] = st.slider(
        "Client JPEG quality",
        min_value=30, max_value=95,
        value=int(config.get("client_jpeg_quality", 70)),
        help="Lower = less network bandwidth, slightly less accurate OCR.",
    )

config = load_config()

col1, col2 = st.columns([1, 1])

with col1:
    st.header("⚙️ Core Neural Profiles")

    def index_in(options, value, default):
        try:
            return options.index(value)
        except ValueError:
            return options.index(default) if default in options else 0

    config["chat_model"] = st.selectbox(
        "Primary Chat Brain",
        TEXT_MODELS,
        index=index_in(TEXT_MODELS, config.get("chat_model"), TEXT_MODELS[0]),
        help="General conversation, persona, tool use.",
    )
    config["code_model"] = st.selectbox(
        "Code Brain (Dev Workflow)",
        TEXT_MODELS,
        index=index_in(TEXT_MODELS, config.get("code_model"), TEXT_MODELS[1]),
        help="Used for sandbox self-correction and code triage.",
    )
    config["triage_model"] = st.selectbox(
        "Triage / Fast Classifier",
        TEXT_MODELS,
        index=index_in(TEXT_MODELS, config.get("triage_model"), TEXT_MODELS[4]),
        help="Tiny model used for YES/NO screen triage (saves VRAM).",
    )
    config["vision_model"] = st.selectbox(
        "Vision Model",
        VISION_MODELS,
        index=index_in(VISION_MODELS, config.get("vision_model"), VISION_MODELS[0]),
    )
    config["embedding_model"] = st.selectbox(
        "Embedding Model",
        EMBEDDING_MODELS,
        index=index_in(EMBEDDING_MODELS, config.get("embedding_model"), EMBEDDING_MODELS[0]),
    )

    st.header("⚡ System Directives")
    config["sleep_mode"] = st.toggle(
        "🌙 Sleep Mode (suspends scanning)",
        config.get("sleep_mode", False),
    )
    if config["sleep_mode"]:
        st.warning("AstroBud is resting. Text and vision scanning suspended.")
    else:
        st.success("AstroBud is active and scanning environmental nodes.")

    config["auto_load_models"] = st.toggle(
        "📥 Auto-load models via `lms` CLI when missing",
        config.get("auto_load_models", True),
        help="If the chat model isn't loaded, AstroBud will try `lms load <model>` automatically.",
    )

    old_boot = config.get("auto_start_boot", False)
    config["auto_start_boot"] = st.toggle(
        "🏁 Launch AstroBud on Windows boot",
        old_boot,
    )
    if config["auto_start_boot"] != old_boot:
        ok, msg = manage_windows_startup(config["auto_start_boot"], "main_astro.py")
        if ok:
            st.success(msg)
        else:
            st.error(msg)

with col2:
    st.header("💡 Assistance Matrix Levels")
    config["helpfulness_level"] = st.select_slider(
        "Helpfulness Engagement Target",
        options=[
            "Passive (Voice Prompts Only)",
            "Reactive (Watches Errors)",
            "Proactive (Scans Constantly)",
            "Active Entertainment (Co-pilot for Media/Games)",
        ],
        value=config.get("helpfulness_level", "Reactive (Watches Errors)"),
        help=(
            "Passive: only when you speak. Reactive: scan for code errors. "
            "Proactive: scan constantly. Entertainment: proactive co-pilot for movies/games."
        ),
    )
    # Show the right interval slider for the chosen mode
    if "Entertainment" in config["helpfulness_level"]:
        config["entertainment_interval"] = st.slider(
            "Co-pilot Comment Cadence (seconds)",
            min_value=10, max_value=120,
            value=int(config.get("entertainment_interval", 30)),
            help="How often the entertainment co-pilot looks at the screen and offers a comment.",
        )
    else:
        config["scan_interval"] = st.slider(
            "Screen Analysis Loop Cadence (seconds)",
            min_value=3, max_value=60, value=int(config.get("scan_interval", 10)),
        )

    st.markdown("##### ⌨️ Global Hotkeys")
    st.markdown(
        "All hotkeys use `Ctrl+Shift+` modifiers to avoid conflicts with game / OS bindings.\n\n"
        "- **Ctrl+Shift+F1** — Summon AstroBud (works in any mode)\n"
        "- **Ctrl+Shift+F2** — Mute / unmute TTS output\n"
        "- **Ctrl+Shift+F3** — One-shot screen description\n"
        "- **Ctrl+Shift+F4** — Flag current screen as a bug (auto-triages + saves)\n"
        "- **Ctrl+Shift+F5** — Export recent bugs (Markdown + clipboard)\n\n"
        "_Requires the script to run as Administrator on Windows._"
    )

    st.header("📊 Live Vector Sandbox Logs")
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2:
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
            st.json(logs[-3:] if logs else "Log empty.")
        except json.JSONDecodeError:
            st.text("Log buffers indexing...")
    else:
        st.info("No system debug traces logged yet during this daytime shift.")

if st.button("💾 Apply Control Configuration Changes", use_container_width=True):
    save_config(config)
    st.toast("AstroBud parameters synchronized!", icon="✅")

# ---------------------------------------------------------------------
# Memory & Storage Optimization
# ---------------------------------------------------------------------

st.markdown("---")
st.header("🧹 Memory & Storage Optimization Center")

cp1, cp2 = st.columns(2)
with cp1:
    st.subheader("Storage Optimization")
    st.write("Deletes scratchpad scripts, vision screen frames, audio buffers, and clears today's temporary JSON log pile.")
    if st.button("🗑️ Purge Task Cache & Wipe Temp Storage", use_container_width=True):
        with st.spinner("Scrubbing task file buffers..."):
            removed = cleanup.purge_temporary_files()
            st.success(f"Storage purge complete. Cleared {removed} temporary files + wiped daily log cache.")

with cp2:
    st.subheader("Hardware RAM Optimization")
    st.write("Runs Python garbage collection. (LM Studio manages its own VRAM; unload via the LM Studio GUI as needed.)")
    if st.button("♻️ Flush Python RAM & GC", use_container_width=True):
        with st.spinner("Collecting garbage..."):
            cleanup.free_hardware_ram()
            st.success("Python RAM collected. Open LM Studio and unload unused models to free VRAM.")

# ---------------------------------------------------------------------
# Beta Feedback Log (open-world RPG playtesting)
# ---------------------------------------------------------------------

st.markdown("---")
st.header("🐛 Beta Feedback Log (press Ctrl+Shift+F4 in client to flag)")

from tools import list_bug_observations, BUGS_LOG_PATH, BUG_SCREENS_DIR, export_bugs

bug_count = 0
if BUGS_LOG_PATH.exists():
    try:
        with open(BUGS_LOG_PATH, "r", encoding="utf-8") as f:
            bug_count = sum(1 for line in f if line.strip())
    except OSError:
        bug_count = 0

bc1, bc2, bc3 = st.columns([1, 2, 2])
with bc1:
    st.metric("Total bug entries", bug_count)
with bc2:
    st.caption(
        f"Log: `{BUGS_LOG_PATH.relative_to(PROJECT_ROOT)}`  |  "
        f"Screens: `{BUG_SCREENS_DIR.relative_to(PROJECT_ROOT)}/*.png`"
    )
with bc3:
    config["export_last_n"] = int(st.number_input(
        "Export count (most recent N)",
        min_value=1, max_value=200,
        value=int(config.get("export_last_n", 10)),
        help="How many bugs to include when you click Export.",
    ))

exp_col1, exp_col2, exp_col3 = st.columns([1, 1, 2])
with exp_col1:
    if st.button("📤 Export bugs (Markdown + clipboard)", use_container_width=True):
        try:
            result = export_bugs(
                last_n=int(config.get("export_last_n", 10)),
                fmt="markdown",
                copy_to_clipboard=True,
            )
            st.success(result)
        except Exception as e:
            st.error(f"Export failed: {e}")
with exp_col2:
    if st.button("📄 Export bugs (JSON only)", use_container_width=True):
        try:
            result = export_bugs(
                last_n=int(config.get("export_last_n", 10)),
                fmt="json",
                copy_to_clipboard=False,
            )
            st.success(result)
        except Exception as e:
            st.error(f"Export failed: {e}")
with exp_col3:
    if st.button("🔄 Reload bug log", use_container_width=True):
        st.rerun()

if bug_count == 0:
    st.info("No bug entries yet. Press Ctrl+Shift+F4 in the client (or in single-PC main_astro) to flag the current screen.")
else:
    recent = list_bug_observations(limit=20)
    for entry in recent:
        cat = entry.get("category", "")
        cat_badge = f"  🏷️ **{cat}**" if cat else ""
        with st.expander(
            f"🐞 {entry.get('id', '?')} — {entry.get('iso', '?')}{cat_badge}",
            expanded=False,
        ):
            ec1, ec2 = st.columns([2, 1])
            with ec1:
                if entry.get("description"):
                    st.markdown(f"**Auto-triage description:** {entry['description']}")
                if entry.get("user_note"):
                    st.markdown(f"**Note:** {entry['user_note']}")
                if entry.get("ocr_text"):
                    st.markdown("**OCR text:**")
                    st.code(entry["ocr_text"][:1200], language=None)
                if entry.get("vision_context"):
                    st.markdown(f"**Vision:** {entry['vision_context'][:500]}")
                if entry.get("active_window"):
                    st.caption(f"Active window: `{entry['active_window']}`")
            with ec2:
                if entry.get("frame"):
                    frame_abs = PROJECT_ROOT / entry["frame"]
                    if frame_abs.exists():
                        st.image(str(frame_abs), caption=entry["frame"], use_container_width=True)
                    else:
                        st.warning(f"Frame missing: {entry['frame']}")

# ---------------------------------------------------------------------
# Storage Threshold
# ---------------------------------------------------------------------

st.markdown("---")
st.header("📊 Dynamic Storage Threshold Metrics")

current_size = storage_watchdog.get_directory_size_mb()
st.metric(label="Current Project Workspace Footprint", value=f"{current_size:.2f} MB")
config["max_storage_allowed"] = float(st.slider(
    "Automated Safety Cleanup Trigger Threshold (MB)",
    min_value=100.0, max_value=2000.0,
    value=float(config.get("max_storage_allowed", 500.0)), step=50.0,
))
progress = min(current_size / max(config["max_storage_allowed"], 1.0), 1.0)
st.progress(progress, text=f"Storage Buffer Utilization: {progress * 100:.1f}%")
if current_size > config["max_storage_allowed"]:
    st.error(f"Workspace has breached the cap of {config['max_storage_allowed']}MB. Backend auto-purge is queued.")
else:
    st.info("Storage volumes are operating safely within normal configuration margins.")

if st.button("💾 Apply Storage Threshold Adjustments", use_container_width=True):
    save_config(config)
    st.toast("Storage thresholds synchronized!", icon="💾")
