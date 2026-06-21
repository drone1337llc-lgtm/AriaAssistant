# XTTS v2 Voice Fine-Tuning — End-to-End Training Script
# Run from the Coqui-TTS-XTTS-v2 directory:
#   python scripts/train_my_voice.py
# Or pass a custom path:
#   python scripts/train_my_voice.py --input_dir "C:\path\to\my\recordings"

import os
import sys
import argparse
import subprocess
import shutil
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # Coqui-TTS-XTTS-v2 root

# Training output
RUN_NAME = "XTTS_v2_AstroBud_Voice"
PROJECT_NAME = "xtts_voice_training"
OUT_PATH = PROJECT_ROOT / "run" / "training"
CHECKPOINTS_OUT_PATH = OUT_PATH / "XTTS_v2_original_model_files"

# Audio preprocessing
TARGET_SAMPLE_RATE = 22050  # XTTS v2 expects 22050 Hz mono WAV
AUDIO_FOLDER_NAME = "wavs"   # expected subfolder name

# Training params tuned for RTX 4080 (16 GB VRAM)
BATCH_SIZE = 2               # safe for 16 GB; increase if you OOM
GRAD_ACUMM_STEPS = 126       # effective batch = 2 * 126 = 252
NUM_WORKERS = 6

# Test sentences (use a reference from your own training data)
SPEAKER_REFERENCE = []       # populated after preprocessing
LANGUAGE = "en"

# ── Step 1: Discover MP3s ────────────────────────────────────────────────────
def find_mp3s(input_dir: Path) -> list[Path]:
    mp3s = list(input_dir.rglob("*.mp3")) + list(input_dir.rglob("*.MP3"))
    if not mp3s:
        print(f"[!] No MP3 files found in {input_dir}")
        sys.exit(1)
    print(f"[+] Found {len(mp3s)} MP3 file(s)")
    return mp3s


