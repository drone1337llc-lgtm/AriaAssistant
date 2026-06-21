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
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aria_brain import brain, memory, mood, personality, reflection
from aria_brain.config import ARIA_BRAIN_HOST, ARIA_BRAIN_PORT

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