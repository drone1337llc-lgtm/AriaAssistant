"""
Persistent XTTS server for Aria's Jessica voice.
Loads the model ONCE at startup (~10-15s), then handles requests in <2s.

Start:
    & "C:\Program Files\Python312\python.exe" scripts/tts_server_jessica.py

Aria's TTSBridge POSTs to http://127.0.0.1:5003/tts:
    {"text": "Hello!", "speaker": "", "language": "en"}
Returns: audio/wav bytes (24 kHz mono PCM)
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

HOST, PORT = "127.0.0.1", 5003

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
    print(f"[TTS] Jessica voice ready. Listening on http://{HOST}:{PORT}/tts")


def synthesize(text: str) -> bytes:
    with _lock:
        out = _model.inference(
            text, "en",
            _gpt_cond_latent, _speaker_embedding,
            **PARAMS,
        )
    wav = np.clip(np.asarray(out["wav"], dtype=np.float32), -1.0, 1.0)
    pcm = (wav * 32767).astype("<i2").tobytes()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/tts":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            text = data.get("text", "").strip()
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

    def log_message(self, fmt, *args):
        pass  # suppress default access log; we print our own


if __name__ == "__main__":
    load_model()
    server = HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[TTS] Server stopped.")
