#!/usr/bin/env python3
"""
voice_speak.py — XTTS v2 inference for AstroBud
==============================================
Run on PC 1 (gaming/main PC, RTX 4080 Super).

Loads the fine-tuned XTTS v2 model from models/xtts_astrobud/
and generates speech from text. Called by main_astro.py when
AstroBud needs to speak.

Usage:
    python voice_speak.py "Hey, I'm AstroBud. Bitcoin mining at maximum efficiency."

    # Or import as a module from main_astro.py:
    from voice_speak import AstroVoice
    voice = AstroVoice()
    audio = voice.speak("Nice! We found a share.")
    voice.play(audio)

Dependencies (install on PC 1):
    pip install torch torchaudio TTS soundfile librosa numpy scipy
    # or from requirements: pip install -r requirements.txt

For the RTX 4080 Super, VRAM usage is ~3-4 GB for XTTS inference.
Compatible with gaming/compiling running simultaneously.
"""

import os, sys, time, threading, logging
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────────────
# Training scripts + model live in the Coqui project at C:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\
# To retrain: run scripts/train_jessica_voice.py there, then update MODEL_DIR to the new checkpoint.
MODEL_DIR   = Path("C:/Users/Tench/Documents/Coqui-TTS-XTTS-v2-/run/training/XTTS_v2_Jessica_Voice-June-08-2026_05+55PM-dbf1a08a")
SAMPLES_DIR = Path("C:/Users/Tench/Documents/Coqui-TTS-XTTS-v2-/data/jessica_voice/wavs")
LOG_FILE    = Path("C:/Users/Tench/Documents/AI Learning/astro_assistant/logs/voice_speak.log")

# Primary speaker reference — one of Jessica's training clips used for voice conditioning.
DEFAULT_SPEAKER = "jessica_0123.wav"

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("voice_speak")


