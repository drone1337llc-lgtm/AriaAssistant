# Inference with the fine-tuned "ana" XTTS voice.
#   & "C:\Program Files\Python312\python.exe" scripts/tts_ana.py
#   & "C:\Program Files\Python312\python.exe" scripts/tts_ana.py --text "Say something custom."
#
# Output: 24 kHz WAV files in run/samples/
import argparse
import sys
import wave
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))   # use the local repo TTS (dev), same as training

from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

RUN = ROOT / "run" / "training" / "XTTS_v2_Ana_Voice-June-08-2026_04+18PM-dbf1a08a"
BASE = ROOT / "run" / "training" / "XTTS_v2_original_model_files"
CHECKPOINT = RUN / "best_model.pth"               # epoch-11 sweet spot
VOCAB = BASE / "vocab.json"
SPEAKER_REFS = [str(ROOT / "data" / "ana_voice" / "wavs" / "ana_0001.wav"),
                str(ROOT / "data" / "ana_voice" / "wavs" / "ana_0002.wav")]
OUT_DIR = ROOT / "run" / "samples"

# A few sentences NOT spoken verbatim in training -> tests natural generalization
DEMO = [
    ("01_greeting",  "Hello, I am AstroBud, your desktop AI assistant. How can I help you today?"),
    ("02_unseen",    "Of course. I've gone ahead and scheduled that for tomorrow at nine. "
                     "Is there anything else you'd like me to take care of?"),
    ("03_stability", "Let me think about that for a second. Based on what I'm seeing, the simplest "
                     "fix is to restart the service and then clear the cache."),
]


def save_wav(wav, path, sr=24000):
    wav = np.asarray(wav, dtype=np.float32)
    wav = np.clip(wav, -1.0, 1.0)
    pcm = (wav * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default=None, help="custom sentence (overrides the demo set)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[+] Loading fine-tuned ana model...")
    config = XttsConfig()
    config.load_json(str(RUN / "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_path=str(CHECKPOINT), vocab_path=str(VOCAB),
                          use_deepspeed=False)
    model.cuda()

    items = [("custom", args.text)] if args.text else DEMO
    for name, text in items:
        print(f"[+] Synthesizing {name}: {text[:50]}...")
        out = model.synthesize(
            text, config, speaker_wav=SPEAKER_REFS, language="en",
            temperature=0.7, length_penalty=1.0, repetition_penalty=5.0,
            top_k=50, top_p=0.85, enable_text_splitting=True,
        )
        path = OUT_DIR / f"ana_{name}.wav"
        save_wav(out["wav"], path)
        print(f"    -> {path}")

    print("[+] Done. Samples in", OUT_DIR)


if __name__ == "__main__":
    main()
