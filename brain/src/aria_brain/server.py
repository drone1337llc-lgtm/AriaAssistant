"""FastAPI server — exposes the Brain over HTTP + WebSocket.

Routes:
  GET  /health           liveness + memory stats + mood
  GET  /mood             current mood only
  POST /message          send a text message, get a text reply
  WS   /chat             bidirectional streaming (same semantics as /message)
  POST /reflect          trigger a reflection tick (used by the tray menu)
  POST /shutdown         graceful shutdown
  POST /voice            accept audio, transcribe via Whisper, route to brain (Phase 3)
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import wave
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aria_brain import brain, memory, mood, personality, reflection
from aria_brain import voice as voice_mod
from aria_brain.config import ARIA_BRAIN_HOST, ARIA_BRAIN_PORT, TTS_URL

# Streaming TTS endpoint = the /tts_stream sibling of the configured /tts URL.
TTS_STREAM_URL = (TTS_URL[: -len("/tts")] + "/tts_stream") if TTS_URL.endswith("/tts") else (TTS_URL + "_stream")
# Mic capture format the front-end streams up (raw PCM16 mono).
VOICE_IN_RATE = 16000

log = logging.getLogger("aria_brain.server")


# --- Request / response schemas --------------------------------------------

class MessageIn(BaseModel):
    text: str = Field(..., description="The user's message text.")
    source: str = Field("api", description="Where the message came from (chat, tray, telegram, voice).")
    speak: bool = Field(False, description="Whether to also call TTS.")


class MessageOut(BaseModel):
    reply: str
    mood: float
    mood_label: str
    audio_url: Optional[str] = None
    memories_used: int = 0
    recent_memories_used: int = 0
    drift_detected: bool = False
    drift_script: str = ""
    attempts: int = 1


class MoodOut(BaseModel):
    value: float
    label: str
    hours_since_interaction: float
    history_size: int


class HealthOut(BaseModel):
    status: str
    brain_version: str
    memory: dict
    mood: MoodOut
    llm_url: str
    chromadb_url: str


class ReflectionOut(BaseModel):
    thought: str
    mood: float
    hours_since_interaction: float


# --- App lifecycle ---------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(f"aria_brain starting on {ARIA_BRAIN_HOST}:{ARIA_BRAIN_PORT}")
    # Pre-warm ChromaDB so the first /message doesn't pay the embedding-model load cost.
    import asyncio
    await asyncio.to_thread(memory.warmup)
    reflection.start()
    log.info("aria_brain online")
    yield
    reflection.stop()
    log.info("aria_brain stopped")


app = FastAPI(
    title="Aria Brain",
    version="0.1.0",
    description="Personality, memory, mood, and reflection engine for AriaAssistant.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routes ----------------------------------------------------------------

@app.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    import asyncio
    mood_value, state = mood.get_current()
    try:
        mem_stats = await memory.astats()
    except Exception as exc:
        log.warning(f"memory.stats failed: {exc}")
        mem_stats = {"backend": "unavailable", "episodic_count": 0, "facts_count": 0, "thoughts_count": 0}
    return HealthOut(
        status="ok",
        brain_version="0.1.0",
        memory=mem_stats,
        mood=MoodOut(
            value=mood_value,
            label=personality.mood_to_label(mood_value),
            hours_since_interaction=mood.hours_since_last_interaction(),
            history_size=len(state.history),
        ),
        llm_url=f"{__import__('aria_brain.config', fromlist=['LM_STUDIO_BASE_URL']).LM_STUDIO_BASE_URL}",
        chromadb_url=f"{__import__('aria_brain.config', fromlist=['CHROMADB_URL']).CHROMADB_URL}",
    )


@app.get("/mood", response_model=MoodOut)
async def get_mood() -> MoodOut:
    mood_value, state = mood.get_current()
    return MoodOut(
        value=mood_value,
        label=personality.mood_to_label(mood_value),
        hours_since_interaction=mood.hours_since_last_interaction(),
        history_size=len(state.history),
    )


@app.post("/message", response_model=MessageOut)
async def post_message(msg: MessageIn) -> MessageOut:
    result = await brain.handle_message(msg.text, source=msg.source, speak=msg.speak)
    return MessageOut(**result)


@app.post("/reflect", response_model=ReflectionOut)
async def post_reflect() -> ReflectionOut:
    result = await brain.handle_reflection()
    return ReflectionOut(**result)


@app.post("/transcribe")
async def post_transcribe(audio_file: bytes = None) -> dict:
    """Accept audio bytes (WAV), return {text: str}.

    Uses faster-whisper locally. Lazy-loads the model on first call.
    """
    from fastapi import Request
    # FastAPI doesn't natively bind raw body without a Pydantic model; use Request instead.
    raise NotImplementedError("use POST /transcribe-bytes instead")


@app.post("/transcribe-bytes")
async def post_transcribe_bytes(request: Request) -> dict:
    """Accept raw audio bytes (WAV) in the body, return {text: str}."""
    from aria_brain import voice as voice_mod
    audio_bytes = await request.body()
    if not audio_bytes:
        return {"text": "", "error": "empty body"}
    try:
        text = await asyncio.to_thread(voice_mod.transcribe_wav_bytes, audio_bytes)
    except Exception as exc:
        log.warning(f"transcribe failed: {exc}")
        return {"text": "", "error": str(exc)}
    return {"text": text}


@app.post("/shutdown")
async def post_shutdown():
    """Graceful shutdown — sets uvicorn's should_exit flag so the server
    finishes in-flight requests, then exits. Works the same on Windows
    where os.kill(SIGTERM) is unreliable.
    """
    import aria_brain.server as _self
    server = getattr(_self, "_uvicorn_server", None)
    if server is not None:
        server.should_exit = True
        return {"status": "shutting_down", "via": "uvicorn"}
    # Fallback — no programmatic handle. Best-effort SIGTERM.
    import os, signal
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except OSError as exc:
        return {"status": "shutdown_failed", "error": str(exc)}
    return {"status": "shutting_down", "via": "signal"}


@app.websocket("/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            text = (data.get("text") or "").strip()
            if not text:
                await ws.send_json({"error": "empty text"})
                continue
            source = data.get("source", "ws")
            speak = bool(data.get("speak", False))
            result = await brain.handle_message(text, source=source, speak=speak)
            await ws.send_json(result)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning(f"ws_chat error: {exc}")
        try:
            await ws.send_json({"error": str(exc)})
        except Exception:
            pass


# --- Streaming voice -------------------------------------------------------
#
# One push-to-talk turn over a single WebSocket:
#   client → brain:  {"type":"ptt_down"}            barge-in: cancel current turn
#                    <binary frames>                raw PCM16 mono @ 16 kHz (mic)
#                    {"type":"ptt_up"}              end of turn → transcribe + reply
#   brain  → client: {"type":"cancel"}             stop playback NOW (barge-in)
#                    {"type":"transcript","text":..}
#                    {"type":"sentence","text":..}  display text for the next audio
#                    <binary frames>                Aria's voice: raw PCM16 mono @ 24 kHz
#                    {"type":"done", ...}           turn finished (reply, mood, etc.)
#
# Pressing PTT again at any time cancels the in-flight turn (stops the LLM stream
# and drops the TTS connection, which makes the TTS server stop generating).

def _pcm_to_wav(pcm: bytes, rate: int = VOICE_IN_RATE) -> bytes:
    """Wrap raw mono PCM16 in a WAV container so faster-whisper can decode it."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def _stream_tts_to_ws(ws: WebSocket, text: str) -> None:
    """Synthesize one sentence on the streaming TTS server and forward its PCM
    chunks to the client as binary frames. Cancellation (barge-in) propagates as
    CancelledError, which closes the httpx stream → the TTS server sees the drop
    and stops generating."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", TTS_STREAM_URL, json={"text": text}) as r:
                if r.status_code != 200:
                    log.warning(f"voice tts_stream: status {r.status_code}")
                    return
                async for chunk in r.aiter_bytes():
                    if chunk:
                        await ws.send_bytes(chunk)
    except (httpx.HTTPError, OSError) as exc:
        log.warning(f"voice tts_stream: {type(exc).__name__}: {exc}")


async def _run_voice_turn(ws: WebSocket, pcm: bytes) -> None:
    """Transcribe the captured audio, stream the reply through TTS to the client."""
    if not pcm:
        await ws.send_json({"type": "done", "reply": "", "transcript": ""})
        return
    # 1. STT (faster-whisper is sync → run in a thread).
    try:
        wav = _pcm_to_wav(pcm)
        text = await asyncio.to_thread(voice_mod.transcribe_wav_bytes, wav)
    except Exception as exc:
        log.warning(f"voice STT failed: {exc}")
        await ws.send_json({"type": "done", "reply": "", "transcript": "", "error": "stt_failed"})
        return
    text = (text or "").strip()
    await ws.send_json({"type": "transcript", "text": text})
    if not text:
        await ws.send_json({"type": "done", "reply": "", "transcript": ""})
        return
    # 2. Stream the reply sentence-by-sentence; speak each as it forms.
    async for ev in brain.handle_message_stream(text, source="voice"):
        if ev["type"] == "sentence":
            await ws.send_json({"type": "sentence", "text": ev["text"]})
            await _stream_tts_to_ws(ws, ev["text"])
        elif ev["type"] == "done":
            await ws.send_json({
                "type": "done",
                "reply": ev.get("reply", ""),
                "mood": ev.get("mood"),
                "mood_label": ev.get("mood_label"),
                "task_mode": ev.get("task_mode", False),
                "model": ev.get("model", "chat"),
            })


async def _cancel_voice_turn(state: dict) -> None:
    task = state.get("task")
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    state["task"] = None


@app.websocket("/voice-stream")
async def voice_stream(ws: WebSocket):
    await ws.accept()
    state: dict = {"buf": bytearray(), "capturing": False, "task": None}
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            text = msg.get("text")
            data_bytes = msg.get("bytes")
            if text is not None:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    continue
                kind = data.get("type")
                if kind == "ptt_down":
                    # Barge-in: cancel any in-flight turn, tell client to stop playback,
                    # and start a fresh capture buffer.
                    await _cancel_voice_turn(state)
                    try:
                        await ws.send_json({"type": "cancel"})
                    except Exception:
                        pass
                    state["buf"] = bytearray()
                    state["capturing"] = True
                elif kind == "ptt_up":
                    state["capturing"] = False
                    pcm = bytes(state["buf"])
                    state["buf"] = bytearray()
                    await _cancel_voice_turn(state)  # safety: never overlap turns
                    state["task"] = asyncio.create_task(_run_voice_turn(ws, pcm))
            elif data_bytes is not None:
                if state["capturing"]:
                    state["buf"].extend(data_bytes)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning(f"voice_stream error: {exc}")
    finally:
        await _cancel_voice_turn(state)