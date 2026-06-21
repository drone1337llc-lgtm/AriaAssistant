"""Mood state machine for Aria.

Persisted to a JSON file. Decays toward baseline when the user is quiet,
boosts on positive interaction. Read on every turn so the LLM sees fresh
mood (decay is computed lazily, not by a background timer).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from aria_brain.config import (
    MOOD_DECAY_AFTER_HOURS,
    MOOD_DECAY_PER_HOUR,
    MOOD_INITIAL,
    MOOD_SCALE_MAX,
    MOOD_SCALE_MIN,
    MOOD_STATE_PATH,
)


# Heuristic sentiment — keep it simple, no external model.
_POSITIVE_PATTERNS = [
    r"\b(love|adore|appreciate|thank you|thanks|amazing|awesome|brilliant|perfect)\b",
    r"\b(great job|well done|nice work|good catch|good bot|you'?\s*re the best)\b",
    r"[!]{2,}",
    r"[\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U0001F4A0-\U0001F4FF]{2,}",  # multiple emoji
]
_NEGATIVE_PATTERNS = [
    r"\b(hate|stupid|dumb|useless|annoying|shut up|terrible|awful|garbage)\b",
    r"\b(wrong|no that'?s not|that'?s incorrect)\b",
    r"\b(i'?m done|i quit|fuck off)\b",
]
_QUESTION_PATTERN = r"\?\s*$"


@dataclass
class MoodState:
    value: float = MOOD_INITIAL
    last_interaction: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    history: list[dict] = field(default_factory=list)  # last 50 {ts, value, reason}
    decay_started_at: Optional[str] = None  # when last_interaction was first past the threshold

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MoodState":
        return cls(**{k: d.get(k, getattr(cls(), k)) for k in cls.__dataclass_fields__})


def _load() -> MoodState:
    if not MOOD_STATE_PATH.exists():
        return MoodState()
    try:
        with open(MOOD_STATE_PATH, "r", encoding="utf-8") as f:
            return MoodState.from_dict(json.load(f))
    except (OSError, json.JSONDecodeError):
        return MoodState()


def _save(state: MoodState) -> None:
    MOOD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = MOOD_STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
    tmp.replace(MOOD_STATE_PATH)


def _hours_since(iso_ts: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.utcnow().replace(tzinfo=dt.tzinfo) - dt).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return 0.0


def _clip(v: float) -> float:
    return max(MOOD_SCALE_MIN, min(MOOD_SCALE_MAX, v))


def get_current() -> tuple[float, MoodState]:
    """Return (effective_mood, full_state). Decay is computed lazily."""
    state = _load()
    hours = _hours_since(state.last_interaction)
    if hours >= MOOD_DECAY_AFTER_HOURS and state.decay_started_at is None:
        state.decay_started_at = datetime.utcnow().isoformat() + "Z"
    if state.decay_started_at is not None:
        decay_hours = _hours_since(state.decay_started_at)
        state.value = _clip(state.value + MOOD_DECAY_PER_HOUR * decay_hours)
    return state.value, state


def note_interaction(text: str) -> tuple[float, MoodState]:
    """Update mood based on the user's message. Persists."""
    state = _load()
    text_l = text.lower()
    delta = 0.0
    reasons: list[str] = []

    if any(re.search(p, text_l) for p in _POSITIVE_PATTERNS):
        from aria_brain.config import MOOD_BOOST_POSITIVE
        delta += MOOD_BOOST_POSITIVE
        reasons.append("positive_sentiment")
    if any(re.search(p, text_l) for p in _NEGATIVE_PATTERNS):
        from aria_brain.config import MOOD_BOOST_NEGATIVE
        delta += MOOD_BOOST_NEGATIVE
        reasons.append("negative_sentiment")
    if re.search(_QUESTION_PATTERN, text.strip()):
        from aria_brain.config import MOOD_BOOST_QUESTION
        delta += MOOD_BOOST_QUESTION
        reasons.append("engaged_question")

    # Always refresh the interaction timestamp — that resets the decay clock.
    now_iso = datetime.utcnow().isoformat() + "Z"
    state.last_interaction = now_iso
    state.decay_started_at = None
    state.value = _clip(state.value + delta)
    if reasons:
        state.history.append({
            "ts": now_iso,
            "value": state.value,
            "reason": ",".join(reasons),
            "delta": delta,
        })
        state.history = state.history[-50:]
    _save(state)
    return state.value, state


def set_mood(value: float, reason: str = "manual") -> tuple[float, MoodState]:
    """Force mood to a value (e.g. from a reflection insight)."""
    state = _load()
    state.value = _clip(value)
    state.history.append({
        "ts": datetime.utcnow().isoformat() + "Z",
        "value": state.value,
        "reason": reason,
        "delta": value - state.value,
    })
    state.history = state.history[-50:]
    _save(state)
    return state.value, state


def hours_since_last_interaction() -> float:
    state = _load()
    return _hours_since(state.last_interaction)