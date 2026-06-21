"""motion_library.py — Read-only helpers for motion_library.json.

This is the runtime-facing module the motion server imports to load the
motion library into its diffusion context. The ingest CLI
(``ingest_motion_library.py``) writes the JSON; this module reads it.

Two public helpers:
    - ``load_library(path)`` — return the parsed dict.
    - ``hash_library(path)`` — return a stable SHA-256 hex digest of the file.

The hash is useful for embedding the library version into the diffusion
server's request context (so the model knows when the library changed).

A small ``build_context_snippet(library)`` helper is also provided; it
formats the library into a compact text block suitable for stuffing into
the FloodDiffusion prompt's "context" field.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


# Default path next to this module.
DEFAULT_PATH = Path(__file__).resolve().parent / 'motion_library.json'


def load_library(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load motion_library.json. Returns the parsed dict.

    On any error (missing file, bad JSON), returns a minimal stub so the
    caller can degrade gracefully (e.g. empty animation list).
    """
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        return {'schemaVersion': 0, 'animations': []}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {'schemaVersion': 0, 'animations': []}


def hash_library(path: Optional[Path] = None) -> str:
    """Return SHA-256 hex digest of motion_library.json.

    The hash is over the file bytes, so any re-ingest (even with the same
    logical content but a different ``generatedAt``) will produce a new
    hash. For a content-only hash, use ``hash_library_dict(load_library(p))``.
    """
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        return ''
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def hash_library_dict(library: Dict[str, Any]) -> str:
    """SHA-256 of a dict representation (deterministic; ignores ``generatedAt``)."""
    # Copy and drop the timestamp for stable hashing
    payload = {k: v for k, v in library.items() if k != 'generatedAt'}
    s = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def find_animation(library: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """Look up an animation by name. Returns the entry dict or None."""
    for a in library.get('animations', []):
        if a.get('name') == name:
            return a
    return None


def animations_by_bone_set(library: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Group animations by their detected boneSet (mixamo / vroid / unknown)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for a in library.get('animations', []):
        bs = a.get('boneSet', 'unknown')
        out.setdefault(bs, []).append(a)
    return out


def needs_retarget(library: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the subset of animations marked as needing retargeting."""
    return [a for a in library.get('animations', []) if a.get('needsRetarget')]


def build_context_snippet(library: Dict[str, Any], max_chars: int = 4000) -> str:
    """Format the library as a compact text block for the diffusion prompt.

    The FloodDiffusion server embeds this into its request context so the
    model knows what animations are available and their metadata. We cap the
    output at ``max_chars`` to avoid bloating the prompt.
    """
    lines: List[str] = []
    schema = library.get('schemaVersion', '?')
    n = library.get('animations', [])
    model = library.get('modelPath', '?')
    lines.append(f'[motion_library v{schema}] {len(n)} animations (model={model})')
    # Group summary by boneSet
    by_set = animations_by_bone_set(library)
    for bs, items in sorted(by_set.items()):
        lines.append(f'  {bs}: {len(items)}')
    # Per-animation one-liners
    for a in n:
        dur = a.get('durationSec', 0.0)
        ip = 'in-place' if a.get('isInPlace') else 'moving'
        rm = a.get('rootMotion', {})
        rm_total = rm.get('total', 0.0)
        rm_str = f'root={rm_total:.2f}' if rm_total > 0.01 else 'root=0'
        contacts = len(a.get('contactFrames', []))
        lines.append(
            f"  - {a.get('name', '?'):28s} dur={dur:6.2f}s {ip:9s} {rm_str:14s} "
            f"contacts={contacts:2d} fps={a.get('fps', 30)}"
        )
    out = '\n'.join(lines)
    if len(out) > max_chars:
        out = out[: max_chars - 3] + '...'
    return out


# ── CLI smoke-test ─────────────────────────────────────────────────────
if __name__ == '__main__':
    lib = load_library()
    print(f'Loaded {len(lib.get("animations", []))} animations')
    print(f'Library hash: {hash_library()}')
    print(f'Content hash (excl generatedAt): {hash_library_dict(lib)}')
    print()
    print('Context snippet (first 1500 chars):')
    print(build_context_snippet(lib)[:1500])
