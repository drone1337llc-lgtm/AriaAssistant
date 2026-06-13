# XTTS v2 fine-tune — "ana" voice (single speaker, naturalness-tuned)
#
# Rebuilt from train_my_voice.py with the fixes from the audit:
#   * single voice only (data/ana_voice, 200 clips) — no 6-voice blend
#   * real transcripts (data/ana_voice/metadata.csv) — not filenames
#   * real eval split + short, early-stopped training — avoids the overfitting
#     that turned the previous run robotic (best eval was reached very early)
#
# Run with the training env (has Coqui TTS):
#   & "C:\Program Files\Python312\python.exe" scripts/train_ana_voice.py

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trainer import Trainer, TrainerArgs
from TTS.config.shared_configs import BaseDatasetConfig
from TTS.tts.datasets import load_tts_samples
from TTS.tts.layers.xtts.trainer.gpt_trainer import (
    GPTArgs, GPTTrainer, GPTTrainerConfig, XttsAudioConfig,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
RUN_NAME = "XTTS_v2_Ana_Voice"
PROJECT_NAME = "xtts_voice_training"
OUT_PATH = PROJECT_ROOT / "run" / "training"
BASE_FILES = OUT_PATH / "XTTS_v2_original_model_files"   # dvae/mel/vocab/model already downloaded

DATA_DIR = PROJECT_ROOT / "data" / "ana_voice"
WAV_DIR = DATA_DIR / "wavs"
META = "metadata.csv"
SPEAKER_REFERENCE = [str(WAV_DIR / "ana_0001.wav")]      # clean 5.8s greeting clip
LANGUAGE = "en"

# ── Hyperparameters (tuned for a small, single-voice, natural fine-tune) ──────
BATCH_SIZE = 3            # 16 GB 4080; drop to 2 if you OOM
GRAD_ACUMM = 6           # effective batch = 18 -> ~10 optimizer updates/epoch (fine control)
NUM_WORKERS = 6
EPOCHS = 40              # cap; the *best_model.pth* (lowest eval loss) is your model, not the last epoch
LR = 5e-6               # conservative -> preserves the natural base voice, won't over-write it


def main():
    dataset_config = BaseDatasetConfig(
        formatter="ljspeech",
        dataset_name="ana_voice",
        path=str(DATA_DIR),
        meta_file_train=META,
        language=LANGUAGE,
    )

    model_args = GPTArgs(
        max_conditioning_length=132300,   # 6 s
        min_conditioning_length=66150,    # 3 s
        debug_loading_failures=False,
        max_wav_length=255995,            # ~11.6 s (all clips are well under this)
        max_text_length=200,
        mel_norm_file=str(BASE_FILES / "mel_stats.pth"),
        dvae_checkpoint=str(BASE_FILES / "dvae.pth"),
        xtts_checkpoint=str(BASE_FILES / "model.pth"),
        tokenizer_file=str(BASE_FILES / "vocab.json"),
        gpt_num_audio_tokens=1026,
        gpt_start_audio_token=1024,
        gpt_stop_audio_token=1025,
        gpt_use_masking_gt_prompt_approach=True,
        gpt_use_perceiver_resampler=True,
    )

    audio_config = XttsAudioConfig(
        sample_rate=22050, dvae_sample_rate=22050, output_sample_rate=24000,
    )

    config = GPTTrainerConfig(
        output_path=str(OUT_PATH),
        model_args=model_args,
        run_name=RUN_NAME,
        project_name=PROJECT_NAME,
        run_description="XTTS v2 fine-tune — ana voice (single speaker, naturalness-tuned)",
        dashboard_logger="tensorboard",
        logger_uri=None,
        audio=audio_config,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        batch_group_size=48,
        eval_batch_size=BATCH_SIZE,
        num_loader_workers=NUM_WORKERS,
        num_eval_loader_workers=0,        # Windows-safe
        eval_split_max_size=256,
        eval_split_size=0.05,             # ~10 held-out clips -> trustworthy early-stop signal
        print_step=25,
        plot_step=100,
        log_model_step=1000,
        save_step=2000,
        save_n_checkpoints=1,             # keep disk down; best_model.pth is what matters
        save_best_after=0,
        save_checkpoints=True,
        run_eval=True,
        test_delay_epochs=0,
        optimizer="AdamW",
        optimizer_wd_only_on_weights=True,
        optimizer_params={"betas": [0.9, 0.96], "eps": 1e-8, "weight_decay": 1e-2},
        lr=LR,
        lr_scheduler="MultiStepLR",
        lr_scheduler_params={"milestones": [9_000_000], "gamma": 0.5, "last_epoch": -1},  # effectively constant LR
        test_sentences=[
            {"text": "Hello, I am AstroBud, your desktop AI assistant. How can I help you today?",
             "speaker_wav": SPEAKER_REFERENCE, "language": LANGUAGE},
            {"text": "Sure, I can take care of that for you. Give me just a moment to pull it up.",
             "speaker_wav": SPEAKER_REFERENCE, "language": LANGUAGE},
            {"text": "The afternoon light came softly through the window as the rain finally eased.",
             "speaker_wav": SPEAKER_REFERENCE, "language": LANGUAGE},
        ],
    )

    model = GPTTrainer.init_from_config(config)

    train_samples, eval_samples = load_tts_samples(
        [dataset_config],
        eval_split=True,
        eval_split_max_size=config.eval_split_max_size,
        eval_split_size=config.eval_split_size,
    )
    print(f"[+] train clips: {len(train_samples)} | eval clips: {len(eval_samples)}")

    trainer = Trainer(
        TrainerArgs(
            restore_path=None,
            skip_train_epoch=False,
            start_with_eval=True,         # baseline eval before any fine-tuning
            grad_accum_steps=GRAD_ACUMM,
        ),
        config,
        output_path=str(OUT_PATH),
        model=model,
        train_samples=train_samples,
        eval_samples=eval_samples,
    )

    print("[+] Training ana voice — best checkpoint saved as best_model.pth (lowest eval loss)")
    trainer.fit()


if __name__ == "__main__":
    main()
