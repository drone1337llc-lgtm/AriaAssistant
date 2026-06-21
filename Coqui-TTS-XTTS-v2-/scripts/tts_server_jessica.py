"""
Persistent XTTS server for Aria's Jessica voice — NOW WITH STREAMING.

Loads the model ONCE at startup (~10-15s). Two endpoints:
  POST /tts          → whole WAV bytes (24 kHz mono PCM16).  [unchanged; text-chat path]
  POST /tts_stream   → raw PCM16 (24 kHz mono LE) streamed as it's generated, so Aria
                       starts speaking ~immediately instead of after the whole line.
                       Body: {"text": "..."}. Response: audio/L16; rate=24000; channels=1,
                       Connection: close (read until EOF). If the client disconnects
                       mid-stream (barge-in), generation stops on the next write.

Start (on PC2, from the Coqui-TTS-XTTS-v2- folder — this file lives in its scripts/):
    & "C:\\Program Files\\Python312\\python.exe" scripts/tts_server_jessica.py
"""
import io
import json
import sys
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Lock

import numpy as np
import torch

# ── Path setup ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

# ── Model paths ─────────────────────────────────────────────────────────────
RUN  = ROOT / "run" / "training" / "XTTS_v2_Jessica_Voice-June-08-2026_05+55PM-dbf1a08a"
BASE = ROOT / "run" / "training" / "XTTS_v2_original_model_files"
WAVS = ROOT / "data" / "jessica_voice" / "wavs"

# Multiple clips → robust prosodic conditioning
REFS = [str(WAVS / f"jessica_{i:04d}.wav") for i in (123, 187, 83, 216, 149, 70)]

PARAMS = dict(
    temperature=0.80,
    repetition_penalty=2.0,
    top_k=55,
    top_p=0.90,
    length_penalty=1.0,
    speed=0.95,
    enable_text_splitting=False,
)

# Streaming-only knobs. stream_chunk_size = GPT tokens per emitted audio chunk;
# smaller = lower latency to first audio, but more overhead. 20 is a good start;
# try 10-15 if first-audio still feels slow, higher if you hear chunk seams.
STREAM_PARAMS = dict(
    stream_chunk_size=20,
    overlap_wav_len=1024,
)

HOST, PORT = "127.0.0.1", 5003
SAMPLE_RATE = 24000

# ── Global model (loaded once) ───────────────────────────────────────────────
_model = None
_gpt_cond_latent = None
_speaker_embedding = None
_lock = Lock()  # inference is not thread-safe; serialize requests


def load_model():
    global _model, _gpt_cond_latent, _speaker_embedding
    print("[TTS] Loading Jessica XTTS model (this takes ~15s)...")
    config = XttsConfig()
    config.load_json(str(RUN / "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(
        config,
        checkpoint_path=str(RUN / "best_model.pth"),
        vocab_path=str(BASE / "vocab.json"),
        use_deepspeed=False,
    )
    model.cuda()
    model.eval()

    print("[TTS] Computing speaker conditioning from reference clips...")
    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=REFS,
        gpt_cond_len=30,
        gpt_cond_chunk_len=6,
        max_ref_length=30,
    )
    _model, _gpt_cond_latent, _speaker_embedding = model, gpt_cond_latent, speaker_embedding
    print(f"[TTS] Jessica voice ready. Listening on http://{HOST}:{PORT}/tts (+ /tts_stream)")


def _pcm16_bytes(wav_array) -> bytes:
    """float waveform in [-1,1] → little-endian 16-bit PCM bytes."""
    wav = np.clip(np.asarray(wav_array, dtype=np.float32), -1.0, 1.0)
    return (wav * 32767).astype("<i2").tobytes()


def synthesize(text: str) -> bytes:
    """Whole-line synthesis → complete WAV bytes (unchanged behavior)."""
    with _lock:
        out = _model.inference(
            text, "en",
            _gpt_cond_latent, _speaker_embedding,
            **PARAMS,
        )
    pcm = _pcm16_bytes(out["wav"])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def synthesize_stream(text: str):
    """Generator: yields PCM16 byte chunks as XTTS produces them.

    Holds the inference lock for the whole utterance (XTTS isn't thread-safe and
    serializing is correct for a single user). Chunks are raw PCM16 LE @ 24 kHz —
    NO WAV header (the client knows the fixed format and plays a raw stream).
    """
    with _lock:
        stream = _model.inference_stream(
            text, "en",
            _gpt_cond_latent, _speaker_embedding,
            **STREAM_PARAMS,
            **PARAMS,
        )
        for chunk in stream:
            # chunk is a 1-D float tensor (often on GPU)
            wav = chunk.squeeze().detach().cpu().numpy()
            if wav.size == 0:
                continue
            yield _pcm16_bytes(wav)


class Handler(BaseHTTPRequestHandler):
    def _read_text(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        data = json.loads(body)
        return (data.get("text", "") or "").strip()

    def do_POST(self):
        if self.path == "/tts":
            self._handle_whole()
        elif self.path == "/tts_stream":
            self._handle_stream()
        else:
            self.send_error(404)

    def _handle_whole(self):
        try:
            text = self._read_text()
        except Exception:
            self.send_error(400, "Bad JSON")
            return
        if not text:
            self.send_error(400, "Empty text")
            return
        print(f"[TTS] Synthesizing: {text[:80]}{'...' if len(text) > 80 else ''}")
        try:
            wav_bytes = synthesize(text)
        except Exception as e:
            print(f"[TTS] Error: {e}")
            self.send_error(500, str(e))
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav_bytes)))
        self.end_headers()
        self.wfile.write(wav_bytes)

    def _handle_stream(self):
        try:
            text = self._read_text()
        except Exception:
            self.send_error(400, "Bad JSON")
            return
        if not text:
            self.send_error(400, "Empty text")
            return
        print(f"[TTS] Streaming: {text[:80]}{'...' if len(text) > 80 else ''}")
        self.send_response(200)
        self.send_header("Content-Type", f"audio/L16; rate={SAMPLE_RATE}; channels=1")
        self.send_header("Connection", "close")  # HTTP/1.0: read body until EOF
        self.end_headers()
        try:
            for pcm in synthesize_stream(text):
                self.wfile.write(pcm)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # Client hung up mid-utterance (barge-in). Stop generating quietly.
            print("[TTS] stream client disconnected (barge-in) — stopping")
        except Exception as e:
            print(f"[TTS] Stream error: {e}")

    def log_message(self, fmt, *args):
        pass  # suppress default access log; we print our own


if __name__ == "__main__":
    load_model()
    server = HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[TTS] Server stopped.")
