r"""
AstroBud nightly memory compiler.

Runs at 3 AM via Windows Task Scheduler. Reads `daily_log.json`, embeds each
interaction via the local embedding model served by LM Studio, stores them
in ChromaDB for long-term recall, and clears the daily log so the file
doesn't grow unbounded.

Schedule it:
    Task Scheduler -> Create Basic Task
        Trigger: Daily, 3:00 AM
        Action:   Start a program
                  Program: python
                  Args:    "C:\Users\Tench\Documents\AI Learning\astro_assistant\nightly_memory.py"
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from chromadb import PersistentClient

import lmstudio_client as lms


PROJECT_ROOT = Path(__file__).parent.resolve()
LOG_FILE = PROJECT_ROOT / "daily_log.json"
MEMORY_DIR = PROJECT_ROOT / "astro_memory"
COLLECTION_NAME = "astro_episodic_memory"
CONFIG_PATH = PROJECT_ROOT / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"embedding_model": "nomic-embed-text-v2-moe"}


def compile_memories() -> None:
    print("[AstroBud Nightly] Memory compiler starting...")

    if not LOG_FILE.exists() or LOG_FILE.stat().st_size < 5:
        print("[AstroBud Nightly] No log file / empty. Nothing to do.")
        return

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            daily = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[AstroBud Nightly] Log file is corrupt: {e}. Leaving it alone.")
        return

    if not daily:
        print("[AstroBud Nightly] Daily log is empty. Exiting.")
        return

    cfg = load_config()
    embedding_model = cfg.get("embedding_model", "nomic-embed-text-v2-moe")

    client = lms.get_client()
    print(f"[AstroBud Nightly] Checking LM Studio server + model '{embedding_model}'...")
    info = lms.smoke_test(client)
    if not info["server_reachable"]:
        print(f"[AstroBud Nightly] LM Studio unreachable: {info.get('error')}. Aborting.")
        return
    print(f"[AstroBud Nightly] Loaded models: {info['models']}")
    if embedding_model not in info["models"]:
        print(f"[AstroBud Nightly] '{embedding_model}' not loaded. Skipping until it's active.")
        return

    print(f"[AstroBud Nightly] Vectorizing {len(daily)} interactions via '{embedding_model}'...")
    MEMORY_DIR.mkdir(exist_ok=True)
    chroma = PersistentClient(path=str(MEMORY_DIR))
    collection = chroma.get_or_create_collection(name=COLLECTION_NAME)

    success = 0
    failures = 0
    for idx, entry in enumerate(daily):
        combined = (
            f"At timestamp {entry.get('timestamp', 0)}, the User said: "
            f"'{entry.get('user_input', '')}'. "
            f"AstroBud observed the screen showing: '{entry.get('screen_context', '')}'. "
            f"AstroBud responded with: '{entry.get('bot_reply', '')}'."
        )
        try:
            vector = lms.embed(client, model=embedding_model, text=combined)
        except Exception as e:
            print(f"[AstroBud Nightly] Embedding failed for entry {idx}: {e}")
            failures += 1
            continue

        try:
            collection.add(
                ids=[f"mem_{int(entry.get('timestamp', time.time()))}_{idx}"],
                embeddings=[vector],
                documents=[combined],
                metadatas=[{
                    "timestamp": entry.get("timestamp", 0),
                    "type": "daily_history",
                }],
            )
            success += 1
        except Exception as e:
            print(f"[AstroBud Nightly] ChromaDB add failed for entry {idx}: {e}")
            failures += 1

    # Clear the daily log now that the vectors are stored
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

    print(f"[AstroBud Nightly] Done. Embedded {success} | failed {failures}. "
          f"Daily log cleared.")


if __name__ == "__main__":
    try:
        compile_memories()
    except Exception as e:
        print(f"[AstroBud Nightly] Fatal: {e}")
        sys.exit(1)
