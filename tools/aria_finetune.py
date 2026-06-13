#!/usr/bin/env python3
"""
aria_finetune.py — daily LoRA fine-tune of Aria's persona on her own chat log.

WHAT IT DOES
  1. Reads the conversation dataset Aria writes at runtime
     (aria_dataset.jsonl — one JSON object per turn).
  2. Drops "offline" fallback turns (those aren't real model output).
  3. Formats each turn as a chat pair: user -> assistant(JSON say/emotion/action).
  4. Runs a short LoRA SFT pass on your local base model and saves an adapter
     stamped with today's date.

THIS IS A TEMPLATE. You must set the CONFIG block below to point at one of your
local base models and confirm your training libs (transformers / peft / trl /
torch) are installed in the AI Learning venv. Run it by hand once; when it's
clean, schedule it (Task Scheduler or a Cowork scheduled task) to run nightly,
then point Aria's ModelName / adapter at the newest output each morning.

If the training libraries aren't present, the script still runs in --check mode:
it validates and summarises the dataset so you can see it's being collected.

Usage:
    python aria_finetune.py            # full fine-tune (needs libs + GPU)
    python aria_finetune.py --check    # just validate/summarise the dataset
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import date

# ─────────────────────────── CONFIG — EDIT ME ───────────────────────────
DATASET_PATH = r"C:\Users\Tench\Documents\AI Learning\aria_dataset.jsonl"
OUTPUT_DIR   = r"C:\Users\Tench\Documents\AI Learning\adapters"
# Point this at a LOCAL base model directory or HF id you actually have:
BASE_MODEL   = r"C:\Users\Tench\Documents\AI Learning\models\Meta-Llama-3-8B-Instruct"
EPOCHS       = 1
LEARNING_RATE = 2e-4
LORA_R       = 16
LORA_ALPHA   = 32
MAX_SEQ_LEN  = 1024
MIN_EXAMPLES = 20          # don't bother training on fewer than this
# ─────────────────────────────────────────────────────────────────────────

SYSTEM = (
    "You are Aria, a virtually-sentient anime companion living on the user's "
    "desktop. Reply with one compact line of JSON: "
    '{"say":"...","emotion":"neutral|joy|fun|sad|angry|surprised",'
    '"action":"none|wave|dance|sit|look|thankful|react"}.'
)


def load_examples(path: str) -> list[dict]:
    """Read the JSONL log, skip offline/malformed lines, dedupe."""
    if not os.path.exists(path):
        print(f"[finetune] dataset not found: {path}")
        return []
    examples, seen = [], set()
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                print(f"[finetune] skipping malformed line {ln}")
                continue
            if row.get("offline"):
                continue
            user = (row.get("user") or "").strip()
            say = (row.get("say") or "").strip()
            if not user or not say:
                continue
            key = (user, say)
            if key in seen:
                continue
            seen.add(key)
            assistant = json.dumps(
                {
                    "say": say,
                    "emotion": row.get("emotion", "neutral"),
                    "action": row.get("action", "none"),
                },
                ensure_ascii=False,
            )
            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": user},
                        {"role": "assistant", "content": assistant},
                    ]
                }
            )
    return examples


def summarise(examples: list[dict]) -> None:
    from collections import Counter
    emo = Counter()
    act = Counter()
    for ex in examples:
        try:
            a = json.loads(ex["messages"][-1]["content"])
            emo[a.get("emotion", "?")] += 1
            act[a.get("action", "?")] += 1
        except Exception:
            pass
    print(f"[finetune] usable examples: {len(examples)}")
    print(f"[finetune] emotions: {dict(emo)}")
    print(f"[finetune] actions:  {dict(act)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="validate/summarise the dataset and exit")
    args = ap.parse_args()

    examples = load_examples(DATASET_PATH)
    summarise(examples)

    if args.check:
        return 0
    if len(examples) < MIN_EXAMPLES:
        print(f"[finetune] only {len(examples)} examples (< {MIN_EXAMPLES}); "
              f"collect more chat first. Exiting without training.")
        return 0

    # Heavy imports are deferred so --check works without a training stack.
    try:
        import torch
        from datasets import Dataset
        from transformers import (AutoModelForCausalLM, AutoTokenizer,
                                   TrainingArguments)
        from peft import LoraConfig
        from trl import SFTTrainer
    except ImportError as e:
        print(f"[finetune] training libs missing ({e}). "
              f"Install torch/transformers/peft/trl/datasets in your AI Learning "
              f"venv, or run with --check. Exiting.")
        return 1

    if not os.path.isdir(BASE_MODEL):
        print(f"[finetune] BASE_MODEL not found: {BASE_MODEL}. Edit the CONFIG block.")
        return 1

    out = os.path.join(OUTPUT_DIR, f"aria-lora-{date.today().isoformat()}")
    os.makedirs(out, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    def fmt(row):
        return {"text": tok.apply_chat_template(row["messages"], tokenize=False)}

    ds = Dataset.from_list(examples).map(fmt)

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
    )

    peft_cfg = LoraConfig(
        r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=0.05,
        bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=ds,
        peft_config=peft_cfg,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        args=TrainingArguments(
            output_dir=out,
            num_train_epochs=EPOCHS,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=8,
            learning_rate=LEARNING_RATE,
            logging_steps=5,
            save_strategy="epoch",
            bf16=torch.cuda.is_available(),
        ),
    )
    trainer.train()
    trainer.save_model(out)
    tok.save_pretrained(out)
    print(f"[finetune] saved adapter → {out}")
    print("[finetune] point Aria's ModelName/adapter at this folder to use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