# ── TTS Engine ────────────────────────────────────────────────────────────────
class AstroVoice:
    """
    XTTS v2 voice engine for AstroBud.

    Usage:
        voice = AstroVoice()
        voice.speak("Nice! We found a share.")
    """

    def __init__(self, speaker_wav=None, model_dir=None, use_gpu=True):
        self.speaker_wav = str(SAMPLES_DIR / (speaker_wav or DEFAULT_SPEAKER))
        self.model_dir   = str(model_dir or MODEL_DIR)
        self.use_gpu     = use_gpu
        self._tts        = None
        self._ready     = False

        # Cache last generated audio for repeat playback
        self._last_audio = None
        self._last_text  = ""

        log.info(f"AstroVoice init: speaker={speaker_wav or DEFAULT_SPEAKER}  "
                 f"gpu={use_gpu}  model={self.model_dir}")

    def _load(self):
        """Lazy-load the model on first use (not at import time)."""
        if self._ready:
            return

        import torch
        from TTS.api import TTS

        log.info("Loading XTTS v2 model (first use, ~5-15 seconds) ...")
        t0 = time.time()

        try:
            # Try fine-tuned model first
            self._tts = TTS(
                model_path=str(Path(self.model_dir) / "best_model.pth"),
                config_path=str(Path(self.model_dir) / "config.json"),
                gpu=self.use_gpu,
            )
        except Exception:
            # Fall back to base XTTS v2 with speaker reference
            log.info("Fine-tuned model not found — using base XTTS v2 with speaker reference")
            self._tts = TTS(
                "tts_models/multilingual/multi-dataset/xtts_v2",
                gpu=self.use_gpu,
            )

        if torch.cuda.is_available() and self.use_gpu:
            log.info(f"  GPU: {torch.cuda.get_device_name(0)}  "
                     f"VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB")
        else:
            log.info("  Running on CPU (slower but works)")

        log.info(f"  Model loaded in {time.time()-t0:.1f}s")
        self._ready = True

    # ── Generate speech ──────────────────────────────────────────────────────
    def speak(self, text, output_path=None, speaker_wav=None, language="en"):
        """
        Generate audio for `text` and return the WAV data as a numpy array.

        Args:
            text:        The text to synthesize
            output_path: Optional path to save a WAV file
            speaker_wav: Override the default speaker reference audio
            language:   Language code ("en" for English)

        Returns:
            numpy array of audio samples (float32, 24 kHz mono)
        """
        self._load()

        ref_wav = str(SAMPLES_DIR / speaker_wav) if speaker_wav else self.speaker_wav
        if not Path(ref_wav).exists():
            log.error(f"Speaker reference not found: {ref_wav}")
            return None

        if not text or not text.strip():
            log.debug("Empty text, skipping synthesis")
            return None

        # Strip asterisk sound effects before speaking
        clean_text = text.replace("*", " ").strip()

        t0 = time.time()
        try:
            if output_path:
                self._tts.tts_to_file(
                    text=clean_text,
                    speaker_wav=ref_wav,
                    file_path=output_path,
                    language=language,
                )
                audio = None  # caller has the file
                log.info(f"  saved → {output_path}  ({time.time()-t0:.1f}s)")
            else:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    wav_path = Path(tmp.name)
                self._tts.tts_to_file(
                    text=clean_text,
                    speaker_wav=ref_wav,
                    file_path=str(wav_path),
                    language=language,
                )
                import soundfile as sf
                audio, sr = sf.read(str(wav_path), dtype="float32")
                wav_path.unlink(missing_ok=True)
                self._last_audio = audio
                self._last_text  = text
                log.info(f"  generated {len(audio)/sr:.1f}s in {time.time()-t0:.1f}s")

        except Exception as e:
            log.error(f"TTS failed: {e}")
            return None

        return audio

    # ── Play audio ────────────────────────────────────────────────────────────
    def play(self, audio=None, output_path=None):
        """
        Play audio through the default output device.
        Call speak() first, or pass an output_path from a previous speak() call.
        """
        import soundfile as sf
        import sounddevice as sd
        import numpy as np

        if output_path:
            data, sr = sf.read(output_path, dtype="float32")
        elif audio is not None:
            data = audio
            sr = 24000  # XTTS native sample rate
        elif self._last_audio is not None:
            data = self._last_audio
            sr = 24000
        else:
            log.warning("Nothing to play — call speak() first")
            return

        # Normalize to [-1, 1]
        data = np.clip(data, -1.0, 1.0)

        try:
            sd.play(data, sr, device=None)
            sd.wait()  # blocking
        except Exception as e:
            log.warning(f"Audio playback failed: {e}")

    # ── Quick speak + play combo ────────────────────────────────────────────────
    def say(self, text, speaker_wav=None):
        """Generate and play in one call. Blocks until audio finishes."""
        audio = self.speak(text, speaker_wav=speaker_wav)
        if audio is not None:
            self.play(audio)

    # ── Async speak (non-blocking) ──────────────────────────────────────────
    def say_async(self, text, speaker_wav=None):
        """Generate and play in a background thread. Returns immediately."""
        thread = threading.Thread(target=self.say, args=(text, speaker_wav), daemon=True)
        thread.start()
        return thread

    # ── Switch voice mode ──────────────────────────────────────────────────────
    def set_mode(self, mode):
        """
        Switch AstroBud's voice character.
        Modes: "neutral" | "flirty" | "intimate" | "enthusiastic" | "calm"
        """
        mode_map = {
            "neutral":      "jessica_0123.wav",
            "enthusiastic": "jessica_0187.wav",
            "flirty":       "jessica_0083.wav",
            "intimate":     "jessica_0216.wav",
            "calm":         "jessica_0149.wav",
            "british":      "jessica_0070.wav",
            "young":        "jessica_0070.wav",
        }
        wav = mode_map.get(mode.lower(), DEFAULT_SPEAKER)
        log.info(f"Voice mode → {mode}  (speaker={wav})")
        self.speaker_wav = str(SAMPLES_DIR / wav)

    # ── Warm-up (call at startup to preload model) ────────────────────────────
    def warmup(self):
        """Pre-load the model without generating audio. Call once at AstroBud start."""
        log.info("Warming up XTTS v2 model ...")
        self._load()
        # Quick silent generation to fully initialize GPU kernels
        try:
            self.speak(".", output_path="NUL")
        except Exception:
            pass
        log.info("  Ready.")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse, numpy as np, sounddevice as sd

    parser = argparse.ArgumentParser(description="AstroBud XTTS v2 voice synthesis")
    parser.add_argument("text", nargs="?", default="Hey, I'm AstroBud. Bitcoin mining at maximum efficiency.")
    parser.add_argument("--speaker", "-s", default=DEFAULT_SPEAKER,
                        help="Speaker reference MP3 (e.g. jflirty_A1.mp3)")
    parser.add_argument("--output", "-o", default=None,
                        help="Save WAV to this path")
    parser.add_argument("--no-play", action="store_true",
                        help="Generate only, don't play audio")
    parser.add_argument("--warmup", action="store_true",
                        help="Pre-load model without generating audio")
    args = parser.parse_args()

    voice = AstroVoice(speaker_wav=args.speaker)

    if args.warmup:
        voice.warmup()
    else:
        audio = voice.speak(args.text, output_path=args.output)
        if not args.no_play and audio is not None:
            print(f"Playing... ({len(audio)/24000:.1f}s)")
            sd.play(audio, 24000)
            sd.wait()
        elif args.output:
            print(f"Saved → {args.output}")