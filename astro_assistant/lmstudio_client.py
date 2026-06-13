"""
LM Studio client wrapper for AstroBud.

Replaces the `ollama` Python SDK from the original spec. LM Studio exposes an
OpenAI-compatible API on localhost:1234 by default, so we just use the
official `openai` SDK pointed at that base URL.

Functions:
    get_client()              -> returns a shared openai.OpenAI client
    chat(client, **kwargs)    -> thin wrapper around client.chat.completions.create
    embed(client, **kwargs)   -> thin wrapper around client.embeddings.create
    list_loaded_models(client)-> returns list of model IDs currently loaded in LM Studio
    vision_message(prompt,    -> builds an OpenAI-format multimodal message
                 image_path)
    ensure_model_loaded(      -> uses `lms` CLI to load a model if not already active
        client, model_id)

The spec's ollama.embeddings() returns {"embedding": [...]} — the OpenAI
embeddings endpoint returns {"data": [{"embedding": [...]}]}. We normalize
that here so the rest of the codebase doesn't care which backend.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI, OpenAIError


DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_API_KEY = "lm-studio"  # LM Studio doesn't enforce; any string works


def get_client(
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = 120.0,
) -> OpenAI:
    """Return a configured OpenAI client pointed at LM Studio."""
    return OpenAI(
        base_url=base_url or os.environ.get("LMSTUDIO_BASE_URL", DEFAULT_BASE_URL),
        api_key=api_key or os.environ.get("LMSTUDIO_API_KEY", DEFAULT_API_KEY),
        timeout=timeout,
    )


def chat(client: OpenAI, **kwargs: Any) -> Any:
    """Thin pass-through to client.chat.completions.create with friendlier errors."""
    try:
        return client.chat.completions.create(**kwargs)
    except OpenAIError as e:
        # Common case: LM Studio server isn't running or the model isn't loaded
        raise RuntimeError(
            f"LM Studio chat call failed: {e}\n"
            "Check that:\n"
            "  1. LM Studio is running\n"
            "  2. The local server is started (Developer tab -> Start Server)\n"
            "  3. The requested model is loaded (it must be the active model)"
        ) from e


def embed(client: OpenAI, model: str, text: str) -> list[float]:
    """Return a single embedding vector for `text`. Normalizes the OpenAI response shape."""
    try:
        resp = client.embeddings.create(model=model, input=text)
    except OpenAIError as e:
        raise RuntimeError(
            f"LM Studio embeddings call failed: {e}\n"
            "Check that the embedding model is loaded in LM Studio."
        ) from e
    return resp.data[0].embedding


def list_loaded_models(client: OpenAI) -> list[str]:
    """Return the IDs of models currently loaded in LM Studio's local server."""
    try:
        models = client.models.list()
        return [m.id for m in models.data]
    except OpenAIError:
        return []


def vision_message(prompt: str, image_path: str | Path) -> dict[str, Any]:
    """
    Build an OpenAI-format multimodal user message containing `prompt` and a
    base64-encoded `image_path`. Use as the `messages` payload for vision
    models that accept images (LLaVA, Nous-Hermes-2-Vision, Qwen3-VL, etc.).
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Vision image not found: {image_path}")
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    suffix = image_path.suffix.lower().lstrip(".") or "png"
    mime = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{data}"},
            },
        ],
    }


def text_message(role: str, content: str) -> dict[str, Any]:
    """Build a simple text message (role: system|user|assistant|tool)."""
    return {"role": role, "content": content}


def tool_result_message(tool_call_id: str, content: str) -> dict[str, Any]:
    """Build a tool result message to feed back into a tool-calling conversation."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }


def is_lms_cli_available() -> bool:
    """True if the `lms` CLI is on PATH (shipped with LM Studio 0.3+)."""
    return shutil.which("lms") is not None


def ensure_model_loaded(
    model_id: str,
    loaded_ids: list[str] | None = None,
    auto_load: bool = True,
) -> tuple[bool, str]:
    """
    Best-effort: if `model_id` isn't in `loaded_ids`, try to load it via `lms`.

    Returns (success, message). If `auto_load=False` or `lms` is not on PATH,
    we just return a clear message asking the user to load manually.
    """
    if loaded_ids is None:
        # Caller didn't pre-fetch; skip the check
        return True, f"Assuming {model_id} is available (no pre-fetch)."

    if model_id in loaded_ids:
        return True, f"{model_id} is already loaded."

    if not auto_load or not is_lms_cli_available():
        return (
            False,
            f"Model '{model_id}' is not loaded. "
            f"Open LM Studio, load it, and try again. Currently loaded: {loaded_ids}",
        )

    try:
        result = subprocess.run(
            ["lms", "load", model_id],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return True, f"Loaded {model_id} via lms CLI."
        return False, f"`lms load {model_id}` failed: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, f"`lms load {model_id}` timed out."
    except Exception as e:
        return False, f"lms load error: {e}"


def smoke_test(client: OpenAI) -> dict[str, Any]:
    """Quick connectivity check — used by the dashboard's status panel."""
    info: dict[str, Any] = {"server_reachable": False, "models": [], "error": None}
    try:
        info["models"] = list_loaded_models(client)
        info["server_reachable"] = True
    except Exception as e:
        info["error"] = str(e)
    return info


if __name__ == "__main__":
    # Quick CLI sanity check: `python lmstudio_client.py`
    c = get_client()
    info = smoke_test(c)
    print(json.dumps(info, indent=2))
    sys.exit(0 if info["server_reachable"] else 1)
