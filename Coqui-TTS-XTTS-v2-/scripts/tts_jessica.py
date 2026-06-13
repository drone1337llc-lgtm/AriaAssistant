# Inference with the fine-tuned "Jessica" XTTS voice.
# Locked-in natural settings (your B+D preference): single-pass, repetition_penalty 2.0,
# temperature 0.8, speed 0.95, rich multi-clip speaker conditioning.
#
#   & "C:\Program Files\Python312\python.exe" scripts/tts_jessica.py
#   & "C:\Program Files\Python312\python.exe" scripts/tts_jessica.py --text "Say something."
import argparse
import sys
import wave
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

RUN = ROOT / "run" / "training" / "XTTS_v2_Jessica_Voice-June-08-2026_05+55PM-dbf1a08a"
BASE = ROOT / "run" / "training" / "XTTS_v2_original_model_files"
WAVS = ROOT / "data" / "jessica_voice" / "wavs"
OUT = ROOT / "run" / "samples"

# varied clips -> robust prosodic conditioning (greeting + several longer lines)
REFS = [str(WAVS / f"jessica_{i:04d}.wav") for i in (123, 187, 83, 216, 149, 70)]

PARAMS = dict(temperature=0.80, repetition_penalty=2.0, top_k=55, top_p=0.90,
              length_penalty=1.0, speed=0.95, enable_text_splitting=False)

# Same 3 sentences used to judge the ana voice (direct A/B) + 1 novel unseen line
DEMO = [
    ("01_greeting", "Hello, I am AstroBud, your desktop AI assistant. How can I help you today?"),
    ("02_unseen",   "Of course. I've gone ahead and scheduled that for tomorrow at nine. "
                    "Is there anything else you'd like me to take care of?"),
    ("03_timing",   "Let me think about that for a second. Based on what I'm seeing, the simplest "
                    "fix is to restart the service and then clear the cache."),
    ("04_novel",    "I just finished going through everything, and honestly, it came together more "
                    "smoothly than I expected, so we're in great shape for tomorrow."),
]


def save_wav(wav, path, sr=24000):
    wav = np.clip(np.asarray(wav, dtype=np.float32), -1.0, 1.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((wav * 32767).astype("<i2").tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default=None)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    print("[+] Loading Jessica model...")
    config = XttsConfig(); config.load_json(str(RUN / "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_path=str(RUN / "best_model.pth"),
                          vocab_path=str(BASE / "vocab.json"), use_deepspeed=False)
    model.cuda()

    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=REFS, gpt_cond_len=30, gpt_cond_chunk_len=6, max_ref_length=30)

    items = [("custom", args.text)] if args.text else DEMO
    for name, text in items:
        print(f"[+] {name}: {text[:50]}...")
        out = model.inference(text, "en", gpt_cond_latent, speaker_embedding, **PARAMS)
        save_wav(out["wav"], OUT / f"jessica_{name}.wav")
    print("[+] Done ->", OUT)


if __name__ == "__main__":
    main()
