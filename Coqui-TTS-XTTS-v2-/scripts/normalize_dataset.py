"""Audit + loudness-normalize a wav dataset in place (22050/mono/16-bit).

Scales each clip to a target RMS with a peak ceiling (no clipping), and flags
clips that are too short, too long, silent, or the wrong format.

    python scripts/normalize_dataset.py data/jessica_voice/wavs
"""
import sys
import wave
from pathlib import Path

import numpy as np

TARGET_RMS = 0.12     # matches the level that trained well before
PEAK_CEIL = 0.97      # never let a normalized peak exceed this
MIN_S, MAX_S = 1.0, 13.0


def main():
    wav_dir = Path(sys.argv[1])
    files = sorted(wav_dir.glob("*.wav"))
    durs, flags, changed = [], [], 0
    for f in files:
        with wave.open(str(f), "rb") as w:
            n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(n)
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        dur = n / sr
        durs.append(dur)
        rms = float(np.sqrt(np.mean(a ** 2))) if a.size else 0.0
        peak = float(np.max(np.abs(a))) if a.size else 0.0
        if sr != 22050 or ch != 1 or sw != 2:
            flags.append((f.name, f"format sr={sr} ch={ch} {sw*8}bit"))
        if dur < MIN_S or dur > MAX_S:
            flags.append((f.name, f"duration {dur:.2f}s"))
        if rms < 0.02:
            flags.append((f.name, f"near-silent RMS={rms:.3f}"))
            continue
        # normalize: hit target RMS unless it would clip, then back off to the peak ceiling
        scale = TARGET_RMS / rms
        if peak * scale > PEAK_CEIL:
            scale = PEAK_CEIL / peak
        if abs(scale - 1.0) > 0.01:
            out = np.clip(a * scale, -1.0, 1.0)
            pcm = (out * 32767).astype("<i2")
            with wave.open(str(f), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(pcm.tobytes())
            changed += 1

    durs.sort()
    tot = sum(durs)
    print(f"clips: {len(files)} | total {tot/60:.1f} min | normalized {changed}")
    print(f"duration min/median/max: {durs[0]:.2f} / {durs[len(durs)//2]:.2f} / {durs[-1]:.2f} s")
    print(f"flags: {len(flags)}")
    for name, why in flags[:40]:
        print("   ", name, "->", why)


if __name__ == "__main__":
    main()
