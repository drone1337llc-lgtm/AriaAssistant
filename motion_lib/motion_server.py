#!/usr/bin/env python3
"""
FloodDiffusion motion-generation server for Aria.

Single-job queue: FloodDiffusion holds a CUDA context and concurrent inference
is OOM-prone, so we run ONE generation at a time and queue the rest (FIFO).
The queue is capped at 100 items — anything beyond returns HTTP 429.

Wire protocol (HTTP, JSON):

  POST /motion
    Body: {"prompt": str, "frames": int=60, "suggested_name": str=""}
    Returns 200: {"id": str, "position": int, "queue_depth": int}
    Returns 429: {"error": "queue full", "queue_depth": int, "capacity": int}
    Returns 400: {"error": str}            (bad input)

  POST /motion/status
    Body: {"ids": [str, ...]}
    Returns 200: {"results": [
        {"id": str, "status": "pending"|"running"|"done"|"failed",
         "animation_name"?: str, "animation_url"?: str, "error"?: str}
    ]}

  GET /motion/get?id=<id>
    Returns 200: application/json
      {"id": str, "name": str, "frames": int, "fps": int,
       "bones": [{"name": str, "rotations": [[w,x,y,z], ...]}, ...]}
    Each bone has a per-frame quaternion (w,x,y,z) relative to its rest pose.
    Aria's Godot client maps these to Skeleton3D.SetBonePoseRotation.

  GET /motion/cap
    Returns 200: {"capacity": int, "depth": int, "running": str|null,
                  "next_id": str|null}

This server is run on the AI PC. Start it once; it auto-loads the model on
first request (or via --preload). The Godot client on the user's desktop
talks to it over LAN.

Usage:
  python motion_server.py --port 8765 --capacity 100
  python motion_server.py --port 8765 --capacity 100 --preload
  python motion_server.py --port 8765 --model ShandaAI/FloodDiffusionTiny

Default model is the standard FloodDiffusion (needs ~16GB VRAM); Tiny
fits in 8GB and runs faster — good for an RTX 3090. The user can override
with --model.

Author: Mavis (Mavis-runtime agent), 2026-06-14
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import random
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    from motion_library import DEFAULT_PATH as LIBRARY_DEFAULT_PATH, load_library
except Exception:  # pragma: no cover — keep server importable even if helper breaks
    LIBRARY_DEFAULT_PATH = None
    load_library = None  # type: ignore[assignment]

log = logging.getLogger("motion_server")

try:
    # The auto-curator (handles /curator HTTP). Soft import: if curator.py is
    # missing or breaks on import, the motion server still boots - /curator
    # just 503s with an "unavailable" error. (log must be defined first, or a
    # missing curator crashes startup with a NameError.)
    from curator import handle_curator_request, format_curator_prompt_for_llm
except Exception as _curator_err:  # pragma: no cover
    log.warning("curator module not available: %s", _curator_err)
    handle_curator_request = None  # type: ignore[assignment]
    format_curator_prompt_for_llm = None  # type: ignore[assignment]

# ── Config ──────────────────────────────────────────────────────────────
DEFAULT_MODEL = "ShandaAI/FloodDiffusion"      # full size, ~16GB VRAM
TINY_MODEL = "ShandaAI/FloodDiffusionTiny"     # ~8GB VRAM
DEFAULT_PORT = 8765
DEFAULT_CAPACITY = 100
DEFAULT_FPS = 30                                # output frame rate

# SMPL 22-joint → Aria's Mixamo bone names. Standard published correspondence.
# (We only need joint NAME translation; the joint POSITIONS in SMPL output can
#  be re-targeted to a 52-bone Mixamo rig via an Inverse-Kinematics step in
#  the client. This dictionary maps joint indices → bone names so the client
#  knows which Mixamo bone each retargeted joint corresponds to.)
SMPL_TO_MIXAMO = {
    0:  "J_Bip_C_Hips",        # pelvis
    1:  "J_Bip_L_UpperLeg",    # left hip → upper leg
    2:  "J_Bip_R_UpperLeg",    # right hip → upper leg
    3:  "J_Bip_C_Spine",        # spine1
    4:  "J_Bip_L_LowerLeg",    # left knee
    5:  "J_Bip_R_LowerLeg",    # right knee
    6:  "J_Bip_C_Chest",        # spine2
    7:  "J_Bip_L_Foot",         # left ankle
    8:  "J_Bip_R_Foot",         # right ankle
    9:  "J_Bip_C_UpperChest",   # spine3
    10: "J_Bip_L_ToeBase",      # left foot tip
    11: "J_Bip_R_ToeBase",      # right foot tip
    12: "J_Bip_C_Neck",         # neck
    13: "J_Bip_L_Shoulder",     # left collar
    14: "J_Bip_R_Shoulder",     # right collar
    15: "J_Bip_C_Head",         # head
    16: "J_Bip_L_UpperArm",     # left shoulder
    17: "J_Bip_R_UpperArm",     # right shoulder
    18: "J_Bip_L_LowerArm",     # left elbow
    19: "J_Bip_R_LowerArm",     # right elbow
    20: "J_Bip_L_Hand",         # left wrist
    21: "J_Bip_R_Hand",         # right wrist
}


@dataclass
class MotionRequest:
    request_id: str
    prompt: str
    frames: int
    suggested_name: str
    enqueued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    status: str = "pending"             # pending | running | done | failed
    error: Optional[str] = None
    animation: Optional[dict] = None    # populated when status == "done"
    system_prompt: Optional[str] = None  # diffusion context (library snippet + prompt)

    def elapsed(self) -> float:
        if self.started_at is None:
            return time.time() - self.enqueued_at
        if self.finished_at is None:
            return time.time() - self.started_at
        return self.finished_at - self.started_at


# ── Library state (watched file → diffusion context) ────────────────────
class LibraryState:
    """In-memory cache of motion_library.json with a mtime watchdog.

    The motion server reads this on every /motion POST to build the diffusion
    system prompt. The watchdog re-reads the file every ``poll_sec`` seconds;
    if the mtime changes, the in-memory dict is swapped out atomically under
    a lock. The /library route returns the latest parsed dict (or None if
    the file is missing).
    """

    # Keyword aliases for the simple matcher. Keep small and obvious — the goal
    # is "wave" surfaces greeting/wave/hello entries, not perfect retrieval.
    KEYWORD_ALIASES = {
        "wave": ["wave", "greeting", "hello", "hi", "bye", "goodbye"],
        "greet": ["greeting", "hello", "hi", "wave", "thankful", "standing_greeting"],
        "hello": ["greeting", "hello", "wave", "standing_greeting"],
        "walk": ["walk", "walking", "stroll", "step", "female_start_walking"],
        "run": ["run", "running", "sprint", "jog"],
        "jump": ["jump", "jump_down", "leap", "hop"],
        "sit": ["sit", "sitting", "sitting_clap"],
        "climb": ["climb", "climbing", "climbing_down", "climbing_down_wall", "sprint_to_wall_climb"],
        "fall": ["fall", "falling_idle", "freehang_drop", "drop_to_freehang"],
        "swim": ["swim", "swimming", "swimming_to_edge", "treading_water"],
        "turn": ["turn", "left_turn", "right_turn", "turn_to_running", "change_direction"],
        "idle": ["idle", "idle_1", "standing_greeting", "look_around", "yawn", "bashful", "happy", "thankful"],
        "happy": ["happy", "thankful", "sitting_clap", "wave_hip_hop_dance"],
        "sad": ["bashful", "thankful"],
        "dance": ["wave_hip_hop_dance", "happy", "showoff_walking", "standing_greeting"],
        "look": ["look_around", "yawn", "bashful"],
        "freehang": ["freehang_drop", "drop_to_freehang", "stand_to_freehang"],
        "strafe": ["left_strafe", "right_strafe", "left_strafe_walk", "right_strafe_walk"],
        "showoff": ["showoff_walking", "idle_to_start_showoff_walking", "wave_hip_hop_dance"],
    }

    def __init__(self, path, poll_sec: float = 60.0):
        self.path = path
        self.poll_sec = float(poll_sec)
        self._lock = threading.Lock()
        self._mtime: Optional[float] = None
        self._lib: Optional[dict] = None
        self._watchdog: Optional[threading.Thread] = None
        self._stop = threading.Event()
        # Initial load (synchronous; safe at startup)
        self._read_locked(force=True)

    # ── public API ──────────────────────────────────────────────────
    def start(self):
        if self._watchdog is not None:
            return
        self._stop.clear()
        self._watchdog = threading.Thread(target=self._watchdog_loop, name="library-watchdog", daemon=True)
        self._watchdog.start()

    def stop(self):
        self._stop.set()

    def get(self) -> Optional[dict]:
        with self._lock:
            return self._lib

    def count(self) -> int:
        with self._lock:
            if not self._lib:
                return 0
            return len(self._lib.get("animations") or [])

    def mtime(self) -> Optional[float]:
        with self._lock:
            return self._mtime

    def path_str(self) -> str:
        return str(self.path) if self.path else "<none>"

    # ── internal ────────────────────────────────────────────────────
    def _watchdog_loop(self):
        while not self._stop.is_set():
            # Sleep in 1-second slices so stop() is responsive
            for _ in range(int(self.poll_sec)):
                if self._stop.is_set():
                    return
                time.sleep(1.0)
            try:
                self._read_locked(force=False)
            except Exception as e:  # never let the watchdog die
                log.warning("library watchdog reload error: %s", e)

    def _read_locked(self, force: bool):
        """Re-read the file if the mtime changed (or ``force``). Caller must
        hold ``self._lock`` if non-force and concurrent-safe semantics matter;
        we acquire it ourselves in the public entry path."""
        new_lib: Optional[dict] = None
        new_mtime: Optional[float] = None
        if self.path and self.path.exists():
            new_mtime = self.path.stat().st_mtime
            if force or new_mtime != self._mtime:
                try:
                    if load_library is not None:
                        new_lib = load_library(self.path)
                    else:
                        new_lib = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception as e:
                    log.warning("library reload failed (%s); keeping previous version", e)
                    new_lib = None
                    new_mtime = None  # don't update mtime on failure

        if new_lib is not None and (force or self._lib is None or new_mtime != self._mtime):
            with self._lock:
                old_count = len((self._lib or {}).get("animations") or [])
                new_count = len(new_lib.get("animations") or [])
                self._lib = new_lib
                self._mtime = new_mtime
                if old_count != new_count or force:
                    log.info(
                        "library reloaded: %d animations (was %d) — %s",
                        new_count, old_count, self.path_str(),
                    )
        elif new_mtime is None and not self.path:
            # Caller wired a None path; leave state as-is (still "missing").
            with self._lock:
                self._lib = None
                self._mtime = None


# ── Curator state (auto-fetch missing reference material) ──────────────
@dataclass
class CuratorJob:
    """One auto-curator run. Lifecycle: pending → running → done|failed."""
    job_id: str
    request: dict
    enqueued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    status: str = "pending"          # pending | running | done | failed
    result: Optional[dict] = None    # populated when status == "done"
    error: Optional[str] = None      # populated when status == "failed"


class CuratorState:
    """In-memory tracker for /curator background jobs.

    The motion server's HTTP handler enqueues jobs here and returns
    202 Accepted with the job id; a daemon thread picks them up and
    runs ``handle_curator_request`` (which may take 30-60 s for the
    web search + download + re-ingest). The Godot client polls
    ``GET /curator/status?id=<job_id>`` until status ∈ {done, failed}.
    """

    def __init__(self):
        self._jobs: dict[str, CuratorJob] = {}
        self._lock = threading.Lock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        if self._worker is not None:
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._worker_loop, name="curator-worker", daemon=True)
        self._worker.start()
        log.info("curator worker started")

    def stop(self):
        self._stop.set()

    def enqueue(self, request: dict) -> CuratorJob:
        # Use a defensive max length on the action so a runaway LLM
        # can't trigger 10-MB web searches.
        action = (request.get("action") or "").strip()[: 64]
        req = {
            "action": action,
            "reason": (request.get("reason") or "")[: 500],
            "urgency": (request.get("urgency") or "normal").strip().lower(),
            "max_results": max(1, min(int(request.get("max_results") or 1), 5)),
        }
        job = CuratorJob(
            job_id=uuid.uuid4().hex[:12],
            request=req,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        self._queue.put(job.job_id)
        log.info("curator: enqueued job=%s action=%r", job.job_id, req["action"])
        return job

    def get(self, job_id: str) -> Optional[CuratorJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def _worker_loop(self):
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            with self._lock:
                job = self._jobs.get(job_id)
            if job is None:
                self._queue.task_done()
                continue
            job.started_at = time.time()
            job.status = "running"
            log.info("curator: [%s] START action=%r", job.job_id, job.request.get("action"))
            try:
                if handle_curator_request is None:
                    raise RuntimeError("curator module not loaded")
                # The actual web search + download + ingest may take 30-60 s.
                # The HTTP handler has already returned 202; we run synchronously
                # in this thread and update the job state in-place.
                job.result = handle_curator_request(job.request)
                job.status = "done"
                added = len((job.result or {}).get("added") or [])
                log.info("curator: [%s] DONE in %.1fs (added=%d)",
                         job.job_id, time.time() - job.started_at, added)
            except Exception as e:
                log.exception("curator: [%s] FAILED: %s", job.job_id, e)
                job.status = "failed"
                job.error = str(e)
            finally:
                job.finished_at = time.time()
                self._queue.task_done()


# ── Context assembly (library → diffusion system prompt) ────────────────
# Rough heuristic: 1 token ≈ 4 characters of English text. 2000 tokens ≈ 8000 chars.
CHARS_PER_TOKEN = 4
DEFAULT_MAX_TOKENS = 2000
KEYWORD_MATCH_LIMIT = 30
KEYWORD_RANDOM_PADDING = 10


def _format_animation_line(anim: dict) -> str:
    """One-line per-anim spec for the diffusion system prompt."""
    name = anim.get("name", "?")
    dur = float(anim.get("durationSec") or 0.0)
    in_place = bool(anim.get("isInPlace"))
    rm = anim.get("rootMotion") or {}
    if isinstance(rm, dict):
        total = float(rm.get("total") or 0.0)
    else:
        total = 0.0
    contact_frames = anim.get("contactFrames") or []
    contacts_rounded = [round(float(c), 2) for c in contact_frames]
    bone_set = anim.get("boneSet") or "unknown"
    return (
        f"  - {name}: durationSec={dur:.2f}, isInPlace={in_place}, "
        f"travelSpeed={total:.2f}, contactFrames={contacts_rounded}, boneSet={bone_set}"
    )


def _animation_keyword_score(anim: dict, prompt: str) -> int:
    """Return a simple match score (higher = more relevant)."""
    name = (anim.get("name") or "").lower()
    file_ = (anim.get("file") or "").lower()
    blob = f"{name} {file_}"
    score = 0
    for token in re.findall(r"[a-z_]+", prompt.lower()):
        if not token or len(token) < 2:
            continue
        if token in blob:
            score += 2
        # Alias map
        for alias_target, alias_terms in LibraryState.KEYWORD_ALIASES.items():
            if token == alias_target or token in alias_terms:
                if any(t in blob for t in alias_terms):
                    score += 1
                    break
    return score


def build_diffusion_context(
    library: Optional[dict],
    prompt: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    rng: Optional[random.Random] = None,
) -> str:
    """Build a diffusion system prompt from the motion library.

    Layout:
        <one-line summary>
        <per-anim spec lines, capped at ~max_tokens chars>

    If the full per-anim list is larger than the cap, we keep the
    KEYWORD_MATCH_LIMIT most relevant entries (by simple keyword match against
    the user prompt) and pad with KEYWORD_RANDOM_PADDING random entries from
    the rest, so the model still gets exposure to non-relevant actions.
    """
    rng = rng or random.Random()
    curator_suffix = (
        format_curator_prompt_for_llm()
        if format_curator_prompt_for_llm is not None
        else ""
    )
    if not library:
        return (
            "Available animations: 0. The motion library is unavailable; "
            "use your best judgment for the requested action."
        ) + curator_suffix

    animations = list(library.get("animations") or [])
    total = len(animations)
    if total == 0:
        return "Available animations: 0. Use these names when you want a specific action." + curator_suffix

    summary = (
        f"Available animations: {total}. "
        f"Use these names when you want a specific action."
    )
    char_cap = max_tokens * CHARS_PER_TOKEN

    # Build per-line blocks
    blocks = [_format_animation_line(a) for a in animations]
    total_chars = sum(len(b) for b in blocks) + len(animations)  # newlines

    if total_chars <= char_cap:
        body = "\n".join(blocks)
        return f"{summary}\n{body}" + curator_suffix

    # Over budget — rank by keyword, keep top-N, then random-pad
    scored = sorted(
        enumerate(animations),
        key=lambda kv: (_animation_keyword_score(kv[1], prompt), -kv[0]),
        reverse=True,
    )
    keep_idx: list[int] = []
    for idx, anim in scored:
        if len(keep_idx) >= KEYWORD_MATCH_LIMIT:
            break
        keep_idx.append(idx)
    keep_set = set(keep_idx)

    remaining = [i for i in range(total) if i not in keep_set]
    pad_count = min(KEYWORD_RANDOM_PADDING, len(remaining))
    if pad_count > 0:
        pad_idx = rng.sample(remaining, pad_count)
    else:
        pad_idx = []
    final_idx = sorted(set(keep_idx) | set(pad_idx))

    blocks = [_format_animation_line(animations[i]) for i in final_idx]
    body = "\n".join(blocks)
    if len(body) > char_cap:
        body = body[: max(0, char_cap - 3)] + "..."
    return f"{summary}\n{body}" + curator_suffix


class MotionServer:
    """Owns the queue, the worker thread, and the loaded model."""

    def __init__(self, model_id: str, capacity: int, fps: int, preload: bool, mock: bool = False,
                 library_path=None, library_poll_sec: float = 60.0):
        self.model_id = model_id
        self.capacity = capacity
        self.fps = fps
        self.mock = mock
        self._queue: "queue.Queue[MotionRequest]" = queue.Queue(maxsize=capacity)
        self._all: dict[str, MotionRequest] = {}
        self._all_lock = threading.Lock()
        self._running_id: Optional[str] = None
        self._model = None
        self._preload = preload
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        # Library state — wired even if the file is missing; we just degrade to
        # "0 animations" context (logged once at startup).
        self.library = LibraryState(library_path, poll_sec=library_poll_sec)
        # Curator state — accepts POST /curator and runs the auto-fetch in a
        # background thread. Returns 202 Accepted with a job id.
        self.curator = CuratorState()

    # ── Queue API (called by HTTP handler) ──────────────────────────
    def enqueue(self, prompt: str, frames: int, suggested_name: str = "") -> MotionRequest:
        req = MotionRequest(
            request_id=uuid.uuid4().hex[:12],
            prompt=prompt,
            frames=max(8, min(frames, 480)),     # hard limits: 0.13s..16s @ 30fps
            suggested_name=(suggested_name or "").strip(),
        )
        # Build the diffusion system prompt from the current library state.
        # This runs at enqueue (not inside the worker) so the HTTP handler can
        # surface the snippet back in /motion/status if we ever want to.
        req.system_prompt = build_diffusion_context(
            self.library.get(), prompt=prompt,
        )
        with self._all_lock:
            self._all[req.request_id] = req
            position = sum(1 for r in self._all.values() if r.status in ("pending", "running"))
        self._queue.put(req)
        return req

    def get(self, request_id: str) -> Optional[MotionRequest]:
        with self._all_lock:
            return self._all.get(request_id)

    def status(self, ids: list[str]) -> list[MotionRequest]:
        with self._all_lock:
            return [self._all[i] for i in ids if i in self._all]

    def depth(self) -> int:
        with self._all_lock:
            return sum(1 for r in self._all.values() if r.status in ("pending", "running"))

    def snapshot(self) -> dict:
        with self._all_lock:
            depth = sum(1 for r in self._all.values() if r.status in ("pending", "running"))
            return {
                "capacity": self.capacity,
                "depth": depth,
                "running": self._running_id,
                "next_id": (self._queue.queue[0].request_id if not self._queue.empty() else None),
            }

    # ── Worker ──────────────────────────────────────────────────────
    def start(self):
        if self._worker is not None: return
        self._stop.clear()
        self._worker = threading.Thread(target=self._worker_loop, name="motion-worker", daemon=True)
        self._worker.start()
        log.info("worker started (capacity=%d, model=%s, fps=%d)", self.capacity, self.model_id, self.fps)
        if self._preload:
            threading.Thread(target=self._ensure_model, name="model-preload", daemon=True).start()
        # Watchdog is harmless if the library file is missing; it just logs
        # "0 animations" on the first check and then idles.
        self.library.start()
        # Curator background worker — picks up /curator POSTs and runs the
        # web search + download + re-ingest asynchronously.
        self.curator.start()

    def stop(self):
        self._stop.set()
        self.library.stop()
        self.curator.stop()

    def _ensure_model(self):
        if self._model is not None: return
        if self.mock:
            # In mock mode, "load" a tiny dummy model in 0.5s — used by
            # motion_stress_test.py to verify queue/cap semantics without
            # needing the real FloodDiffusion weights.
            time.sleep(0.5)
            self._model = object()   # truthy, satisfies "is not None" checks
            log.info("[mock] model loaded (synthetic)")
            return
        try:
            log.info("loading model %s …", self.model_id)
            # Use our local loader instead of AutoModel.from_pretrained.
            # The upstream LDFModel has a broken trust_remote_code check
            # and a hard dependency on flash_attn (no official Windows
            # wheel). See _flood_loader.py for the gory details. The
            # loader is a no-op on Linux with flash_attn installed; on
            # Windows it forces the SDPA fallback. Imported by direct
            # path so it works whether motion_server.py is run as a
            # script (cd astro_assistant && python motion_server.py) or
            # as `python -m astro_assistant.motion_server`.
            try:
                from astro_assistant._flood_loader import load_FloodDiffusion
            except ImportError:
                from _flood_loader import load_FloodDiffusion
            self._model = load_FloodDiffusion(self.model_id)
            # Move to GPU if available
            try:
                import torch
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                    log.info("model on GPU")
                else:
                    log.info("model on CPU (no CUDA — inference will be slow)")
            except Exception as e:
                log.warning("could not move model to GPU: %s", e)
            log.info("model loaded")
        except Exception as e:
            log.exception("model load failed: %s", e)
            self._model = None

    def _worker_loop(self):
        while not self._stop.is_set():
            try:
                req = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            self._running_id = req.request_id
            req.status = "running"
            req.started_at = time.time()
            n_lib = self.library.count()
            log.info(
                "[%s] START prompt=%r frames=%d (queue waited %.1fs) — library context: %d animations",
                req.request_id, req.prompt, req.frames, req.started_at - req.enqueued_at, n_lib,
            )
            try:
                self._ensure_model()
                if self._model is None:
                    raise RuntimeError("model not loaded — install with `pip install -r requirements.txt` and ensure the FloodDiffusion deps are present")
                req.animation = self._generate(req)
                req.status = "done"
                req.finished_at = time.time()
                log.info("[%s] DONE in %.1fs (animation name=%s, bones=%d)",
                         req.request_id, req.elapsed(), req.animation.get("name"), len(req.animation.get("bones", [])))
            except Exception as e:
                log.exception("[%s] FAILED: %s", req.request_id, e)
                req.status = "failed"
                req.error = str(e)
                req.finished_at = time.time()
            finally:
                self._running_id = None
                self._queue.task_done()

    def _generate(self, req: MotionRequest) -> dict:
        """Run FloodDiffusion on the request. Returns a dict the Godot client
        can install directly into a Godot.Animation."""
        if self.mock:
            # Mock generation: 0.2s + a fake joint timeline. Used by
            # motion_stress_test.py. Won't look like a real motion, but
            # the wire protocol + retargeter are still exercised end-to-end.
            time.sleep(0.2)
            T = max(8, min(req.frames, 30))
            joints = np.random.RandomState(hash(req.prompt) & 0xFFFF).randn(T, 22, 3).astype(np.float32) * 0.3
            joints[:, 0, :] = 0  # root at origin
            centred = joints - joints[:, 0:1, :]
            bones = self._retarget_to_mixamo_quaternions(centred)
            if req.suggested_name:
                name = req.suggested_name
            else:
                slug = "".join(c if c.isalnum() else "_" for c in req.prompt[:32]).strip("_")
                name = f"gen_{slug}_{req.request_id[:6]}"
            return {
                "name": name, "frames": T, "fps": self.fps,
                "format": "joints+rotations",
                "joints": centred.tolist(), "bones": bones,
            }

        # Output joint positions (22, 3) at req.fps. We pad/trim to req.frames
        # by linear resampling — FloodDiffusion always emits at its own frame
        # rate; the user requested req.frames at req.fps fps.
        #
        # If we have an assembled system prompt from the motion library, pass it
        # along as `context` so the model can pick named animations when the
        # prompt is short or library-friendly. The model API accepts context as
        # a kwarg; if this particular backend doesn't support it, the caller
        # can ignore it.
        model_kwargs: dict = {"length": req.frames, "output_joints": True}
        if req.system_prompt:
            model_kwargs["context"] = req.system_prompt
        try:
            out_joints = self._model(req.prompt, **model_kwargs)
        except TypeError:
            # Backend doesn't accept the context kwarg — fall back to plain call.
            log.debug("model backend rejected `context` kwarg; calling without it")
            out_joints = self._model(req.prompt, length=req.frames, output_joints=True)
        # `out_joints` shape: (T, 22, 3) — T may not equal req.frames
        joints = np.asarray(out_joints)   # (T, 22, 3)
        if joints.ndim != 3 or joints.shape[1] != 22 or joints.shape[2] != 3:
            raise RuntimeError(f"unexpected output shape: {joints.shape}")

        # Resample to exactly req.frames if needed
        T = joints.shape[0]
        if T != req.frames:
            xp = np.linspace(0, 1, T)
            xq = np.linspace(0, 1, req.frames)
            joints = np.stack(
                [np.interp(xq, xp, joints[:, j, a]) for j in range(22) for a in range(3)],
                axis=-1,
            ).reshape(req.frames, 22, 3)

        # Convert the SMPL joints to "world" coords for the Godot client.
        # FloodDiffusion's joint positions are ROOT-LOCAL. For the Godot IK
        # retargeter we want ABSOLUTE positions in Aria's world space. The
        # client (AriaMotionClient.InstallAnimation) handles the actual
        # chain-by-chain IK on the Mixamo rig; we just ship the joints.
        # Re-centre so the hips are at origin (the client will offset
        # against Aria's current world position when installing).
        centred = joints - joints[:, 0:1, :]   # root = hips at (0, 0, 0)

        # We also still send the rotation-based fallback ("bones" field) so
        # the client has SOMETHING installable even if the IK retarget fails
        # (e.g. chain not in the catalogue). The client prefers joints over
        # bones; the bones array is the legacy path.
        bones = self._retarget_to_mixamo_quaternions(centred)

        # Stable animation name (prefer suggested; else prompt-slugified)
        if req.suggested_name:
            name = req.suggested_name
        else:
            slug = "".join(c if c.isalnum() else "_" for c in req.prompt[:32]).strip("_")
            name = f"gen_{slug}_{req.request_id[:6]}"

        return {
            "name": name,
            "frames": req.frames,
            "fps": self.fps,
            "format": "joints+rotations",   # client picks the better path
            "joints": centred.tolist(),      # (T, 22, 3) list-of-lists, root-relative
            "bones": bones,                  # legacy per-bone rotation path
        }

    def _retarget_to_mixamo_quaternions(self, smpl_joints: np.ndarray) -> list[dict]:
        """LEGACY FALLBACK: convert (T, 22, 3) SMPL joint positions to per-bone
        rotation timelines for the Mixamo rig. The C# client now prefers the
        `joints` field (raw SMPL positions) and runs FABRIK itself, but we
        keep this path as a no-IK fallback for safety.
        """
        rest = self._smpl_rest_pose()
        T = smpl_joints.shape[0]
        result = []
        for smpl_idx, mixamo_name in SMPL_TO_MIXAMO.items():
            parent_idx = self._smpl_parent(smpl_idx)
            if parent_idx is None:
                continue
            rest_dir = rest[smpl_idx] - rest[parent_idx]
            rest_len = np.linalg.norm(rest_dir)
            if rest_len < 1e-6:
                continue
            rest_dir = rest_dir / rest_len

            rotations = []
            for t in range(T):
                cur_dir = smpl_joints[t, smpl_idx] - smpl_joints[t, parent_idx]
                cur_len = np.linalg.norm(cur_dir)
                if cur_len < 1e-6:
                    rotations.append([1.0, 0.0, 0.0, 0.0])
                    continue
                cur_dir = cur_dir / cur_len
                q = self._quat_from_two_vectors(rest_dir, cur_dir)
                rotations.append([float(q[0]), float(q[1]), float(q[2]), float(q[3])])
            result.append({"name": mixamo_name, "rotations": rotations})
        return result

    @staticmethod
    def _quat_from_two_vectors(v_from: np.ndarray, v_to: np.ndarray) -> np.ndarray:
        """Quaternion (w,x,y,z) that rotates v_from to v_to."""
        v_from = v_from / (np.linalg.norm(v_from) + 1e-9)
        v_to = v_to / (np.linalg.norm(v_to) + 1e-9)
        d = float(np.dot(v_from, v_to))
        if d >= 0.99999:
            return np.array([1.0, 0.0, 0.0, 0.0])
        if d <= -0.99999:
            # 180° — pick any perpendicular
            axis = np.array([1.0, 0.0, 0.0]) if abs(v_from[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            axis = axis - v_from * float(np.dot(axis, v_from))
            axis = axis / (np.linalg.norm(axis) + 1e-9)
            return np.array([0.0, *axis])
        c = np.cross(v_from, v_to)
        w = 1.0 + d
        q = np.array([w, c[0], c[1], c[2]])
        q = q / np.linalg.norm(q)
        return q

    # Standard SMPL 22-joint kinematic tree (parent indices; -1 = root)
    _SMPL_PARENTS = [-1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19]

    @classmethod
    def _smpl_parent(cls, idx: int) -> Optional[int]:
        p = cls._SMPL_PARENTS[idx]
        return p if p >= 0 else None

    @staticmethod
    def _smpl_rest_pose() -> np.ndarray:
        """Standard SMPL T-pose joint positions (relative to root). Y up,
        arms out to sides, legs down. Scaled to ~1m tall."""
        return np.array([
            [0.0, 0.0, 0.0],          # 0 pelvis (root)
            [0.058, -0.082, 0.0],     # 1 L hip
            [-0.058, -0.082, 0.0],    # 2 R hip
            [0.0, 0.124, 0.0],        # 3 spine1
            [0.0, -0.387, 0.0],       # 4 L knee
            [0.0, -0.387, 0.0],       # 5 R knee
            [0.0, 0.213, 0.0],        # 6 spine2
            [0.0, -0.707, 0.0],       # 7 L ankle
            [0.0, -0.707, 0.0],       # 8 R ankle
            [0.0, 0.273, 0.0],        # 9 spine3
            [0.0, 0.066, 0.138],      # 10 L foot
            [0.0, 0.066, -0.138],     # 11 R foot
            [0.0, 0.376, 0.0],        # 12 neck
            [0.0, 0.276, 0.0],        # 13 L collar
            [0.0, 0.276, 0.0],        # 14 R collar
            [0.0, 0.526, 0.0],        # 15 head
            [0.189, 0.276, 0.0],      # 16 L shoulder
            [-0.189, 0.276, 0.0],     # 17 R shoulder
            [0.0, -0.250, 0.0],       # 18 L elbow
            [0.0, -0.250, 0.0],       # 19 R elbow
            [0.0, -0.255, 0.0],       # 20 L wrist
            [0.0, -0.255, 0.0],       # 21 R wrist
        ], dtype=np.float32)


# ── HTTP handler ────────────────────────────────────────────────────────
class MotionRequestHandler(BaseHTTPRequestHandler):
    server: MotionServer  # type: ignore[assignment]

    @property
    def motion_server(self) -> "MotionServer":
        # The ThreadingHTTPServer instance (self.server) carries the MotionServer
        # in .motion_server (set after construction). Falling back to ._model
        # for legacy accessors (kept so monkey-patching stays simple).
        return self.server.motion_server  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):  # quieter logging
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, status: int, body: dict):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body_raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(body_raw) if body_raw else {}
        except json.JSONDecodeError:
            return self._send_json(400, {"error": "invalid JSON"})
        if self.path == "/motion" or self.path == "/":
            return self._handle_enqueue(body)
        if self.path == "/motion/status":
            return self._handle_status(body)
        if self.path == "/curator":
            return self._handle_curator(body)
        return self._send_json(404, {"error": "not found"})

    def do_GET(self):
        if self.path.startswith("/motion/get"):
            return self._handle_get()
        if self.path.startswith("/motion/status"):
            # GET convenience: /motion/status?id=<id1>,<id2>,...  (or
            # repeated ?id= params). The Godot client uses POST with a
            # {"ids":[...]} body; this just lets you poll from a browser
            # or curl without -X POST -d.
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            ids = qs.get("id") or []
            if isinstance(ids, str):
                ids = [ids]
            return self._handle_status({"ids": ids})
        if self.path == "/motion/cap":
            return self._send_json(200, self.motion_server.snapshot())
        if self.path == "/healthz":
            ms = self.motion_server
            return self._send_json(200, {"ok": True, "model_loaded": ms._model is not None})
        if self.path == "/library":
            return self._handle_library()
        if self.path.startswith("/curator/status"):
            return self._handle_curator_status()
        return self._send_json(404, {"error": "not found"})

    # ── Endpoint implementations ─────────────────────────────────────
    def _handle_enqueue(self, body: dict):
        prompt = (body.get("prompt") or "").strip()
        if not prompt:
            return self._send_json(400, {"error": "prompt is required"})
        frames = int(body.get("frames") or 60)
        suggested_name = (body.get("suggested_name") or "").strip()
        ms = self.motion_server
        if ms.depth() >= ms.capacity:
            return self._send_json(429, {
                "error": "queue full",
                "queue_depth": ms.depth(),
                "capacity": ms.capacity,
            })
        req = ms.enqueue(prompt, frames, suggested_name)
        log.info("ENQUEUE [%s] prompt=%r frames=%d (depth now %d)",
                 req.request_id, prompt, req.frames, ms.depth())
        return self._send_json(200, {
            "id": req.request_id,
            "position": ms.depth(),   # includes this one
            "queue_depth": ms.depth(),
        })

    def _handle_status(self, body: dict):
        ids = body.get("ids") or []
        if not isinstance(ids, list):
            return self._send_json(400, {"error": "ids must be a list"})
        results = []
        for req in self.motion_server.status(ids):
            entry = {
                "id": req.request_id,
                "status": req.status,
                "prompt": req.prompt,
                "frames": req.frames,
                "elapsed_sec": round(req.elapsed(), 1),
            }
            if req.status == "done":
                entry["animation_name"] = req.animation["name"] if req.animation else "?"
                entry["animation_url"] = f"/motion/get?id={req.request_id}"
            if req.status == "failed":
                entry["error"] = req.error
            results.append(entry)
        return self._send_json(200, {"results": results})

    def _handle_get(self):
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        ids = qs.get("id") or []
        if not ids:
            return self._send_json(400, {"error": "id query param required"})
        req = self.motion_server.get(ids[0])
        if req is None:
            return self._send_json(404, {"error": "unknown id"})
        if req.status != "done":
            return self._send_json(409, {"error": "not done yet", "status": req.status})
        # Animation is a dict; send as JSON.
        return self._send_json(200, {
            "id": req.request_id,
            "name": req.animation["name"],
            "frames": req.animation["frames"],
            "fps": req.animation["fps"],
            "bones": req.animation["bones"],
        })

    def _handle_library(self):
        lib = self.motion_server.library.get()
        if not lib:
            return self._send_json(404, {"error": "motion library not loaded", "path": self.motion_server.library.path_str()})
        # Return the latest cached library. mtime is in the header so curl
        # operators can confirm the watchdog reloaded.
        mtime = self.motion_server.library.mtime()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        body = json.dumps(lib).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        if mtime is not None:
            self.send_header("X-Library-Mtime", f"{mtime:.3f}")
        self.end_headers()
        self.wfile.write(body)

    def _handle_curator(self, body: dict):
        """POST /curator — kick off an auto-curator job.

        Request schema:
            {action, reason?, urgency?, max_results?}

        Returns 202 Accepted with a job id; the caller polls
        ``GET /curator/status?id=<job_id>`` to see the result.
        """
        if handle_curator_request is None:
            return self._send_json(503, {
                "error": "curator module not loaded",
                "hint": "check that astro_assistant/curator.py imports cleanly",
            })
        action = (body.get("action") or "").strip()
        if not action:
            return self._send_json(400, {"error": "action is required"})
        job = self.motion_server.curator.enqueue(body)
        return self._send_json(202, {
            "job_id": job.job_id,
            "status": "pending",
            "status_url": f"/curator/status?id={job.job_id}",
            "request": job.request,
        })

    def _handle_curator_status(self):
        """GET /curator/status?id=<job_id> — poll for a job's outcome.

        Returns the job's current state, plus the result dict (added/
        skipped/new_hash) once status == "done".
        """
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        ids = qs.get("id") or []
        if not ids:
            return self._send_json(400, {"error": "id query param required"})
        job = self.motion_server.curator.get(ids[0])
        if job is None:
            return self._send_json(404, {"error": "unknown job id"})
        body: dict = {
            "job_id": job.job_id,
            "status": job.status,
            "request": job.request,
            "enqueued_at": job.enqueued_at,
        }
        if job.started_at is not None:
            body["started_at"] = job.started_at
        if job.finished_at is not None:
            body["finished_at"] = job.finished_at
            body["elapsed_sec"] = round(job.finished_at - job.started_at, 2) if job.started_at else None
        if job.status == "done":
            body["result"] = job.result or {}
        elif job.status == "failed":
            body["error"] = job.error
        return self._send_json(200, body)


# ── Main ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="FloodDiffusion motion server for Aria")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"HuggingFace model id (default {DEFAULT_MODEL}; use {TINY_MODEL} for 8GB VRAM)")
    ap.add_argument("--capacity", type=int, default=DEFAULT_CAPACITY)
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--preload", action="store_true", help="load the model on startup (not on first request)")
    ap.add_argument("--mock", action="store_true",
                    help="use a synthetic model — fast, no GPU needed, for the stress test only")
    ap.add_argument("--library-path", default=None,
                    help="path to motion_library.json (default: ./motion_library.json next to this script)")
    ap.add_argument("--library-poll", type=float, default=60.0,
                    help="watchdog poll interval in seconds (default 60)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    library_path = (
        Path(args.library_path).resolve()
        if args.library_path
        else (LIBRARY_DEFAULT_PATH if LIBRARY_DEFAULT_PATH else None)
    )
    if library_path is not None and not library_path.exists():
        log.warning(
            "motion library not found at %s — server will start, but /library will 404 and "
            "the diffusion context will be empty",
            library_path,
        )
    elif library_path is not None:
        log.info("motion library path: %s (watchdog every %.0fs)", library_path, args.library_poll)

    srv = MotionServer(
        args.model, args.capacity, args.fps, args.preload,
        mock=args.mock,
        library_path=library_path,
        library_poll_sec=args.library_poll,
    )
    log.info("library loaded: %d animations", srv.library.count())
    # Operator-facing smoke test: print (not just log) so the operator can
    # confirm load by tailing stdout, regardless of --log-level.
    print(f"library loaded: {srv.library.count()} animations", flush=True)
    srv.start()

    httpd = ThreadingHTTPServer((args.bind, args.port), MotionRequestHandler)
    httpd.motion_server = srv
    log.info("HTTP server listening on http://%s:%d (POST /motion, /motion/status, /curator; GET /motion/get, /motion/cap, /healthz, /library, /curator/status)",
             args.bind, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down…")
        srv.stop()
        httpd.shutdown()


if __name__ == "__main__":
    main()
