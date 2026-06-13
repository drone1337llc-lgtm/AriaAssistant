"""
AstroBud AI server (runs on PC 2 — the dedicated AI compute node).

Receives screen frames + mic audio from a client (PC 1) over WebSocket,
runs the full AI pipeline (vision, OCR, LLM, TTS), and streams TTS audio
back. The client plays the audio + handles local-only tasks like
pyautogui typing, hotkey capture, and media keys.

Run:    python server.py
Test:   python server.py --selftest    (runs an in-process self-test)
Config: config.json (same as the single-PC version)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytesseract
import websockets

# Make this file work whether run as a module or as a script
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import lmstudio_client as lms
import tools
import transport

# Heavy imports (whisper, piper) deferred to lazy init below


# ---- Config ----

CONFIG_PATH = PROJECT_ROOT / "config.json"
LOG_FILE = PROJECT_ROOT / "daily_log.json"
MEMORY_DIR = PROJECT_ROOT / "astro_memory"
COLLECTION_NAME = "astro_episodic_memory"
DEFAULT_PORT = 8765

# Visual-delta threshold for triggering the vision model
VISUAL_DELTA_THRESHOLD = 5.0
FRAME_DROP_THRESHOLD = 30  # skip frames if more than this many are queued
_last_screen_hash: float | None = None


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "chat_model": "Lexi-Llama-3-8B-Uncensored",
        "code_model": "Qwen3-Coder-30B-A3B-Instruct",
        "triage_model": "Qwen2.5-Coder-1.5B-Instruct",
        "vision_model": "NousResearch_Nous-Hermes-2-Vision",
        "embedding_model": "nomic-embed-text-v2-moe",
        "helpfulness_level": "Reactive (Watches Errors)",
        "scan_interval": 10,
        "entertainment_interval": 30,
    }


def log_interaction(user_input: str, screen_context: str, bot_reply: str) -> None:
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
        "screen_context": screen_context[:1000],
        "bot_reply": bot_reply[:1000],
    })
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)


# ---- Whisper STT (lazy init) ----

_stt_model = None
_stt_lock = asyncio.Lock()


async def get_stt_model():
    global _stt_model
    async with _stt_lock:
        if _stt_model is None:
            import whisper
            print("[Server] Loading Whisper STT (base)...")
            _stt_model = await asyncio.to_thread(whisper.load_model, "base")
        return _stt_model


async def transcribe(wav_bytes: bytes) -> str:
    """Run Whisper on raw WAV bytes (16kHz mono int16)."""
    import tempfile
    import scipy.io.wavfile as sio
    import numpy as np
    import wave

    model = await get_stt_model()

    # Decode WAV
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        sr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    # Resample to 16kHz if needed
    if sr != 16000:
        # crude resample: simple linear interp
        ratio = 16000 / sr
        new_len = int(len(audio) * ratio)
        audio = np.interp(
            np.linspace(0, len(audio), new_len, endpoint=False),
            np.arange(len(audio)),
            audio,
        ).astype(np.float32)

    result = await asyncio.to_thread(model.transcribe, audio)
    return (result.get("text") or "").strip()


# ---- Piper TTS (lazy init) ----

_piper_proc_lock = asyncio.Lock()


async def synthesize_tts(text: str) -> bytes:
    """Generate WAV bytes via local Piper CLI. Returns the WAV file bytes."""
    import subprocess
    import tempfile

    clean = text.replace("*", "")
    if not clean.strip():
        return b""

    async with _piper_proc_lock:
        # Use a temp file for the output so we can return its bytes
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            out_path = tf.name
        try:
            cmd = ["piper", "--model", "en_US-lessac-medium.onnx", "--output_file", out_path]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate(input=clean.encode("utf-8"))
            with open(out_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass


# ---- ChromaDB memory ----

def get_chroma_collection():
    try:
        from chromadb import PersistentClient
    except ImportError:
        return None
    if not MEMORY_DIR.exists():
        MEMORY_DIR.mkdir(exist_ok=True)
    return PersistentClient(path=str(MEMORY_DIR)).get_or_create_collection(name=COLLECTION_NAME)


def query_relevant_memories(client, embedding_model: str, query: str, n: int = 2) -> str:
    collection = get_chroma_collection()
    if collection is None or collection.count() == 0:
        return ""
    try:
        embed = lms.embed(client, model=embedding_model, text=query)
        results = collection.query(query_embeddings=[embed], n_results=n)
        docs = results.get("documents", [[]])[0] if results else []
        return " ".join(docs)
    except Exception as e:
        print(f"[Server Memory] query failed: {e}")
        return ""


# ---- Frame processing (OCR + optional vision) ----

def process_frame(jpeg_bytes: bytes, client, vision_model: str) -> tuple[str, str]:
    """
    Decode a JPEG frame, run OCR (CPU) on it, and (only on visual delta)
    call the vision model. Returns (ocr_text, visual_context).
    """
    global _last_screen_hash
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return "", "Screen frame decode failed."
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ocr_text = pytesseract.image_to_string(gray).strip()[:2000]
    resized = cv2.resize(gray, (10, 10))
    current_hash = float(resized.mean())

    visual_context = "Screen layout appears stable."
    if _last_screen_hash is not None and abs(current_hash - _last_screen_hash) > VISUAL_DELTA_THRESHOLD:
        try:
            # Save the frame so the vision call can reference it via file path
            tmp_path = PROJECT_ROOT / "screen.png"
            cv2.imwrite(str(tmp_path), img)
            msg = lms.vision_message(
                "Describe any new UI alert window or major visual layout change in 1 concise sentence.",
                str(tmp_path),
            )
            response = lms.chat(
                client,
                model=vision_model,
                messages=[msg],
                max_tokens=120,
            )
            visual_context = response.choices[0].message.content.strip()[:500]
        except Exception as e:
            print(f"[Server Vision] call failed: {e}")
    _last_screen_hash = current_hash
    return ocr_text, visual_context


# ---- LLM turn (the heart of the server) ----

# Persona imports from main_astro for consistency
def _persona_for_mode(mode: str) -> str:
    from main_astro import persona_for_mode
    return persona_for_mode(mode)


async def run_turn_async(
    lms_client,
    cfg: dict,
    user_speech: str,
    ocr_text: str,
    visual_context: str,
    memory_context: str,
    triggered_by: str = "user",
) -> tuple[str, str]:
    """
    Run a full AI turn. Returns (final_text, tts_wav_bytes).
    `triggered_by` is 'user' (someone spoke / pressed F1) or 'auto' (timer).
    """
    chat_model = cfg.get("chat_model", "")
    mode = cfg.get("helpfulness_level", "")
    persona = _persona_for_mode(mode)

    if "Entertainment" in mode or "Co-pilot" in mode:
        user_prompt = (
            f"Current Desktop Screen (OCR text):\n```\n{ocr_text[:1500]}\n```\n\n"
            f"Visual / UI Context: {visual_context}\n\n"
            f"Relevant Past Interactions: {memory_context or '(none)'}\n\n"
            f"{'The user just asked: ' + user_speech if triggered_by == 'user' else 'The user has not spoken. Look at the visual + OCR context and decide if there is something worth saying. If not, reply with the single token SKIP.'}"
        )
    else:
        user_prompt = (
            f"Current Desktop Screen (OCR text):\n```\n{ocr_text}\n```\n\n"
            f"Visual / UI Context: {visual_context}\n\n"
            f"Relevant Past Interactions: {memory_context or '(none)'}\n\n"
            f"User Speech Input: {user_speech}"
        )

    messages = [
        {"role": "system", "content": persona},
        {"role": "user", "content": user_prompt},
    ]

    # First call: with tools
    try:
        response = await asyncio.to_thread(
            lms.chat,
            lms_client,
            model=chat_model,
            messages=messages,
            tools=tools.get_all_tool_schemas(),
            tool_choice="auto",
            temperature=0.4,
        )
    except Exception as e:
        return f"[Server] LLM call failed: {e}", b""
    assistant_msg = response.choices[0].message

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
            result_str = tools.execute_tool_call(tc.function.name, tc.function.arguments)
            messages.append(lms.tool_result_message(tc.id, result_str))
        try:
            final = await asyncio.to_thread(
                lms.chat,
                lms_client,
                model=chat_model,
                messages=messages,
                temperature=0.4,
            )
            reply_text = (final.choices[0].message.content or "").strip()
        except Exception as e:
            return f"[Server] LLM follow-up failed: {e}", b""
    else:
        reply_text = (assistant_msg.content or "").strip()

    # Entertainment SKIP handling
    if ("Entertainment" in mode or "Co-pilot" in mode) and reply_text.strip().upper() == "SKIP":
        return "", b""

    # Generate TTS in parallel-ish (await to_thread)
    wav_bytes = b""
    if reply_text:
        try:
            wav_bytes = await synthesize_tts(reply_text)
        except Exception as e:
            print(f"[Server] TTS failed: {e}")

    return reply_text, wav_bytes


# ---- Connection handler ----

class ClientState:
    """Per-connection state on the server side."""
    def __init__(self, websocket):
        self.ws = websocket
        self.remote_addr = getattr(websocket, "remote_address", ("?", 0))
        self.cfg = load_config()
        self.lms_client = lms.get_client()
        self.last_frame_ts = 0.0
        self.last_ocr = ""
        self.last_visual = "Screen not yet captured."
        self.muted = False  # TTS mute toggle (F2 hotkey)
        self.frame_queue: asyncio.Queue = asyncio.Queue(maxsize=FRAME_DROP_THRESHOLD)
        self.audio_queue: asyncio.Queue = asyncio.Queue(maxsize=8)

    async def send(self, msg: dict) -> None:
        try:
            await transport.send_json(self.ws, msg)
        except websockets.ConnectionClosed:
            raise

    async def send_text(self, text: str, level: str = "info") -> None:
        await self.send(transport.text_message(text, level))

    async def producer_loop(self) -> None:
        """Receive frames/audio/commands from the client and route them."""
        try:
            async for raw in self.ws:
                try:
                    msg = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode("utf-8"))
                except Exception as e:
                    print(f"[Server] Bad JSON from client: {e}")
                    continue

                mtype = msg.get("type")
                if mtype == transport.FRAME:
                    # Drop oldest if we're behind
                    if self.frame_queue.full():
                        try:
                            self.frame_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    await self.frame_queue.put(msg)
                elif mtype == transport.AUDIO:
                    if self.audio_queue.full():
                        try:
                            self.audio_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    await self.audio_queue.put(msg)
                elif mtype == transport.HOTKEY:
                    await self._handle_hotkey(msg.get("key", ""))
                elif mtype == transport.COMMAND:
                    await self._handle_command(msg)
                elif mtype == transport.PING:
                    await self.send({"type": transport.PONG, "ts": time.time()})
        except websockets.ConnectionClosed:
            print(f"[Server] Client {self.remote_addr} disconnected.")

    async def _handle_hotkey(self, key: str) -> None:
        key = key.upper()
        if key == "F1":
            await self.send_text("Summon hotkey pressed.")
            # Trigger a user turn — wait briefly for the next audio frame
            await self._handle_summon()
        elif key == "F2":
            self.muted = not self.muted
            await self.send_text(f"TTS {'MUTED' if self.muted else 'UNMUTED'}")
        elif key == "F3":
            await self._handle_describe()
        else:
            await self.send_text(f"Unknown hotkey: {key}")

    async def _handle_command(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "describe_screen":
            await self._handle_describe()
        elif cmd == "summon":
            await self._handle_summon()
        elif cmd == "flag_bug":
            await self._handle_flag_bug(msg)
        elif cmd == "export_bugs":
            await self._handle_export_bugs(msg)
        else:
            await self.send_text(f"Unknown command: {cmd}")

    async def _handle_flag_bug(self, msg: dict) -> None:
        """Persist a bug/observation entry. The payload includes a fresh frame
        captured by the client when the user pressed Ctrl+Shift+F4. Runs the
        small triage model to auto-categorize + describe the issue."""
        try:
            jpeg_bytes = transport.get_b64_data(msg)
        except Exception as e:
            await self.send_text(f"flag_bug: bad payload ({e})")
            return

        # Save the frame to beta_feedback/screens/
        from tools import BUG_SCREENS_DIR, log_bug_observation
        import time
        BUG_SCREENS_DIR.mkdir(parents=True, exist_ok=True)
        bug_id = f"bug_{int(time.time())}_{os.getpid() % 10000:04d}"
        frame_path = BUG_SCREENS_DIR / f"{bug_id}.png"
        with open(frame_path, "wb") as f:
            f.write(jpeg_bytes)

        # Run OCR on the saved frame so the bug entry has the on-screen text
        try:
            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ocr_text = pytesseract.image_to_string(gray).strip()[:2000]
        except Exception as e:
            ocr_text = f"(OCR failed: {e})"

        # Auto-triage via the small model (1.5B coder or configured triage brain)
        category = ""
        description = ""
        if self.cfg.get("triage_enabled", True):
            category, description = await self._auto_triage(ocr_text, self.last_visual or "Frame captured at flag time.")

        # Log it (synchronous; this is rare and small)
        try:
            summary = log_bug_observation(
                ocr_text=ocr_text,
                vision_context=self.last_visual or "Frame captured at flag time.",
                user_note="",
                frame_path=str(frame_path),
                category=category,
                description=description,
            )
        except Exception as e:
            summary = f"log_bug_observation failed: {e}"

        await self.send(transport.bug_logged_message(bug_id, summary))
        # Verbose spoken confirmation includes the category so the user
        # hears the triage result without needing to look at the dashboard.
        speak_bits = [f"Bug {bug_id} logged."]
        if category:
            speak_bits.append(f"Category: {category}.")
        if description:
            speak_bits.append(description)
        speak_text = " ".join(speak_bits)
        await self.send_text(f"Bug {bug_id} saved — {category or 'uncategorized'}: {description or '(no description)'}")
        if not self.muted:
            wav = await synthesize_tts(speak_text)
            if wav:
                await self.send(transport.tts_audio_message(wav))

    async def _auto_triage(self, ocr_text: str, vision_context: str) -> tuple[str, str]:
        """Run the small triage model to categorize + describe a flagged bug.
        Returns (category, description) — empty strings if anything fails."""
        triage_model = self.cfg.get("triage_model") or self.cfg.get("chat_model", "")
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
            f"Vision context:\n{vision_context[:500]}"
        )
        try:
            response = await asyncio.to_thread(
                lms.chat,
                self.lms_client,
                model=triage_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.1,
            )
            raw = (response.choices[0].message.content or "").strip()
            import re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                return (
                    str(data.get("category", "")).strip(),
                    str(data.get("description", "")).strip(),
                )
            return "", raw[:200]
        except Exception as e:
            print(f"[Server Triage] Failed: {e}")
            return "", ""

    async def _handle_export_bugs(self, msg: dict) -> None:
        from tools import export_bugs
        last_n = int(msg.get("last_n", 10))
        fmt = msg.get("fmt", "markdown")
        copy = bool(msg.get("copy_to_clipboard", True))
        try:
            result = await asyncio.to_thread(export_bugs, last_n, fmt, copy)
        except Exception as e:
            result = f"Export failed: {e}"
        await self.send_text(result)
        if not self.muted:
            wav = await synthesize_tts("Bugs exported.")
            if wav:
                await self.send(transport.tts_audio_message(wav))

    async def _handle_summon(self) -> None:
        """Grab the next audio chunk (with a short wait) and run a turn."""
        try:
            audio_msg = await asyncio.wait_for(self.audio_queue.get(), timeout=2.0)
        except asyncio.TimeoutError:
            await self.send_text("No audio received for summon.")
            return
        await self._run_audio_turn(audio_msg, triggered_by="user")

    async def _handle_describe(self) -> None:
        """One-shot description of the latest screen state."""
        if not self.last_ocr and self.last_visual == "Screen not yet captured.":
            await self.send_text("No screen frame received yet.")
            return
        summary = f"OCR: {self.last_ocr[:400]}\nVision: {self.last_visual}"
        await self.send_text(summary)
        # Also speak it
        if not self.muted and self.last_visual:
            wav_bytes = await synthesize_tts(self.last_visual)
            if wav_bytes:
                await self.send(transport.tts_audio_message(wav_bytes))

    async def _run_audio_turn(self, audio_msg: dict, triggered_by: str) -> None:
        try:
            wav_bytes_in = transport.get_b64_data(audio_msg)
        except Exception as e:
            await self.send_text(f"Bad audio payload: {e}")
            return

        await self.send_text("Transcribing audio...")
        text = await transcribe(wav_bytes_in)
        if not text:
            await self.send_text("*Whir* I didn't catch that.")
            return
        await self.send(transport.transcript_message(text))
        await self._run_text_turn(text, triggered_by=triggered_by)

    async def _run_text_turn(self, user_text: str, triggered_by: str = "user") -> None:
        cfg = self.cfg
        embed_model = cfg.get("embedding_model", "nomic-embed-text-v2-moe")
        memory_context = query_relevant_memories(self.lms_client, embed_model, user_text, n=2)
        await self.send_text(f"Thinking (mode={cfg.get('helpfulness_level')[:24]})...")
        reply_text, wav_bytes = await run_turn_async(
            self.lms_client,
            cfg,
            user_text,
            self.last_ocr,
            self.last_visual,
            memory_context,
            triggered_by=triggered_by,
        )
        if not reply_text:
            return
        await self.send_text(f"AstroBud: {reply_text}")
        if wav_bytes and not self.muted:
            await self.send(transport.tts_audio_message(wav_bytes))
        log_interaction(user_text, f"OCR={self.last_ocr[:300]}; VIS={self.last_visual}", reply_text)

    async def consumer_loop(self) -> None:
        """
        Pop frames, run OCR+vision to keep `last_ocr` and `last_visual` fresh.
        In entertainment mode, also pop audio opportunistically and run a turn.
        """
        last_auto_turn = 0.0
        while True:
            try:
                msg = await asyncio.wait_for(self.frame_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Idle tick — possibly fire an auto turn in entertainment mode
                mode = self.cfg.get("helpfulness_level", "")
                if "Entertainment" in mode or "Co-pilot" in mode:
                    interval = int(self.cfg.get("entertainment_interval", 30))
                    if time.time() - last_auto_turn > interval:
                        last_auto_turn = time.time()
                        try:
                            audio_msg = await asyncio.wait_for(self.audio_queue.get(), timeout=0.1)
                            await self._run_audio_turn(audio_msg, triggered_by="auto")
                        except asyncio.TimeoutError:
                            # No audio — but we can still do a "describe only" turn
                            await self._run_text_turn("", triggered_by="auto")
                continue

            # Decode + process frame (CPU-bound, run in thread)
            jpeg_bytes = transport.get_b64_data(msg)
            try:
                ocr_text, visual_context = await asyncio.to_thread(
                    process_frame,
                    jpeg_bytes,
                    self.lms_client,
                    self.cfg.get("vision_model", self.cfg.get("chat_model", "")),
                )
                self.last_ocr = ocr_text
                self.last_visual = visual_context
            except Exception as e:
                print(f"[Server] Frame processing error: {e}")

    async def run(self) -> None:
        print(f"[Server] Client connected: {self.remote_addr}")
        await self.send_text(f"AstroBud server online. Models: {lms.list_loaded_models(self.lms_client)}")
        try:
            await asyncio.gather(self.producer_loop(), self.consumer_loop())
        except websockets.ConnectionClosed:
            pass
        finally:
            print(f"[Server] Connection closed: {self.remote_addr}")


# ---- Server bootstrap ----

async def handle_connection(ws) -> None:
    state = ClientState(ws)
    await state.run()


async def main_async(port: int) -> None:
    print(f"[Server] Starting AstroBud AI server on 0.0.0.0:{port}")
    # LM Studio connectivity check
    info = lms.smoke_test(lms.get_client())
    if info["server_reachable"]:
        print(f"[Server] LM Studio reachable. Models loaded: {info['models']}")
    else:
        print(f"[Server] WARNING: LM Studio not reachable. Detail: {info.get('error')}")

    async with websockets.serve(handle_connection, "0.0.0.0", port, max_size=64 * 1024 * 1024):
        print(f"[Server] Listening on ws://0.0.0.0:{port}/  (Ctrl+C to stop)")
        await asyncio.Future()  # run forever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="WebSocket port")
    parser.add_argument("--selftest", action="store_true", help="Run an in-process self-test then exit")
    args = parser.parse_args()

    if args.selftest:
        # Sanity: check that we can build all messages
        m = transport.frame_message(b"\xff\xd8\xff\xe0", 100, 100)
        assert m["type"] == transport.FRAME
        m2 = transport.tts_audio_message(b"RIFF")
        assert m2["type"] == transport.TTS_AUDIO
        # And that the protocol file imports cleanly
        print("Self-test OK.")
        return

    try:
        asyncio.run(main_async(args.port))
    except KeyboardInterrupt:
        print("\n[Server] Shutting down.")


if __name__ == "__main__":
    main()
