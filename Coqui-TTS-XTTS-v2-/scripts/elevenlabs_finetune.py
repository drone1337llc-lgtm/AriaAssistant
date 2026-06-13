# ElevenLabs Professional Voice Fine-Tune
# Uploads reference audio samples and triggers professional fine-tuning.
#
# Prerequisites:
#   pip install requests
#
# Run: python scripts/elevenlabs_finetune.py --api_key HV4UOL5rtTGkWTULlq6W

import os
import sys
import argparse
import time
import requests
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY = None          # Set via --api_key or XI_API_KEY env var
BASE_URL = "https://api.elevenlabs.io/v1"

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "data" / "elevenlabs_reference"

HEADERS = {}

def api_headers():
    return {"xi-api-key": API_KEY or os.environ.get("XI_API_KEY", "")}


# ── Step 1: Verify API key ────────────────────────────────────────────────────
def verify_api_key():
    resp = requests.get(f"{BASE_URL}/voices", headers=api_headers())
    if resp.status_code == 200:
        voices = resp.json()
        print(f"[+] API key valid. Current voices: {len(voices.get('voices', []))}")
        return True
    elif resp.status_code == 401:
        print("[!] Invalid API key. Check your key and try again.")
        return False
    else:
        print(f"[!] API error: {resp.status_code} {resp.text}")
        return False


# ── Step 2: Upload reference samples ─────────────────────────────────────────
def upload_samples(wav_files: list[Path]) -> list[dict]:
    uploaded = []
    for i, wav in enumerate(wav_files, 1):
        print(f"  [{i}/{len(wav_files)}] Uploading {wav.name}...")
        with open(wav, "rb") as f:
            resp = requests.post(
                f"{BASE_URL}/voices/add/upload",
                headers={**api_headers(), "Content-Type": "audio/wav"},
                data=f.read(),
            )
        if resp.status_code == 200:
            result = resp.json()
            print(f"    → {result.get('name', wav.name)} uploaded OK")
            uploaded.append(result)
        else:
            print(f"    [!] Failed ({resp.status_code}): {resp.text[:200]}")
    return uploaded


# ── Step 3: Start fine-tuning job ─────────────────────────────────────────────
def start_finetune(voice_id: str, name: str = "AstroBud Voice") -> dict:
    print(f"\n[+] Starting ElevenLabs fine-tune for voice_id: {voice_id}")
    resp = requests.post(
        f"{BASE_URL}/voices/{voice_id}/fine-tune",
        headers=api_headers(),
        json={"name": name},
    )
    if resp.status_code in (200, 201):
        return resp.json()
    elif resp.status_code == 429:
        print("[!] Rate limited. Waiting 60s and retrying...")
        time.sleep(60)
        return start_finetune(voice_id, name)
    else:
        print(f"[!] Fine-tune start failed: {resp.status_code} {resp.text}")
        return None


# ── Step 4: Poll for completion ───────────────────────────────────────────────
def wait_for_finetune(voice_id: str, poll_interval: int = 30):
    print("\n[*] Polling for fine-tune completion...")
    while True:
        resp = requests.get(f"{BASE_URL}/voices/{voice_id}", headers=api_headers())
        if resp.status_code != 200:
            print(f"[!] Status check failed: {resp.status_code}")
            break

        data = resp.json()
        fine_tuning = data.get("fine_tuning", {})

        status = fine_tunes_status = fine_tuning.get("status", "unknown")
        quality = fine_tuning.get("quality", "unknown")

        print(f"  Status: {status} | Quality: {quality}")

        if status in ("completed", "done"):
            print("\n[+] Fine-tuning complete!")
            print(f"    Voice ID: {voice_id}")
            print(f"    Quality: {quality}")
            return data
        elif status in ("failed", "error"):
            print(f"\n[!] Fine-tune failed: {fine_tuning}")
            return None

        print(f"  Waiting {poll_interval}s...")
        time.sleep(poll_interval)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="ElevenLabs voice fine-tuning")
    parser.add_argument("--api_key", type=str, default=os.environ.get("XI_API_KEY"))
    parser.add_argument(
        "--reference_dir",
        type=str,
        default=str(REFERENCE_DIR),
        help="Folder with reference WAV samples",
    )
    parser.add_argument(
        "--voice_name",
        type=str,
        default="AstroBud Voice",
        help="Name for the fine-tuned voice",
    )
    args = parser.parse_args()

    global API_KEY
    API_KEY = args.api_key

    if not API_KEY:
        print("[!] No API key. Set --api_key or XI_API_KEY env variable.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f" ElevenLabs Voice Fine-Tuning — AstroBud")
    print(f"{'='*60}")

    # Step 1 — verify key
    if not verify_api_key():
        sys.exit(1)

    # Step 2 — find WAV files
    ref_dir = Path(args.reference_dir)
    if not ref_dir.exists():
        print(f"[!] Reference directory not found: {ref_dir}")
        print("    Run generate_reference_samples.py first to produce the samples.")
        sys.exit(1)

    wav_files = sorted(ref_dir.glob("*.wav"))
    if len(wav_files) < 1:
        print(f"[!] No WAV files found in {ref_dir}")
        sys.exit(1)
    print(f"\n[+] Found {len(wav_files)} reference samples")

    # Show credits info
    resp = requests.get(f"{BASE_URL}/user", headers=api_headers())
    if resp.status_code == 200:
        user = resp.json()
        credits = user.get("subscription", {}).get("character_count", "unknown")
        print(f"    Available credits: {credits}")

    # Step 3 — upload
    print(f"\n[+] Uploading samples to ElevenLabs...")
    samples = upload_samples(wav_files)

    if not samples:
        print("[!] No samples uploaded successfully.")
        sys.exit(1)

    # Get the voice ID from the first successful upload
    voice_id = samples[0].get("voice_id")
    if not voice_id:
        print(f"[!] Could not get voice_id from upload response: {samples[0]}")
        sys.exit(1)

    print(f"\n[+] Voice created with ID: {voice_id}")

    # Step 4 — start fine-tune
    result = start_finetune(voice_id, name=args.voice_name)
    if not result:
        sys.exit(1)

    # Step 5 — poll
    final = wait_for_finetune(voice_id)

    if final:
        print(f"\n{'='*60}")
        print(f" ✓ Fine-tuning complete!")
        print(f"   Voice ID : {voice_id}")
        print(f"   Name     : {final.get('name', 'AstroBud Voice')}")
        print(f"   Share URL: {final.get('share_url', 'N/A')}")
        print(f"{'='*60}")
        print("\nAdd this to your AstroBud config:")
        print(f'  voice_model = "elevenlabs"')
        print(f'  elevenlabs_voice_id = "{voice_id}"')


if __name__ == "__main__":
    main()