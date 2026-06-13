# Inference-parameter sweep for the ana voice — focused on fixing robotic *timing*.
# Generates the same sentence under several settings so we can A/B and lock in the best.
#   & "C:\Program Files\Python312\python.exe" scripts/tts_sweep.py
import sys
import wave
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

RUN = ROOT / "run" / "training" / "XTTS_v2_Ana_Voice-June-08-2026_04+18PM-dbf1a08a"
BASE = ROOT / "run" / "training" / "XTTS_v2_original_model_files"
WAVS = ROOT / "data" / "ana_voice" / "wavs"
OUT = ROOT / "run" / "samples"

# Target = sentence #3 (the one that sounded most natural), so the A/B is apples-to-apples.
TEXT = ("Let me think about that for a second. Based on what I'm seeing, the simplest "
        "fix is to restart the service and then clear the cache.")

# "rich" conditioning = several varied clips -> more prosodic context, steadier timing
RICH_REFS = [str(WAVS / f"ana_{i:04d}.wav") for i in (1, 11, 21, 31, 41, 51)]
ORIG_REFS = [str(WAVS / "ana_0001.wav"), str(WAVS / "ana_0002.wav")]

# (label, refs, cond_len, params) — change one or two knobs at a time
CONFIGS = [
    ("A_original",  ORIG_REFS, 12, dict(temperature=0.70, repetition_penalty=5.0, top_k=50, top_p=0.85,
                                        length_penalty=1.0, speed=1.00, enable_text_splitting=True)),
    ("B_singlepass", RICH_REFS, 30, dict(temperature=0.75, repetition_penalty=2.0, top_k=50, top_p=0.85,
                                        length_penalty=1.0, speed=1.00, enable_text_splitting=False)),
    ("C_slower",    RICH_REFS, 30, dict(temperature=0.75, repetition_penalty=2.0, top_k=50, top_p=0.85,
                                        length_penalty=1.0, speed=0.90, enable_text_splitting=False)),
    ("D_warmer",    RICH_REFS, 30, dict(temperature=0.85, repetition_penalty=2.0, top_k=60, top_p=0.90,
                                        length_penalty=1.0, speed=0.95, enable_text_splitting=False)),
    ("E_relaxed",   RICH_REFS, 30, dict(temperature=0.80, repetition_penalty=2.0, top_k=50, top_p=0.90,
                                        length_penalty=1.0, speed=0.88, enable_text_splitting=False)),
]


def save_wav(wav, path, sr=24000):
    wav = np.clip(np.asarray(wav, dtype=np.float32), -1.0, 1.0)
    pcm = (wav * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("[+] Loading model...")
    config = XttsConfig(); config.load_json(str(RUN / "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_path=str(RUN / "best_model.pth"),
                          vocab_path=str(BASE / "vocab.json"), use_deepspeed=False)
    model.cuda()

    latent_cache = {}
    for label, refs, cond_len, params in CONFIGS:
        key = (tuple(refs), cond_len)
        if key not in latent_cache:
            latent_cache[key] = model.get_conditioning_latents(
                audio_path=list(refs), gpt_cond_len=cond_len, gpt_cond_chunk_len=6,
                max_ref_length=cond_len)
        gpt_cond_latent, speaker_embedding = latent_cache[key]
        print(f"[+] {label}: {params}")
        out = model.inference(TEXT, "en", gpt_cond_latent, speaker_embedding, **params)
        save_wav(out["wav"], OUT / f"sweep_{label}.wav")
        print(f"    -> sweep_{label}.wav")
    print("[+] Done.")


if __name__ == "__main__":
    main()
