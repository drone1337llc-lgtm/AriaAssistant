# ElevenLabs Reference Sample Generator
# Uses the ElevenLabs TTS API with Ana's voice to generate high-quality
# reference samples for professional fine-tuning.
#
# Run: python scripts/generate_reference_samples.py

import os
import sys
import requests
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY = "972e4fc0fdb74834fa34422c1b228b7b82cd971628659d461073759081925bfa"
VOICE_ID = "HV4UOL5rtTGkWTULlq6W"  # Ana
BASE_URL = "https://api.elevenlabs.io/v1"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "elevenlabs_reference"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"xi-api-key": API_KEY}

# Sample texts — varied to capture voice nuances for fine-tuning
# Total duration target: 3-5 minutes of clean audio
SAMPLES = [
    # Short prompts (2-4s each) — 10 samples
    ("Hello, I'm AstroBud, your personal desktop AI assistant. How can I help you today?", 1),
    ("The quick brown fox jumps over the lazy dog. Every letter of the alphabet.", 1),
    ("I can read your screen, run code, and manage your calendar instantly.", 1),
    ("That's a really interesting point. Tell me more about what you found.", 1),
    ("I'll get that done for you right away. Give me just a moment.", 1),
    ("Machine learning is transforming the way we interact with technology.", 1),
    ("Thanks for asking. I really appreciate you taking the time to chat with me.", 1),
    ("This is going to be fun. I love working on new projects with creative people.", 1),
    ("Alright, I've finished. Let me know if you'd like me to make any changes.", 1),
    ("Would you like me to play some music while we work?", 1),
    # Medium prompts (4-8s) — 10 samples
    ("Good morning! I hope you had a restful sleep. What are we working on today? I've been looking forward to helping you with whatever you need.", 1),
    ("I've been thinking about this problem for a while and I think I have a good solution. Let me walk you through my reasoning step by step.", 1),
    ("I've analyzed the data and here's what I found: the results are quite interesting. There are some patterns that weren't obvious at first glance.", 1),
    ("Don't worry, this is a common issue and it's easy to fix once you know how. I've seen this happen many times before.", 1),
    ("I'm currently training a voice model using advanced deep learning techniques. The process involves generating spectrograms and then converting them to audio.", 1),
    ("Your AI assistant is getting smarter every day. Thanks for teaching me new things and helping me understand your preferences better.", 1),
    ("Okay, let's wrap this up. Anything else you'd like to cover before we finish? I want to make sure we address everything on your list.", 1),
    ("Let's go for a walk around the block and see what the neighbors are up to. The weather is nice today and we could use the fresh air.", 1),
    ("That makes sense. Let me try a different approach and see if it works better. Sometimes it takes a few attempts to get things right.", 1),
    ("I've been working on this project for several weeks now and I'm really happy with how it's turning out. The team has been great to work with.", 1),
]

# ── Generate samples via ElevenLabs API ──────────────────────────────────────
def generate_audio(text: str, filename: str) -> bool:
    url = f"{BASE_URL}/text-to-speech/{VOICE_ID}"
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.85,
            "style": 0.15,
            "use_speaker_boost": True,
        },
    }
    resp = requests.post(url, json=payload, headers=HEADERS)
    if resp.status_code == 200:
        with open(filename, "wb") as f:
            f.write(resp.content)
        return True
    else:
        print(f"  [!] Error: {resp.status_code} {resp.text[:200]}")
        return False


def get_duration(filename: str) -> float:
    try:
        import scipy.io.wavfile as wavfile
        sr, data = wavfile.read(filename)
        return len(data) / sr
    except Exception:
        return 0


# ── Main ─────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f" ElevenLabs Reference Sample Generator — Ana")
print(f"{'='*60}")

# Check remaining credits
r = requests.get(f"{BASE_URL}/user", headers=HEADERS)
if r.status_code == 200:
    sub = r.json()["subscription"]
    remaining = sub["character_count"]
    limit = sub["character_limit"]
    print(f"Credits: {remaining}/{limit} ({remaining/limit*100:.1f}% used)")
else:
    print(f"[!] Could not check credits: {r.status_code}")

print(f"Output: {OUTPUT_DIR}")
print(f"Voice: Ana ({VOICE_ID})")
print(f"Samples: {len(SAMPLES)}")

total_chars = sum(len(s) for s, _ in SAMPLES)
print(f"Est. characters: ~{total_chars}")

if total_chars > remaining:
    print(f"\n[!] WARNING: estimated {total_chars} chars > {remaining} remaining credits")
    print("    Proceed anyway? Press Ctrl+C to abort, or wait 5s to continue...")
    import time; time.sleep(5)

print()

success = 0
fail = 0
total_dur = 0
for i, (text, _) in enumerate(SAMPLES, 1):
    filename = OUTPUT_DIR / f"sample_{i:02d}.wav"
    print(f"[{i}/{len(SAMPLES)}] Generating: {text[:50]}...")
    if generate_audio(text, str(filename)):
        dur = get_duration(str(filename))
        total_dur += dur
        print(f"  ✓ {filename.name} ({dur:.1f}s)")
        success += 1
    else:
        fail += 1

print(f"\n{'='*60}")
print(f" Results: {success} success, {fail} failed")
print(f" Total audio: {total_dur:.1f}s ({total_dur/60:.1f} min)")
print(f" Output: {OUTPUT_DIR}")
print(f"{'='*60}")

# Clean up tiny files (failed generations)
tiny = [f for f in OUTPUT_DIR.glob("*.wav") if f.stat().st_size < 5000]
if tiny:
    print(f"\n[!] Removing {len(tiny)} tiny/empty files:")
    for f in tiny:
        print(f"  - {f.name}")
        f.unlink()