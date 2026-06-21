"""ChromaDB-backed long-term memory for Aria.

Three collections:
  - aria_episodic:  each conversation turn or thought (with mood, source, timestamp)
  - aria_facts:     user preferences, project facts, stable info ("user prefers dark mode")
  - aria_thoughts:  reflections from the scheduler (what Aria was thinking about)

Default: HTTP client to PC 2 (`CHROMADB_URL`). Falls back to a local DuckDB+Parquet
persistent client on PC 1 if PC 2 is unreachable — so dev works even when the AI box
is off.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from aria_brain.config import CHROMADB_FALLBACK_DIR, CHROMADB_URL, LM_STUDIO_EMBED_MODEL

# Suppress chromadb/posthog telemetry noise (incompatible posthog API on Windows).
import os as _os
_os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

log = logging.getLogger("aria_brain.memory")

COLLECTION_EPISODIC = "aria_episodic"
COLLECTION_FACTS = "aria_facts"
COLLECTION_THOUGHTS = "aria_thoughts"


_client = None
_use_remote: Optional[bool] = None  # None = unknown, True = remote, False = fallback


def _get_client():
    """Lazy-init the ChromaDB client. Tries remote first, falls back to local."""
    global _client, _use_remote
    if _client is not None:
        return _client
    try:
        import chromadb
        # Try remote first (PC 2 server mode)
        client = chromadb.HttpClient(host=CHROMADB_URL.replace("http://", "").replace("https://", "").split(":")[0],
                                     port=int(CHROMADB_URL.rsplit(":", 1)[-1]),
                                     settings=chromadb.Settings(anonymized_telemetry=False))
        client.heartbeat()
        _client = client
        _use_remote = True
        log.info(f"chromadb: connected to remote at {CHROMADB_URL}")
        return _client
    except Exception as exc:
        log.warning(f"chromadb: remote unreachable ({type(exc).__name__}: {exc}); falling back to local DuckDB+Parquet")
        try:
            import chromadb
            from pathlib import Path
            Path(CHROMADB_FALLBACK_DIR).mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=CHROMADB_FALLBACK_DIR)
            _use_remote = False
            log.info(f"chromadb: using local fallback at {CHROMADB_FALLBACK_DIR}")
            return _client
        except Exception as exc2:
            log.error(f"chromadb: fallback also failed: {exc2}")
            raise


def _collection(name: str):
    client = _get_client()
    return client.get_or_create_collection(name=name, metadata={"created": datetime.utcnow().isoformat()})


def is_remote() -> bool:
    if _use_remote is None:
        _get_client()
    return bool(_use_remote)


def add_memory(text: str, kind: str = "episodic", metadata: Optional[dict] = None) -> str:
    """Store a memory. Returns the generated id."""
    if not text.strip():
        return ""
    coll_name = {
        "episodic": COLLECTION_EPISODIC,
        "fact": COLLECTION_FACTS,
        "thought": COLLECTION_THOUGHTS,
    }.get(kind, COLLECTION_EPISODIC)
    coll = _collection(coll_name)
    mem_id = f"{coll_name}-{int(time.time() * 1000)}"
    meta = {"ts": datetime.utcnow().isoformat() + "Z", "kind": kind}
    if metadata:
        meta.update(metadata)
    coll.add(documents=[text], ids=[mem_id], metadatas=[meta])
    return mem_id


def search(query: str, kind: str = "episodic", n: int = 5) -> list[dict]:
    """Semantic search. Returns [{id, text, metadata, distance}, ...]."""
    if not query.strip():
        return []
    coll_name = {
        "episodic": COLLECTION_EPISODIC,
        "fact": COLLECTION_FACTS,
        "thought": COLLECTION_THOUGHTS,
    }.get(kind, COLLECTION_EPISODIC)
    try:
        coll = _collection(coll_name)
        result = coll.query(query_texts=[query], n_results=n)
    except Exception as exc:
        log.warning(f"chromadb query failed: {exc}")
        return []
    out = []
    if not result or not result.get("documents"):
        return out
    for i, doc in enumerate(result["documents"][0]):
        out.append({
            "id": result["ids"][0][i],
            "text": doc,
            "metadata": result["metadatas"][0][i] if result.get("metadatas") else {},
            "distance": result["distances"][0][i] if result.get("distances") else None,
        })
    return out


def recent(kind: str = "episodic", n: int = 10) -> list[dict]:
    """Most recent memories (chronological, no semantic match)."""
    coll_name = {
        "episodic": COLLECTION_EPISODIC,
        "fact": COLLECTION_FACTS,
        "thought": COLLECTION_THOUGHTS,
    }.get(kind, COLLECTION_EPISODIC)
    try:
        coll = _collection(coll_name)
        result = coll.get(limit=n)
    except Exception as exc:
        log.warning(f"chromadb get failed: {exc}")
        return []
    out = []
    items = list(zip(result.get("ids", []), result.get("documents", []), result.get("metadatas", [])))
    items.sort(key=lambda x: x[2].get("ts", "") if x[2] else "", reverse=True)
    for id_, doc, meta in items[:n]:
        out.append({"id": id_, "text": doc, "metadata": meta or {}})
    return out


def count(kind: str = "episodic") -> int:
    coll_name = {
        "episodic": COLLECTION_EPISODIC,
        "fact": COLLECTION_FACTS,
        "thought": COLLECTION_THOUGHTS,
    }.get(kind, COLLECTION_EPISODIC)
    try:
        return _collection(coll_name).count()
    except Exception:
        return 0


def stats() -> dict:
    return {
        "backend": "remote" if is_remote() else "local",
        "episodic_count": count("episodic"),
        "facts_count": count("fact"),
        "thoughts_count": count("thought"),
    }


def warmup() -> None:
    """Pre-load the embedding model + create collections. Call from app startup."""
    log.info("chromadb warmup: initializing client + collections")
    for name in (COLLECTION_EPISODIC, COLLECTION_FACTS, COLLECTION_THOUGHTS):
        try:
            _collection(name)
            log.info(f"  collection ready: {name}")
        except Exception as exc:
            log.warning(f"  warmup failed for {name}: {exc}")


# Async wrappers — ChromaDB calls are sync and can block the event loop for
# seconds when the embedding model is loading. Wrap in to_thread for FastAPI.

async def aadd_memory(text: str, kind: str = "episodic", metadata: Optional[dict] = None) -> str:
    import asyncio
    return await asyncio.to_thread(add_memory, text, kind, metadata)


async def asearch(query: str, kind: str = "episodic", n: int = 5) -> list[dict]:
    import asyncio
    return await asyncio.to_thread(search, query, kind, n)


async def arecent(kind: str = "episodic", n: int = 10) -> list[dict]:
    import asyncio
    return await asyncio.to_thread(recent, kind, n)


async def astats() -> dict:
    import asyncio
    return await asyncio.to_thread(stats)