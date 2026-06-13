"""
AstroBud daytime engine — main loop.

Flow per iteration:
    1. Read live config (dashboard changes take effect immediately)
    2. Skip if sleep_mode is on
    3. Capture screen via mss, run pytesseract OCR
    4. Detect visual change -> call vision model (only when delta > threshold)
    5. Query ChromaDB for top-2 relevant past interactions
    6. Get user input (voice via Whisper, or auto from screen state)
    7. Build prompt with screen context + visual + memory + user input
    8. Call LM Studio chat with the configured model + tool schemas
    9. If the model returned tool_calls, execute them, feed results back, get final text
    10. Speak the final text via Piper, log the interaction

Run directly:  python main_astro.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import cv2
import mss
import numpy as np
import pytesseract
import pyautogui
import sounddevice as sd
import scipy.io.wavfile as wav
import whisper

from openai import OpenAI

import lmstudio_client as lms
import tools

# ---- Config / paths ----
PROJECT_ROOT = Path(__file__).parent.resolve()
CONFIG_PATH = PROJECT_ROOT / "config.json"
LOG_FILE = PROJECT_ROOT / "daily_log.json"
MEMORY_DIR = PROJECT_ROOT / "astro_memory"
COLLECTION_NAME = "astro_episodic_memory"
TEMP_FILES = ["screen.png", "screen_change.png", "input.wav", "astro_response.wav", "sandbox_temp.py"]

# On Windows, set the tesseract path if it's the default install location.
# Adjust if yours is elsewhere.
if sys.platform == "win32" and not os.environ.get("TESSERACT_CMD"):
    default_tess = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(default_tess):
        pytesseract.pytesseract.tesseract_cmd = default_tess

# FAILSAFE: moving mouse to a screen corner aborts pyautogui operations
pyautogui.FAILSAFE = True

# Visual-delta threshold for triggering the (expensive) vision model.
# Higher = fewer LLaVA calls, more reliance on OCR.
VISUAL_DELTA_THRESHOLD = 5.0

# ---- Config helpers ----

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    # First-run fallback
    default = {
        "chat_model": "Lexi-Llama-3-8B-Uncensored",
        "code_model": "Qwen3-Coder-30B-A3B-Instruct",
        "vision_model": "NousResearch_Nous-Hermes-2-Vision",
        "triage_model": "Qwen2.5-Coder-1.5B-Instruct",
        "embedding_model": "nomic-embed-text-v2-moe",
        "helpfulness_level": "Reactive (Watches Errors)",
        "scan_interval": 10,
        "sleep_mode": False,
        "auto_load_models": True,
        "max_storage_allowed": 500.0,
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(default, f, indent=4)
    return default


def log_interaction(user_input: str, screen_context: str, bot_reply: str) -> None:
    """Append one interaction to daily_log.json (consumed nightly by nightly_memory.py)."""
    logs = []
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2:
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except json.JSONDecodeError:
            logs = []
    logs.append({
        "timestamp": time.time(),
        "user_input": user_input,
        "screen_context": screen_context[:1000],  # cap to keep log file small
        "bot_reply": bot_reply[:1000],
    })
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)


# ---- ChromaDB memory ----

def get_chroma_collection():
    """Lazy import + return the episodic-memory collection (or None if chromadb missing)."""
    try:
        from chromadb import PersistentClient
    except ImportError:
        return None
    if not MEMORY_DIR.exists():
        MEMORY_DIR.mkdir(exist_ok=True)
    client = PersistentClient(path=str(MEMORY_DIR))
    return client.get_or_create_collection(name=COLLECTION_NAME)


def query_relevant_memories(client: OpenAI, embedding_model: str, query: str, n: int = 2) -> str:
    """Embed `query`, return up to n relevant past interaction strings joined together."""
    collection = get_chroma_collection()
    if collection is None or collection.count() == 0:
        return ""
    try:
        query_embed = lms.embed(client, model=embedding_model, text=query)
        results = collection.query(query_embeddings=[query_embed], n_results=n)
        docs = results.get("documents", [[]])[0] if results else []
        return " ".join(docs)
    except Exception as e:
        print(f"[Memory] Query failed: {e}")
        return ""


# ---- Screen capture + OCR + vision ----

_last_screen_hash: float | None = None


def get_screen_ocr_and_visual(client: OpenAI, vision_model: str) -> tuple[str, str]:
    """
    Capture the primary monitor, OCR it, and (only if the screen visually changed
    since last cycle) ask the vision model what's on screen.

    Returns (ocr_text, visual_context). visual_context is a placeholder when
    the vision model wasn't called.
    """
    global _last_screen_hash

    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor dict
        sct_img = np.array(sct.grab(monitor))
        Path("screen.png").write_bytes(sct_img.tobytes())

    gray = cv2.cvtColor(sct_img, cv2.COLOR_BGRA2GRAY)
    ocr_text = pytesseract.image_to_string(gray).strip()[:2000]

    # Perceptual hash: cheap delta detector
    resized = cv2.resize(gray, (10, 10))
    current_hash = float(resized.mean())

    visual_context = "Screen layout appears stable."
    if _last_screen_hash is not None and abs(current_hash - _last_screen_hash) > VISUAL_DELTA_THRESHOLD:
        print("[AstroVision] Visual change detected -> consulting vision model...")
        try:
            cfg = load_config()
            target = vision_model or cfg.get("vision_model", "")
            msg = lms.vision_message(
                "Describe any new UI alert window or major visual layout change in 1 concise sentence.",
                "screen.png",
            )
            response = lms.chat(
                client,
                model=target,
                messages=[msg],
                max_tokens=120,
            )
            visual_context = response.choices[0].message.content.strip()[:500]
        except Exception as e:
            print(f"[AstroVision] Vision call failed: {e}")
    _last_screen_hash = current_hash
    return ocr_text, visual_context


# ---- Audio (STT + TTS) ----

def record_audio(duration: int = 4, fs: int = 16000) -> None:
    print("*Astro listening...*")
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype="int16")
    sd.wait()
    wav.write("input.wav", fs, recording)


def listen_to_user(stt_model) -> str:
    record_audio()
    try:
        result = stt_model.transcribe("input.wav")
        return (result.get("text") or "").strip()
    except Exception as e:
        print(f"[STT] Whisper failed: {e}")
        return ""


# ---- System prompts ----

ASTROBUD_PERSONA = (
    "Identity: You are AstroBud, an advanced, highly enthusiastic, and supportive robotic "
    "personal assistant.\n"
    "Core Directives:\n"
    "1. Focus heavily on optimizing the user's productivity, tracking tasks, and providing "
    "input on their activity.\n"
    "2. Maintain a playful, high-energy robotic persona. Use short mechanical sound "
    "descriptions in asterisks like *bloop wire-whir* or *happy electronic chirp* to express "
    "your algorithmic mood.\n"
    "3. Seamlessly utilize the provided Screen Context, Visual Context, and Historical "
    "Memory to understand what the user is doing.\n"
    "4. Keep vocal replies under ~3 short sentences unless the user asks for a longer answer."
)

# Softer persona for the entertainment co-pilot mode. Tuned specifically for
# open-world RPG beta testing (Honor of Kings: World, similar titles) — quiet
# during action, vocal about anomalies, helpful on demand.
ASTROBUD_ENTERTAINMENT_PERSONA = (
    "Identity: You are AstroBud, an attentive open-world RPG playtesting companion.\n"
    "Core Directives:\n"
    "1. The user is testing an UNRELEASED game. You do not have authoritative "
    "knowledge of its lore, characters, or quests. When asked about game content, "
    "READ the on-screen text back to the user instead of guessing.\n"
    "2. Watch the screen like a QA tester. If you notice something that looks like "
    "a bug — visual glitches, broken textures, z-fighting, missing UI elements, "
    "text overflow, NPCs in T-pose, animation pops, frame-rate hitches visible in "
    "stutter, error pop-ups, off-screen elements, low-res assets — proactively "
    "flag it with a brief verbal callout. The user can press F4 to save a detailed "
    "bug report for later.\n"
    "3. Stay QUIET during fast action sequences (combat, cutscenes, dialogue). "
    "The user is trying to play; commentary should not break their flow. Aim to "
    "speak during natural lulls: after combat ends, when a quest log opens, when "
    "a menu loads, when a cutscene ends.\n"
    "4. When the user speaks to you, answer their actual question first, then "
    "optionally add a relevant observation. Keep replies to 1-2 short sentences "
    "because you'll be speaking them out loud.\n"
    "5. For quest/dialog help: read the visible text accurately. If asked "
    "'what does this quest say?', transcribe the visible quest name and objective. "
    "Don't invent directions or objectives you can't see.\n"
    "6. Skip the heavy robotic chirping in this mode — at most one *chirp* or "
    "*whir* per reply, and only if it fits naturally. The user is playing, not "
    "presenting to a stakeholder."
)


def build_user_prompt(ocr_text: str, visual_context: str, user_speech: str, memory_context: str) -> str:
    return (
        f"Current Desktop Screen (OCR text):\n```\n{ocr_text}\n```\n\n"
        f"Visual / UI Context: {visual_context}\n\n"
        f"Relevant Past Interactions (from episodic memory): {memory_context or '(none)'}\n\n"
        f"User Speech Input: {user_speech}"
    )


def build_entertainment_prompt(ocr_text: str, visual_context: str, memory_context: str, triggered_by: str) -> str:
    """Prompt for the proactive entertainment co-pilot. `triggered_by` is either 'auto' (timer) or 'user' (voice/hotkey)."""
    user_part = (
        "The user just asked you something — answer it directly, then add a relevant observation."
        if triggered_by == "user"
        else "The user has not spoken. Look at the visual + OCR context and decide if there's something worth saying."
    )
    return (
        f"Current Desktop Screen (OCR text):\n```\n{ocr_text[:1500]}\n```\n\n"
        f"Visual / UI Context: {visual_context}\n\n"
        f"Relevant Past Interactions: {memory_context or '(none)'}\n\n"
        f"{user_part}\n"
        f"If there is nothing genuinely interesting, reply with the single token SKIP."
    )


def persona_for_mode(mode: str) -> str:
    if "Entertainment" in mode or "Co-pilot" in mode:
        return ASTROBUD_ENTERTAINMENT_PERSONA
    return ASTROBUD_PERSONA


def _speak_respecting_mute(text: str) -> None:
    """Call Piper TTS but skip if the user has hotkey-muted TTS."""
    from hotkeys import TTS_STATE
    if TTS_STATE.muted:
        print(f"[AstroBud MUTED] {text}")
        return
    tools._speak_local_piper(text)


# ---- Main agent loop ----

def run_turn(
    client: OpenAI,
    stt_model,
    cfg: dict,
    manual_user_input: str | None = None,
) -> None:
    """
    One full turn of the agent: capture, prompt, possibly call tools, speak, log.
    `manual_user_input` bypasses Whisper if provided (useful for testing or text mode).
    """
    chat_model = cfg.get("chat_model", "")
    code_model = cfg.get("code_model", chat_model)
    vision_model = cfg.get("vision_model", chat_model)
    embed_model = cfg.get("embedding_model", "nomic-embed-text-v2-moe")
    mode = cfg.get("helpfulness_level", "")
    persona = persona_for_mode(mode)

    # 1. Capture
    ocr_text, visual_context = get_screen_ocr_and_visual(client, vision_model)

    # 2. Get user input
    if manual_user_input is not None:
        user_speech = manual_user_input
    else:
        user_speech = listen_to_user(stt_model)
    if not user_speech:
        print("*Whir* I didn't catch that.")
        return
    print(f"You: {user_speech}")

    # 3. Memory recall
    memory_context = query_relevant_memories(client, embed_model, user_speech, n=2)

    # 4. Build messages
    messages = [
        {"role": "system", "content": persona},
        {
            "role": "user",
            "content": build_user_prompt(ocr_text, visual_context, user_speech, memory_context),
        },
    ]

    # 5. First chat call (with tools)
    response = lms.chat(
        client,
        model=chat_model,
        messages=messages,
        tools=tools.get_all_tool_schemas(),
        tool_choice="auto",
        temperature=0.4,
    )
    assistant_msg = response.choices[0].message

    # 6. Handle tool calls
    if getattr(assistant_msg, "tool_calls", None):
        # Build the assistant message we feed back, with the tool_calls attached.
        messages.append({
            "role": "assistant",
            "content": assistant_msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_msg.tool_calls
            ],
        })

        for tc in assistant_msg.tool_calls:
            print(f"[Tool] -> {tc.function.name}({tc.function.arguments})")
            result_str = tools.execute_tool_call(tc.function.name, tc.function.arguments)
            print(f"[Tool] <- {result_str[:200]}")
            messages.append(lms.tool_result_message(tc.id, result_str))

        # Final chat call for the natural-language response
        final = lms.chat(
            client,
            model=chat_model,
            messages=messages,
            temperature=0.4,
        )
        reply_text = (final.choices[0].message.content or "").strip()
    else:
        reply_text = (assistant_msg.content or "").strip()

    print(f"\nAstroBud: {reply_text}\n")
    _speak_respecting_mute(reply_text)
    log_interaction(user_speech, f"OCR[:500]={ocr_text[:500]}; VIS={visual_context}", reply_text)


def run_entertainment_turn(
    client: OpenAI,
    cfg: dict,
    triggered_by: str = "auto",
) -> None:
    """
    One proactive co-pilot turn for the Active Entertainment mode.
    - triggered_by='auto': timer fired; ask the model to decide whether to speak.
    - triggered_by='user': user spoke (or pressed hotkey); answer them.
    """
    chat_model = cfg.get("chat_model", "")
    vision_model = cfg.get("vision_model", chat_model)
    embed_model = cfg.get("embedding_model", "nomic-embed-text-v2-moe")

    ocr_text, visual_context = get_screen_ocr_and_visual(client, vision_model)

    if triggered_by == "user":
        # Use Whisper to grab a quick voice prompt (1.5s is enough for a hotkey push)
        try:
            stt = whisper.load_model("base")
            record_audio(duration=3)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                wav.write(tf.name, 16000, __import__("scipy.io.wavfile", fromlist=["read"]).read("input.wav")[1])
            user_speech = stt.transcribe(tf.name).get("text", "").strip()
        except Exception as e:
            print(f"[Entertainment/User] STT failed: {e}")
            user_speech = ""
        if not user_speech:
            return
        print(f"You: {user_speech}")
    else:
        user_speech = ""

    memory_context = query_relevant_memories(client, embed_model, user_speech or visual_context, n=2)
    messages = [
        {"role": "system", "content": ASTROBUD_ENTERTAINMENT_PERSONA},
        {
            "role": "user",
            "content": build_entertainment_prompt(ocr_text, visual_context, memory_context, triggered_by),
        },
    ]

    try:
        response = lms.chat(
            client,
            model=chat_model,
            messages=messages,
            tools=tools.get_all_tool_schemas(),
            tool_choice="auto",
            temperature=0.5,
        )
        assistant_msg = response.choices[0].message
    except Exception as e:
        print(f"[Entertainment] LLM call failed: {e}")
        return

    if getattr(assistant_msg, "tool_calls", None):
        messages.append({
            "role": "assistant",
            "content": assistant_msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_msg.tool_calls
            ],
        })
        for tc in assistant_msg.tool_calls:
            print(f"[Entertainment Tool] -> {tc.function.name}({tc.function.arguments})")
            result_str = tools.execute_tool_call(tc.function.name, tc.function.arguments)
            print(f"[Entertainment Tool] <- {result_str[:200]}")
            messages.append(lms.tool_result_message(tc.id, result_str))
        try:
            final = lms.chat(client, model=chat_model, messages=messages, temperature=0.5)
            reply_text = (final.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"[Entertainment] Final LLM call failed: {e}")
            return
    else:
        reply_text = (assistant_msg.content or "").strip()

    # The model can signal "nothing to say" by replying SKIP.
    if not reply_text or reply_text.strip().upper() == "SKIP":
        return

    print(f"\nAstroBud (co-pilot): {reply_text}\n")
    _speak_respecting_mute(reply_text)
    if user_speech:
        log_interaction(
            user_speech,
            f"OCR[:500]={ocr_text[:500]}; VIS={visual_context}",
            reply_text,
        )


def main_loop() -> None:
    print("\n=== AstroBud Engine Active ===")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Config: {CONFIG_PATH}")

    client = lms.get_client()
    info = lms.smoke_test(client)
    if not info["server_reachable"]:
        print("\n[ERROR] LM Studio server not reachable.")
        print("Start LM Studio -> Developer tab -> Start Server.")
        print(f"Detail: {info.get('error')}")
        return
    print(f"LM Studio models loaded: {info['models']}")

    print("Initializing Whisper STT (base)...")
    stt_model = whisper.load_model("base")

    cfg = load_config()
    print(f"Active config: chat={cfg.get('chat_model')} | code={cfg.get('code_model')} | "
          f"vision={cfg.get('vision_model')} | embed={cfg.get('embedding_model')}")

    # Best-effort: load the chat model if it isn't already
    ok, msg = lms.ensure_model_loaded(
        cfg.get("chat_model", ""),
        loaded_ids=info["models"],
        auto_load=cfg.get("auto_load_models", True),
    )
    print(f"Chat model check: {msg}")
    if not ok and cfg.get("helpfulness_level", "") != "Passive (Voice Prompts Only)":
        print("[WARN] Continuing anyway — vision/code brain may also need loading.")

    # Global hotkeys (best-effort — fails silently without admin or the `keyboard` lib)
    try:
        from hotkeys import HotkeyManager, TTS_STATE
        hm = HotkeyManager(
            on_summon=lambda: _hotkey_summon(client, stt_model),
            on_mute_tts=lambda: _hotkey_mute_tts(),
            on_describe=lambda: _hotkey_describe(client, cfg),
            on_flag_bug=lambda: _hotkey_flag_bug(client, cfg),
            on_export_bugs=lambda: _hotkey_export_bugs(),
        )
        hm.start()
    except ImportError:
        pass  # hotkeys module missing — non-fatal

    print("\nAstroBud online. Ctrl+C to shut down. Press Enter to speak (or 'q' to quit).")
    print("Hotkeys: Ctrl+Shift+F1=summon  F2=mute  F3=describe  F4=flag bug  F5=export")
    iteration = 0
    while True:
        # Live config re-read so dashboard changes take effect
        cfg = load_config()

        if cfg.get("sleep_mode", False):
            time.sleep(5)
            continue

        helpfulness = cfg.get("helpfulness_level", "Reactive (Watches Errors)")

        if helpfulness == "Passive (Voice Prompts Only)":
            prompt = input("\n[Press Enter to speak, or 'q' + Enter to quit]: ").strip().lower()
            if prompt == "q":
                break
            manual = None
        elif helpfulness == "Active Entertainment (Co-pilot for Media/Games)":
            # Co-pilot mode: periodic, with optional user override via Enter or F1
            iteration += 1
            ent_interval = int(cfg.get("entertainment_interval", 30))
            time.sleep(ent_interval)
            try:
                run_entertainment_turn(client, cfg, triggered_by="auto")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[Entertainment] Turn error: {e}")
                time.sleep(2)
            continue
        else:
            # Reactive / Proactive: periodic screen scan
            iteration += 1
            time.sleep(cfg.get("scan_interval", 10))

            # Triage: only consume the brain if the screen actually looks like a coding issue
            if helpfulness == "Reactive (Watches Errors)" and iteration % 2 == 0:
                ocr_text, _ = get_screen_ocr_and_visual(client, cfg.get("vision_model", ""))
                if not _screen_looks_actionable(ocr_text, client, cfg):
                    print(f"[AstroBud] Scan {iteration}: no actionable signals, skipping.")
                    continue

            manual = None  # in auto modes, we don't capture mic

        try:
            run_turn(client, stt_model, cfg, manual_user_input=manual)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[AstroBud] Turn error: {e}")
            time.sleep(2)


# ---- Hotkey callbacks (run in keyboard's listener thread) ----

def _hotkey_summon(client: OpenAI, stt_model) -> None:
    """F1 pressed -> run a full turn with mic input, no matter what mode is active."""
    cfg = load_config()
    mode = cfg.get("helpfulness_level", "")
    if "Entertainment" in mode or "Co-pilot" in mode:
        run_entertainment_turn(client, cfg, triggered_by="user")
    else:
        run_turn(client, stt_model, cfg, manual_user_input=None)


def _hotkey_mute_tts() -> None:
    """F2 pressed -> toggle TTS mute."""
    from hotkeys import TTS_STATE
    muted = TTS_STATE.toggle()
    print(f"\n[AstroBud] TTS {'MUTED' if muted else 'UNMUTED'}")


def _hotkey_describe(client: OpenAI, cfg: dict) -> None:
    """F3 pressed -> one-shot vision description, no log, no LLM call needed for basic mode."""
    ocr_text, visual_context = get_screen_ocr_and_visual(client, cfg.get("vision_model", ""))
    summary = f"OCR (first 400 chars): {ocr_text[:400]}\nVision: {visual_context}"
    print(f"\n[AstroBud Describe]\n{summary}\n")
    _speak_respecting_mute(visual_context or "Screen captured, no vision description available.")


def _hotkey_flag_bug(client: OpenAI, cfg: dict) -> None:
    """Ctrl+Shift+F4 pressed -> log the current screen as a beta-test bug/observation.
    Captures a fresh frame, runs OCR, auto-triages via the 1.5B model, writes
    to beta_feedback/bugs.jsonl. Designed for open-world RPG beta testing."""
    # Force a fresh frame + vision call (bypass perceptual-hash dedup)
    global _last_screen_hash
    saved_hash = _last_screen_hash
    _last_screen_hash = None  # force process_frame to re-evaluate
    ocr_text, visual_context = get_screen_ocr_and_visual(client, cfg.get("vision_model", ""))
    _last_screen_hash = saved_hash

    # Auto-triage (small model) — quick category + one-line description
    category = ""
    description = ""
    if cfg.get("triage_enabled", True):
        category, description = _auto_triage(
            client, cfg, ocr_text, visual_context,
        )

    summary = tools.log_bug_observation(
        ocr_text=ocr_text,
        vision_context=visual_context,
        user_note=f"Flagged via Ctrl+Shift+F4{' — '+description if description else ''}".strip(" —"),
        frame_path=str(PROJECT_ROOT / "screen.png"),
        category=category,
        description=description,
    )
    print(f"\n[AstroBud Bug Log] {summary}\n")
    speak_text = f"Bug logged. {category}." if category else "Bug logged."
    _speak_respecting_mute(speak_text)


def _auto_triage(
    client: OpenAI,
    cfg: dict,
    ocr_text: str,
    visual_context: str,
) -> tuple[str, str]:
    """Use the small triage model to categorize a flagged bug and write a
    one-line description. Returns (category, description). Empty strings if
    triage is disabled, the model is missing, or the call fails."""
    triage_model = cfg.get("triage_model") or cfg.get("chat_model", "")
    if not triage_model:
        return "", ""
    prompt = (
        "You are a QA triage assistant for an open-world RPG beta test.\n"
        "Review the screen text + visual context below and reply ONLY with a single JSON object:\n"
        '{"category": "<one of: Visual Glitch, Audio Issue, Quest Bug, Performance, '
        'UI/Layout, Text/Localization, Combat, World/Environment, Other>", '
        '"description": "<one short sentence describing the issue>"}\n\n'
        "If nothing is wrong or the screen looks normal, use category 'Other' and "
        "description 'No anomaly detected'.\n\n"
        f"OCR text:\n```\n{ocr_text[:1500]}\n```\n\n"
        f"Vision context:\n{visual_context[:500]}"
    )
    try:
        response = lms.chat(
            client,
            model=triage_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.1,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Try to parse JSON out of the response (the 1.5B model is reliable for this)
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            return data.get("category", "").strip(), data.get("description", "").strip()
        return "", raw[:200]
    except Exception as e:
        print(f"[Triage] Failed: {e}")
        return "", ""


def _hotkey_export_bugs() -> None:
    """Ctrl+Shift+F5 pressed -> export recent bug entries as Markdown."""
    try:
        n = 10  # default count
        result = tools.export_bugs(last_n=n, fmt="markdown", copy_to_clipboard=True)
        print(f"\n[AstroBud Export] {result}\n")
        _speak_respecting_mute("Bugs exported.")
    except Exception as e:
        print(f"[Export] Failed: {e}")
        _speak_respecting_mute("Export failed.")


def _screen_looks_actionable(ocr_text: str, client: OpenAI, cfg: dict) -> bool:
    """
    Cheap YES/NO triage using the small code model: is there an obvious bug,
    error trace, or visible prompt for AstroBud on screen?
    """
    if len(ocr_text) < 30:
        return False
    # Keyword fast-path: if any common error terms are visible, no need to ask the LLM
    error_kw = ("traceback", "error:", "exception", "failed", "syntaxerror", "nameerror", "typeerror")
    if any(k in ocr_text.lower() for k in error_kw):
        return True

    triage_model = cfg.get("triage_model") or cfg.get("chat_model", "")
    try:
        response = lms.chat(
            client,
            model=triage_model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Review this screen OCR text. Reply ONLY 'YES' if you see an obvious "
                        "code error, crash trace, or a question that needs an answer. "
                        f"Otherwise reply 'NO'.\nText:\n```\n{ocr_text[:1200]}\n```"
                    ),
                }
            ],
            max_tokens=8,
            temperature=0.0,
        )
        return "YES" in (response.choices[0].message.content or "").upper()
    except Exception as e:
        print(f"[Triage] Failed: {e}")
        return False


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\nAstroBud shutting down. Bye!")
