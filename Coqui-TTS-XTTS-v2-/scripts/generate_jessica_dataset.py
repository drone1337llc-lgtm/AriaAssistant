"""Generate a clean XTTS training dataset from ElevenLabs "Jessica".

Highest-quality model (eleven_multilingual_v2), consistent natural settings,
exact transcripts saved at generation time. Budget-safe on pay-as-you-go:
polls real usage and hard-stops before the quota. Resumable (skips existing wavs).

    python scripts/generate_jessica_dataset.py --limit 3        # smoke test (~250 credits)
    python scripts/generate_jessica_dataset.py --max-chars 24000   # full run, capped
"""
import argparse
import json
import random
import re
import subprocess
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from jessica_corpus import CORPUS

ROOT = Path(__file__).resolve().parent.parent
VOICE_ID = "r1KmysJdVYZjJCm4mL3b"          # Jessica
MODEL_ID = "eleven_multilingual_v2"         # max fidelity (latency irrelevant offline)
VOICE_SETTINGS = {"stability": 0.5, "similarity_boost": 0.8, "style": 0.0, "use_speaker_boost": True}
SAFETY_BUFFER = 1200                        # stay this many credits under the limit
API = "https://api.elevenlabs.io/v1"

_fmt = {"cur": "pcm_22050"}                 # try PCM first; fall back to mp3 if unsupported


def api_key():
    env = (ROOT / ".env").read_text(encoding="utf-8")
    return re.search(r"ELEVENLABS_API_KEY\s*=\s*(\S+)", env).group(1).strip()


def get_json(url, key):
    req = urllib.request.Request(url, headers={"xi-api-key": key})
    return json.load(urllib.request.urlopen(req, timeout=30))


def used_credits(key):
    s = get_json(f"{API}/user/subscription", key)
    return s["character_count"], s["character_limit"]


def tts(text, key):
    """Return raw audio bytes in the current format, retrying/falling back as needed."""
    body = json.dumps({"text": text, "model_id": MODEL_ID, "voice_settings": VOICE_SETTINGS}).encode()
    for attempt in range(4):
        url = f"{API}/text-to-speech/{VOICE_ID}?output_format={_fmt['cur']}"
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"xi-api-key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")[:300]
            if e.code in (400, 403) and "output_format" in msg.lower() and _fmt["cur"].startswith("pcm"):
                print(f"    [i] PCM not available ({e.code}); falling back to mp3_44100_128")
                _fmt["cur"] = "mp3_44100_128"
                continue
            if e.code == 429 or e.code >= 500:
                wait = 5 * (attempt + 1)
                print(f"    [!] HTTP {e.code}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg}")
    raise RuntimeError("exhausted retries")


def save_audio(raw, wav_path):
    if _fmt["cur"].startswith("pcm"):
        sr = int(_fmt["cur"].split("_")[1])
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(raw)
    else:  # mp3 -> 22050 mono s16 wav
        mp3 = wav_path.with_suffix(".mp3")
        mp3.write_bytes(raw)
        subprocess.run(["ffmpeg", "-y", "-i", str(mp3), "-ar", "22050", "-ac", "1",
                        "-sample_fmt", "s16", str(wav_path)], capture_output=True)
        mp3.unlink(missing_ok=True)


def write_metadata(meta_path, entries):
    with open(meta_path, "w", encoding="utf-8") as f:
        for cid in sorted(entries):
            t = entries[cid]
            f.write(f"{cid}|{t}|{t}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max clips (smoke test)")
    ap.add_argument("--max-chars", type=int, default=24000, help="self-imposed character cap")
    ap.add_argument("--out", default=str(ROOT / "data" / "jessica_voice"))
    args = ap.parse_args()

    out = Path(args.out); wavs = out / "wavs"; wavs.mkdir(parents=True, exist_ok=True)
    meta_path = out / "metadata.csv"
    key = api_key()

    sentences = list(CORPUS)
    random.Random(42).shuffle(sentences)          # balanced prefix if we stop early
    if args.limit:
        sentences = sentences[: args.limit]

    base_used, limit = used_credits(key)
    ceiling = limit - SAFETY_BUFFER
    print(f"[i] usage {base_used}/{limit} | ceiling {ceiling} | model {MODEL_ID} | fmt {_fmt['cur']}")

    # resume: keep transcripts for clips already on disk
    entries = {}
    for i, text in enumerate(sentences, 1):
        cid = f"jessica_{i:04d}"
        if (wavs / f"{cid}.wav").exists():
            entries[cid] = text

    last_used = base_used
    chars_since_poll = 0
    made = 0
    for i, text in enumerate(sentences, 1):
        cid = f"jessica_{i:04d}"
        wav_path = wavs / f"{cid}.wav"
        if wav_path.exists():
            continue
        # budget guards (worst case 1 credit/char between polls)
        if last_used + chars_since_poll + len(text) > ceiling:
            print(f"[stop] budget ceiling reached (~{last_used + chars_since_poll} used).")
            break
        if sum(len(entries[c]) for c in entries) + len(text) > args.max_chars:
            print(f"[stop] self-imposed --max-chars {args.max_chars} reached.")
            break
        try:
            raw = tts(text, key)
            save_audio(raw, wav_path)
        except Exception as e:
            print(f"  [!] {cid} failed: {e}")
            continue
        entries[cid] = text
        write_metadata(meta_path, entries)
        chars_since_poll += len(text)
        made += 1
        print(f"  [{made}] {cid} ({len(text)}c): {text[:48]}...")
        if made % 10 == 0:
            try:
                last_used, limit = used_credits(key)
                chars_since_poll = 0
                print(f"      usage {last_used}/{limit}  (consumed {last_used - base_used} so far)")
            except Exception:
                pass
        time.sleep(0.3)

    write_metadata(meta_path, entries)
    final_used, _ = used_credits(key)
    total_chars = sum(len(entries[c]) for c in entries)
    print(f"\n[+] clips on disk: {len(entries)} | transcript chars: {total_chars}")
    print(f"[+] credits consumed this session: {final_used - base_used}")
    print(f"[+] dataset -> {out}")


if __name__ == "__main__":
    main()
