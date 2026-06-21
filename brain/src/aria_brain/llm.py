"""LM Studio client (PC 2). Uses OpenAI-compatible /v1/chat/completions."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from aria_brain.config import LM_STUDIO_API_KEY, LM_STUDIO_BASE_URL, LM_STUDIO_MODEL, LM_STUDIO_STRONG_MODEL

log = logging.getLogger("aria_brain.llm")


async def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.8,
    max_tokens: int = 200,
    timeout: float = 30.0,
) -> str:
    """Call LM Studio chat completion. Returns the assistant text."""
    url = f"{LM_STUDIO_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": model or LM_STUDIO_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {LM_STUDIO_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            log.warning(f"llm: status {r.status_code} body={r.text[:300]}")
            return ""
        data = r.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    except (httpx.HTTPError, OSError) as exc:
        log.warning(f"llm: {type(exc).__name__}: {exc}")
        return ""


async def embed(texts: list[str], model: Optional[str] = None, timeout: float = 30.0) -> list[list[float]]:
    """Call LM Studio embeddings endpoint. Returns a list of embedding vectors."""
    url = f"{LM_STUDIO_BASE_URL.rstrip('/')}/embeddings"
    payload = {
        "model": model or LM_STUDIO_MODEL,
        "input": texts if isinstance(texts, list) else [texts],
    }
    headers = {
        "Authorization": f"Bearer {LM_STUDIO_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            log.warning(f"embed: status {r.status_code} body={r.text[:300]}")
            return []
        data = r.json()
        return [item["embedding"] for item in data.get("data", [])]
    except (httpx.HTTPError, OSError) as exc:
        log.warning(f"embed: {type(exc).__name__}: {exc}")
        return []