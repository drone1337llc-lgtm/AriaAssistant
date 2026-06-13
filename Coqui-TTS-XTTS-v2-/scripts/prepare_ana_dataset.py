"""
Prepare a clean, single-voice (ana) XTTS training dataset.

Reconstructs exact transcripts from the original ElevenLabs generation script
(generate_training_samples.py), validates the clip->text alignment WITHOUT ASR
by correlating clip duration against sentence length, and (with --write) builds
a clean dataset dir with a correct LJSpeech-format metadata.csv.

Usage:
    python scripts/prepare_ana_dataset.py            # validate only
    python scripts/prepare_ana_dataset.py --write    # validate + build dataset
"""
import argparse
import ast
import glob
import os
import re
import shutil
import statistics
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEN_SCRIPT = ROOT / "scripts" / "generate_training_samples.py"
SRC_WAVS = ROOT / "data" / "astrobud_voice" / "wavs"
OUT_DIR = ROOT / "data" / "ana_voice"
OUT_WAVS = OUT_DIR / "wavs"
OUT_META = OUT_DIR / "metadata.csv"


def load_samples():
    """Extract the SAMPLES literal list from the generation script (no import / no API calls)."""
    tree = ast.parse(GEN_SCRIPT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "SAMPLES":
                    return [tup[0] for tup in ast.literal_eval(node.value)]
    raise RuntimeError("SAMPLES list not found in generation script")


def wav_duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="build the clean dataset")
    args = ap.parse_args()

    samples = load_samples()
    n = len(samples)
    clips = sorted(glob.glob(str(SRC_WAVS / "ana_*.wav")))
    print(f"SAMPLES sentences: {n}")
    print(f"ana clips found  : {len(clips)}\n")

    rows = []          # (clip_id, text, dur, n_chars)
    for path in clips:
        cid = Path(path).stem
        idx = int(cid.split("_")[1])          # ana_0001 -> 1
        text = samples[(idx - 1) % n]
        dur = wav_duration(path)
        rows.append((cid, text, dur, len(text)))

    # --- ASR-free alignment check: duration should track sentence length ---
    durs = [r[2] for r in rows]
    chars = [float(r[3]) for r in rows]
    mean_d, mean_c = statistics.mean(durs), statistics.mean(chars)
    cov_dc = sum((d - mean_d) * (c - mean_c) for d, c in zip(durs, chars))
    std_d = sum((d - mean_d) ** 2 for d in durs) ** 0.5
    std_c = sum((c - mean_c) ** 2 for c in chars) ** 0.5
    r = cov_dc / (std_d * std_c) if std_d and std_c else 0.0

    ratios = [d / c for d, c in zip(durs, chars)]      # seconds per char
    med_ratio = statistics.median(ratios)
    print(f"Duration vs sentence-length correlation r = {r:.3f}")
    print(f"  (>0.9 = alignment almost certainly correct)")
    print(f"Median speaking rate: {1/med_ratio:.1f} chars/sec\n")

    # Flag clips whose seconds-per-char deviates a lot from the median
    # (either a mapping error or a genuinely odd clip worth a listen)
    flagged = []
    for (cid, text, dur, nc), ratio in zip(rows, ratios):
        if not (0.45 * med_ratio < ratio < 2.0 * med_ratio):
            flagged.append((cid, round(dur, 2), nc, round(ratio / med_ratio, 2), text[:45]))
    print(f"Outlier clips (rate far from median): {len(flagged)}")
    for f in flagged[:25]:
        print("   ", f)
    print()
    print("Sample reconstructed transcripts:")
    for cid, text, dur, nc in rows[:3] + rows[97:100]:
        print(f"   {cid} ({dur:.1f}s): {text}")

    if not args.write:
        print("\n[validate-only] re-run with --write to build the dataset.")
        return

    OUT_WAVS.mkdir(parents=True, exist_ok=True)
    with open(OUT_META, "w", encoding="utf-8") as f:
        for cid, text, dur, nc in rows:
            shutil.copy2(SRC_WAVS / f"{cid}.wav", OUT_WAVS / f"{cid}.wav")
            f.write(f"{cid}|{text}|{text}\n")
    print(f"\n[+] Wrote {len(rows)} clips -> {OUT_WAVS}")
    print(f"[+] Wrote metadata       -> {OUT_META}")


if __name__ == "__main__":
    main()
