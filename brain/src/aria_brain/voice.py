"""Voice / Whisper STT — push-to-talk transcription.

Defaults: faster-whisper with the 'base' model (74MB, English, runs on CPU OK).
Override via env WHISPER_MODEL=tiny|base|small|medium|large-v3 and WHISPER_DEVICE=cuda|cpu.

The mic is captured locally on PC 1 (sounddevice) and transcribed here. For
low-latency recognition on PC 2's GPU, set WHISPER_DEVICE=cuda on a process
running on PC 2 (out of scope for this file).
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
import wave
from pathlib import Path

log = logging.getLogger("aria_brain.voice")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")  # int8 for CPU speed
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "en")

_model = None  # lazy


def _get_model():
    """Lazy-load the Whisper model."""
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel
            log.info(f"loading whisper model={WHISPER_MODEL} device={WHISPER_DEVICE} compute={WHISPER_COMPUTE}")
            _model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE)
            log.info("whisper loaded")
        except Exception as exc:
            log.warning(f"whisper load failed: {type(exc).__name__}: {exc}")
            raise
    return _model


def transcribe_file(path: str | Path) -> str:
    """Transcribe a WAV/PCM file. Returns the recognized text."""
    model = _get_model()
    segments, info = model.transcribe(
        str(path),
        language=WHISPER_LANGUAGE,
        vad_filter=True,
    )
    text = " ".join(seg.text.strip() for seg in segments).strip()
    log.info(f"transcribed {info.duration:.1f}s audio -> {len(text)} chars")
    return text


def transcribe_wav_bytes(audio_bytes: bytes, sample_rate: int = 16000) -> str:
    """Transcribe raw PCM/WAV bytes (16kHz mono PCM16 or WAV)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        return transcribe_file(tmp_path)
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass


def record_mic(seconds: float = 5.0, sample_rate: int = 16000) -> bytes:
    """Record N seconds from the default mic. Returns WAV bytes."""
    try:
        import sounddevice as sd
    except OSError as exc:
        raise RuntimeError(f"sounddevice not available: {exc}") from exc
    log.info(f"recording {seconds}s @ {sample_rate}Hz")
    audio = sd.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    # Convert to WAV bytes
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


# Push-to-talk loop — used by the tray menu's Voice toggle.

import threading

_recording_thread: threading.Thread | None = None
_ptt_active = threading.Event()


def start_push_to_talk(hotkey: str = "ctrl+shift+space", max_seconds: float = 10.0,
                       on_text=None, on_error=None) -> None:
    """Start a background thread that listens for a global hotkey. Press to record
    and transcribe; the recognized text is delivered via on_text(text) callback.

    Press Esc to stop. Best-effort — global hotkeys may need admin on Windows.
    """
    def _loop():
        try:
            import keyboard  # type: ignore
        except ImportError as exc:
            if on_error:
                on_error(f"keyboard library not available: {exc}")
            return
        log.info(f"push-to-talk armed: press {hotkey} to record, esc to quit")
        while _ptt_active.is_set():
            try:
                keyboard.wait(hotkey)
                if not _ptt_active.is_set():
                    break
                wav = record_mic(max_seconds)
                text = transcribe_wav_bytes(wav)
                if on_text:
                    on_text(text)
            except Exception as exc:
                if on_error:
                    on_error(str(exc))
                break

    global _recording_thread
    if _recording_thread is not None and _recording_thread.is_alive():
        return
    _ptt_active.set()
    _recording_thread = threading.Thread(target=_loop, daemon=True)
    _recording_thread.start()


def stop_push_to_talk() -> None:  # noqa: F811
    _ptt_active.clear()