# XTTS v2 fine-tune — "Jessica" voice (single speaker, naturalness-tuned)
# Same optimized recipe as train_ana_voice.py, pointed at the larger, cleaner,
# loudness-normalized Jessica dataset (272 diverse clips, 17 min).
#
#   & "C:\Program Files\Python312\python.exe" scripts/train_jessica_voice.py

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

RUN_NAME = "XTTS_v2_Jessica_Voice"
PROJECT_NAME = "xtts_voice_training"
OUT_PATH = PROJECT_ROOT / "run" / "training"
BASE_FILES = OUT_PATH / "XTTS_v2_original_model_files"

DATA_DIR = PROJECT_ROOT / "data" / "jessica_voice"
WAV_DIR = DATA_DIR / "wavs"
META = "metadata.csv"
SPEAKER_REFERENCE = [str(WAV_DIR / "jessica_0123.wav")]   # the "Hello, I'm Jessica..." greeting
LANGUAGE = "en"

BATCH_SIZE = 3
GRAD_ACUMM = 6           # effective batch 18
NUM_WORKERS = 6
EPOCHS = 40              # cap; best_model.pth (lowest eval loss) is the deliverable
LR = 5e-6


def main():
    dataset_config = BaseDatasetConfig(
        formatter="ljspeech", dataset_name="jessica_voice",
        path=str(DATA_DIR), meta_file_train=META, language=LANGUAGE,
    )

    model_args = GPTArgs(
        max_conditioning_length=132300, min_conditioning_length=66150,
        debug_loading_failures=False,
        max_wav_length=255995,            # ~11.6 s; all clips are <= 9.2 s
        max_text_length=200,
        mel_norm_file=str(BASE_FILES / "mel_stats.pth"),
        dvae_checkpoint=str(BASE_FILES / "dvae.pth"),
        xtts_checkpoint=str(BASE_FILES / "model.pth"),
        tokenizer_file=str(BASE_FILES / "vocab.json"),
        gpt_num_audio_tokens=1026, gpt_start_audio_token=1024, gpt_stop_audio_token=1025,
        gpt_use_masking_gt_prompt_approach=True, gpt_use_perceiver_resampler=True,
    )
    audio_config = XttsAudioConfig(sample_rate=22050, dvae_sample_rate=22050, output_sample_rate=24000)

    config = GPTTrainerConfig(
        output_path=str(OUT_PATH), model_args=model_args,
        run_name=RUN_NAME, project_name=PROJECT_NAME,
        run_description="XTTS v2 fine-tune — Jessica voice (single speaker, naturalness-tuned)",
        dashboard_logger="tensorboard", logger_uri=None, audio=audio_config,
        epochs=EPOCHS, batch_size=BATCH_SIZE, batch_group_size=48, eval_batch_size=BATCH_SIZE,
        num_loader_workers=NUM_WORKERS, num_eval_loader_workers=0,
        eval_split_max_size=256, eval_split_size=0.05,
        print_step=25, plot_step=100, log_model_step=1000,
        save_step=2000, save_n_checkpoints=1, save_best_after=0, save_checkpoints=True,
        run_eval=True, test_delay_epochs=0,
        optimizer="AdamW", optimizer_wd_only_on_weights=True,
        optimizer_params={"betas": [0.9, 0.96], "eps": 1e-8, "weight_decay": 1e-2},
        lr=LR, lr_scheduler="MultiStepLR",
        lr_scheduler_params={"milestones": [9_000_000], "gamma": 0.5, "last_epoch": -1},
        test_sentences=[
            {"text": "Hello, I'm Jessica. What would you like to work on this morning?",
             "speaker_wav": SPEAKER_REFERENCE, "language": LANGUAGE},
            {"text": "Let me pull up those numbers and walk you through what changed.",
             "speaker_wav": SPEAKER_REFERENCE, "language": LANGUAGE},
            {"text": "It's a quiet evening, and the city outside has finally settled into stillness.",
             "speaker_wav": SPEAKER_REFERENCE, "language": LANGUAGE},
        ],
    )

    model = GPTTrainer.init_from_config(config)
    train_samples, eval_samples = load_tts_samples(
        [dataset_config], eval_split=True,
        eval_split_max_size=config.eval_split_max_size, eval_split_size=config.eval_split_size,
    )
    print(f"[+] train clips: {len(train_samples)} | eval clips: {len(eval_samples)}")

    trainer = Trainer(
        TrainerArgs(restore_path=None, skip_train_epoch=False, start_with_eval=True,
                    grad_accum_steps=GRAD_ACUMM),
        config, output_path=str(OUT_PATH), model=model,
        train_samples=train_samples, eval_samples=eval_samples,
    )
    print("[+] Training Jessica voice — best_model.pth = lowest eval loss")
    trainer.fit()


if __name__ == "__main__":
    main()