# ── Step 2: Preprocess audio ─────────────────────────────────────────────────
def preprocess_audio(mp3s: list[Path], wav_dir: Path, force: bool = False):
    wav_dir = Path(wav_dir)
    wav_dir.mkdir(parents=True, exist_ok=True)

    # Track how many are already converted
    to_convert = []
    for mp3 in mp3s:
        wav_name = mp3.stem + ".wav"
        wav_path = wav_dir / wav_name
        if force or not wav_path.exists():
            to_convert.append((mp3, wav_path))
        else:
            print(f"  [=] {mp3.name} → already converted, skipping")

    if not to_convert:
        print("[+] All files already converted.")
        return

    print(f"[+] Converting {len(to_convert)} file(s) to {TARGET_SAMPLE_RATE}Hz mono WAV...")

    for i, (mp3_path, wav_path) in enumerate(to_convert, 1):
        print(f"  [{i}/{len(to_convert)}] {mp3_path.name} → {wav_path.name}")
        try:
            # ffmpeg is the most reliable way on Windows
            result = subprocess.run([
                "ffmpeg", "-y",
                "-i", str(mp3_path),
                "-ar", str(TARGET_SAMPLE_RATE),
                "-ac", "1",          # mono
                "-c:a", "pcm_s16le", # 16-bit PCM
                str(wav_path)
            ], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  [!] ffmpeg error on {mp3_path.name}:")
                print(result.stderr[-500:])
                sys.exit(1)
        except FileNotFoundError:
            print("[!] ffmpeg not found. Install ffmpeg and add it to PATH.")
            print("    Download: https://ffmpeg.org/download.html")
            sys.exit(1)

    print(f"[+] Audio converted → {wav_dir}")


# ── Step 3: Build metadata CSV ────────────────────────────────────────────────
def build_csv(wav_dir: Path, meta_path: Path):
    wavs = sorted(wav_dir.glob("*.wav"))
    if not wavs:
        print("[!] No WAV files found.")
        sys.exit(1)

    # Try to use the filename (without extension) as the text
    # If user has separate transcripts, they can replace this section.
    # Format: ID|text|normalized_text
    with open(meta_path, "w", encoding="utf-8") as f:
        for wav in wavs:
            # Use filename as placeholder text — XTTS will train on audio, not text
            # Replace with actual transcription if you have them
            text = wav.stem.replace("_", " ").replace("-", " ")
            row = f"{wav.stem}|{text}|{text}\n"
            f.write(row)

    print(f"[+] Metadata CSV written → {meta_path} ({len(wavs)} entries)")


# ── Step 4: Download base model checkpoints ─────────────────────────────────
def download_checkpoints():
    sys.path.insert(0, str(PROJECT_ROOT))
    from TTS.utils.manage import ModelManager

    CHECKPOINTS_OUT_PATH.mkdir(parents=True, exist_ok=True)

    files = {
        "DVAE": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/dvae.pth",
        "MelNorm": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/mel_stats.pth",
        "Tokenizer": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/vocab.json",
        "XTTS": "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/model.pth",
    }

    for name, url in files.items():
        local = CHECKPOINTS_OUT_PATH / Path(url).name
        if local.exists():
            print(f"  [=] {name} already downloaded")
        else:
            print(f"  [↓] Downloading {name}...")
            ModelManager._download_model_files([url], str(CHECKPOINTS_OUT_PATH), progress_bar=True)

    print("[+] Checkpoints ready")


# ── Step 5: Run training ──────────────────────────────────────────────────────
def run_training(wav_dir: Path, meta_path: Path):
    sys.path.insert(0, str(PROJECT_ROOT))
    from trainer import Trainer, TrainerArgs
    from TTS.config.shared_configs import BaseDatasetConfig
    from TTS.tts.datasets import load_tts_samples
    from TTS.tts.layers.xtts.trainer.gpt_trainer import GPTArgs, GPTTrainer, GPTTrainerConfig, XttsAudioConfig

    # Dataset config
    dataset_config = BaseDatasetConfig(
        formatter="ljspeech",
        dataset_name="astrobud_voice",
        path=str(wav_dir.parent),
        meta_file_train=str(meta_path.name),
        language=LANGUAGE,
    )

    # Paths
    DVAE_CHECKPOINT = str(CHECKPOINTS_OUT_PATH / "dvae.pth")
    MEL_NORM_FILE = str(CHECKPOINTS_OUT_PATH / "mel_stats.pth")
    TOKENIZER_FILE = str(CHECKPOINTS_OUT_PATH / "vocab.json")
    XTTS_CHECKPOINT = str(CHECKPOINTS_OUT_PATH / "model.pth")

    # Pick first wav as test reference
    first_wav = sorted(Path(wav_dir).glob("*.wav"))[0]
    SPEAKER_REFERENCE_LOCAL = [str(first_wav)]

    # GPT model args
    model_args = GPTArgs(
        max_conditioning_length=132300,   # 6 seconds
        min_conditioning_length=66150,     # 3 seconds
        debug_loading_failures=False,
        max_wav_length=255995,             # ~11.6 seconds
        max_text_length=200,
        mel_norm_file=MEL_NORM_FILE,
        dvae_checkpoint=DVAE_CHECKPOINT,
        xtts_checkpoint=XTTS_CHECKPOINT,
        tokenizer_file=TOKENIZER_FILE,
        gpt_num_audio_tokens=1026,
        gpt_start_audio_token=1024,
        gpt_stop_audio_token=1025,
        gpt_use_masking_gt_prompt_approach=True,
        gpt_use_perceiver_resampler=True,
    )

    audio_config = XttsAudioConfig(
        sample_rate=TARGET_SAMPLE_RATE,
        dvae_sample_rate=TARGET_SAMPLE_RATE,
        output_sample_rate=24000,
    )

    config = GPTTrainerConfig(
        output_path=str(OUT_PATH),
        model_args=model_args,
        run_name=RUN_NAME,
        project_name=PROJECT_NAME,
        run_description="XTTS v2 fine-tuning for AstroBud voice",
        dashboard_logger="tensorboard",
        logger_uri=None,
        audio=audio_config,
        batch_size=BATCH_SIZE,
        batch_group_size=48,
        eval_batch_size=BATCH_SIZE,
        num_loader_workers=NUM_WORKERS,
        eval_split_max_size=256,
        print_step=50,
        plot_step=200,
        log_model_step=2000,
        save_step=10000,
        save_n_checkpoints=2,
        save_checkpoints=True,
        optimizer="AdamW",
        optimizer_wd_only_on_weights=True,
        optimizer_params={"betas": [0.9, 0.96], "eps": 1e-8, "weight_decay": 1e-2},
        lr=5e-6,
        lr_scheduler="MultiStepLR",
        lr_scheduler_params={"milestones": [50000 * 18, 150000 * 18, 300000 * 18], "gamma": 0.5, "last_epoch": -1},
        test_sentences=[
            {
                "text": "It took me quite a long time to develop a voice, and now that I have it I'm not going to be silent.",
                "speaker_wav": SPEAKER_REFERENCE_LOCAL,
                "language": LANGUAGE,
            },
            {
                "text": "Hello, I am AstroBud, your desktop AI assistant. How can I help you today?",
                "speaker_wav": SPEAKER_REFERENCE_LOCAL,
                "language": LANGUAGE,
            },
        ],
    )

    model = GPTTrainer.init_from_config(config)

    train_samples, eval_samples = load_tts_samples(
        [dataset_config],
        eval_split=True,
        eval_split_max_size=config.eval_split_max_size,
        eval_split_size=config.eval_split_size,
    )

    trainer = Trainer(
        TrainerArgs(
            restore_path=None,
            skip_train_epoch=False,
            start_with_eval=True,
            grad_accum_steps=GRAD_ACUMM_STEPS,
        ),
        config,
        output_path=str(OUT_PATH),
        model=model,
        train_samples=train_samples,
        eval_samples=eval_samples,
    )

    print("[+] Starting training — check TensorBoard at http://localhost:6006")
    trainer.fit()


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="XTTS v2 voice fine-tuning")
    parser.add_argument(
        "--input_dir",
        type=str,
        default=None,
        help="Folder containing your MP3 recordings. "
             "Defaults to ./my_voice_recordings/ relative to this script.",
    )
    parser.add_argument(
        "--force_reconvert",
        action="store_true",
        help="Reconvert all MP3s even if WAV already exists.",
    )
    args = parser.parse_args()

    # Resolve input directory
    if args.input_dir:
        input_dir = Path(args.input_dir).resolve()
    else:
        input_dir = SCRIPT_DIR / "my_voice_recordings"

    if not input_dir.exists():
        print(f"[!] Input directory not found: {input_dir}")
        print("    Pass --input_dir to point at your MP3 folder.")
        sys.exit(1)

    # Working directory for training data
    work_dir = PROJECT_ROOT / "data" / "astrobud_voice"
    wav_dir = work_dir / AUDIO_FOLDER_NAME
    meta_path = work_dir / "metadata.csv"

    print(f"\n{'='*60}")
    print(f" XTTS v2 Voice Training — AstroBud Voice Clone")
    print(f"{'='*60}")
    print(f"  Input MP3s : {input_dir}")
    print(f"  Working dir: {work_dir}")
    print(f"  WAV output : {wav_dir}")
    print(f"  Checkpoints: {CHECKPOINTS_OUT_PATH}")
    print()

    # Step 1 — find MP3s
    mp3s = find_mp3s(input_dir)

    # Step 2 — convert to WAV
    preprocess_audio(mp3s, wav_dir, force=args.force_reconvert)

    # Step 3 — build CSV
    build_csv(wav_dir, meta_path)

    # Step 4 — download base model
    print("\n[+] Downloading XTTS v2 base checkpoints...")
    download_checkpoints()

    # Step 5 — train
    print("\n[+] Launching training...")
    run_training(wav_dir, meta_path)


if __name__ == "__main__":
    main()