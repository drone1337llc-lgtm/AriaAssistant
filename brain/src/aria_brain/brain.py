"""Brain orchestrator — the heart of Aria Brain.

Takes a user message, builds the right context (persona + mood + memories + system state),
calls the LLM, stores the exchange in memory, updates mood, and optionally speaks via TTS.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import AsyncIterator, Optional

from aria_brain import llm, memory, mood, personality, tts
from aria_brain.config import LM_STUDIO_CODER_MODEL

log = logging.getLogger("aria_brain.brain")

# Matches one complete sentence/clause ending in . ! ? … or a newline.
# Used to chunk the streamed reply so TTS can start on sentence one.
_SENTENCE_RE = re.compile(r"[^.!?…\n]*[.!?…\n]+", re.S)
_SOFT_FLUSH_CHARS = 240  # flush a run-on clause this long even with no terminator


def _split_sentences(buf: str) -> tuple[list[str], str]:
    """Pull complete sentences out of a growing buffer.

    Returns (complete_chunks, remainder). Complete chunks end in sentence
    punctuation; the remainder is the unfinished tail kept for the next delta.
    A very long terminator-less run-on is force-flushed at the last space so
    TTS never stalls waiting for a period that isn't coming.
    """
    chunks: list[str] = []
    last = 0
    for m in _SENTENCE_RE.finditer(buf):
        piece = m.group().strip()
        if piece:
            chunks.append(piece)
        last = m.end()
    remainder = buf[last:]
    if len(remainder) >= _SOFT_FLUSH_CHARS:
        cut = remainder.rfind(" ", 0, _SOFT_FLUSH_CHARS)
        if cut > 0:
            head = remainder[:cut].strip()
            if head:
                chunks.append(head)
            remainder = remainder[cut:].lstrip()
    return chunks, remainder


async def handle_message(
    text: str,
    source: str = "chat",
    speak: bool = False,
    temperature: float = 0.8,
    max_tokens: int = 200,
    max_drift_retries: int = 2,
) -> dict:
    """Process one user message end-to-end. Returns a dict with reply + diagnostics.

    If the LLM drifts to a non-Latin script (Chinese/Japanese/Korean/Cyrillic/Arabic/...),
    the reply is rejected and re-prompted up to `max_drift_retries` times with a stronger
    language enforcement hint. If retries are exhausted, the last drift reply is
    returned with `drift_detected` set so the caller can show a fallback message.
    """
    text = (text or "").strip()
    if not text:
        return {"reply": "", "mood": 3.0, "mood_label": personality.mood_to_label(3.0),
                "audio_url": None, "memories_used": 0}

    # 1. Update mood based on sentiment + reset the decay clock.
    hours_before = mood.hours_since_last_interaction()
    mood_value, _ = mood.note_interaction(text)
    mood_label = personality.mood_to_label(mood_value)

    # 2. Pull relevant + recent memories (async wrappers — ChromaDB is sync).
    try:
        relevant = await memory.asearch(text, kind="episodic", n=5)
        relevant_facts = await memory.asearch(text, kind="fact", n=3)
        recent_eps = await memory.arecent(kind="episodic", n=5)
        recent_thoughts = await memory.arecent(kind="thought", n=3)
    except Exception as exc:
        log.warning(f"memory read failed: {exc}")
        relevant, relevant_facts, recent_eps, recent_thoughts = [], [], [], []

    # 3. Build system context.
    ctx = personality.now_context()
    ctx["last_interaction_hours_ago"] = hours_before  # what it was BEFORE this update

    # 4. Decide routing. Real tasks (code, debugging, parsing, analysis) go to
    #    the capable CODER model with room to actually answer; casual chat stays
    #    on the fast roleplay chat model. This is the fix for Aria "refusing" to
    #    help with code: she was being run on the brief-by-design chat persona +
    #    a 200-token cap and never reached the coder model at all.
    is_task = personality.looks_like_task(text)

    # 5. Compose the system prompt (task mode lifts the brevity rule).
    sys_prompt = personality.build_system_prompt(
        mood=mood_value,
        mood_label=mood_label,
        recent_memories=[m["text"] for m in (recent_eps + recent_thoughts)],
        relevant_memories=[m["text"] for m in (relevant + relevant_facts)],
        system_context=ctx,
        task_mode=is_task,
    )

    # Route + budget per mode.
    if is_task:
        call_model = LM_STUDIO_CODER_MODEL
        call_max_tokens = max(max_tokens, 1500)   # code needs room
        call_timeout = 120.0                       # 9B coder can be slow on long output
        temperature = min(temperature, 0.4)        # tighter sampling = more correct code
    else:
        call_model = None                          # llm.chat falls back to the chat model
        call_max_tokens = max_tokens
        call_timeout = 30.0

    # 6. Call the LLM (with drift detection + retry).
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": text},
    ]
    reply = ""
    drift_script = ""
    attempts = 0
    while attempts <= max_drift_retries:
        attempts += 1
        reply = await llm.chat(messages, model=call_model, temperature=temperature,
                               max_tokens=call_max_tokens, timeout=call_timeout)
        is_drift, script = personality.detect_drift(reply)
        if not is_drift:
            drift_script = ""
            break
        # Drift detected. Re-prompt with an appended stronger constraint.
        log.warning(f"language drift attempt {attempts}: detected {script} in reply")
        drift_script = script
        if attempts > max_drift_retries:
            break
        # Build a stronger follow-up system message that REQUIRES English.
        strong_msg = (
            "CRITICAL: Your previous reply contained text in a non-Latin script "
            f"({script}). You must respond in English ONLY. No Chinese, Japanese, "
            "Korean, Cyrillic, Arabic, or any other script. ASCII Latin letters only. "
            "If you don't know how to say something in English, say '...'. Reply now in English."
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": text},
            {"role": "assistant", "content": reply},  # show the drifted reply so the model sees its mistake
            {"role": "user", "content": strong_msg},
        ]
        temperature = max(0.2, temperature * 0.7)  # also tighten the sampler for the retry

    # 7. Store this exchange in memory. We do this even if reply is empty so we
    #    don't lose the user's words.
    try:
        await memory.aadd_memory(
            f"user: {text}",
            "episodic",
            {"role": "user", "source": source, "ts": datetime.utcnow().isoformat() + "Z"},
        )
        if reply:
            drift_meta = {"role": "aria", "source": source, "mood": mood_value,
                          "ts": datetime.utcnow().isoformat() + "Z"}
            if drift_script:
                drift_meta["drift_script"] = drift_script
                drift_meta["drift_retries"] = attempts - 1
            await memory.aadd_memory(
                f"aria: {reply}",
                "episodic",
                drift_meta,
            )
    except Exception as exc:
        log.warning(f"memory write failed: {exc}")

    # 8. Optional TTS. Best-effort — never fail the message because TTS is down.
    audio_url = None
    if speak and reply:
        audio_url = await tts.speak(reply)

    return {
        "reply": reply,
        "mood": mood_value,
        "mood_label": mood_label,
        "audio_url": audio_url,
        "memories_used": len(relevant) + len(relevant_facts),
        "recent_memories_used": len(recent_eps) + len(recent_thoughts),
        "drift_detected": bool(drift_script),
        "drift_script": drift_script,
        "attempts": attempts,
        "task_mode": is_task,
        "model": call_model or "chat",
    }


async def handle_message_stream(
    text: str,
    source: str = "voice",
    temperature: float = 0.8,
    max_tokens: int = 200,
) -> AsyncIterator[dict]:
    """Streaming sibling of handle_message — for voice. Yields event dicts:

      {"type": "sentence", "text": "..."}   one complete sentence, as soon as it forms
      {"type": "done", "reply": "...", "mood": .., "mood_label": "..",
       "task_mode": bool, "model": "..."}   terminal event

    The caller (the /voice-stream WS) forwards each sentence to streaming TTS so
    Aria starts speaking sentence one while the rest is still being generated.
    Drift-retry is skipped here (it needs the full reply); we do a single post-hoc
    drift check on the final text and flag it. Memory is written at the end.
    """
    text = (text or "").strip()
    if not text:
        yield {"type": "done", "reply": "", "mood": 3.0,
               "mood_label": personality.mood_to_label(3.0), "task_mode": False, "model": "chat"}
        return

    # Mood + memory + context (same as handle_message).
    hours_before = mood.hours_since_last_interaction()
    mood_value, _ = mood.note_interaction(text)
    mood_label = personality.mood_to_label(mood_value)
    try:
        relevant = await memory.asearch(text, kind="episodic", n=5)
        relevant_facts = await memory.asearch(text, kind="fact", n=3)
        recent_eps = await memory.arecent(kind="episodic", n=5)
        recent_thoughts = await memory.arecent(kind="thought", n=3)
    except Exception as exc:
        log.warning(f"memory read failed: {exc}")
        relevant, relevant_facts, recent_eps, recent_thoughts = [], [], [], []

    ctx = personality.now_context()
    ctx["last_interaction_hours_ago"] = hours_before

    is_task = personality.looks_like_task(text)
    sys_prompt = personality.build_system_prompt(
        mood=mood_value, mood_label=mood_label,
        recent_memories=[m["text"] for m in (recent_eps + recent_thoughts)],
        relevant_memories=[m["text"] for m in (relevant + relevant_facts)],
        system_context=ctx, task_mode=is_task,
    )
    if is_task:
        call_model = LM_STUDIO_CODER_MODEL
        call_max_tokens = max(max_tokens, 1500)
        temperature = min(temperature, 0.4)
    else:
        call_model = None
        call_max_tokens = max_tokens

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": text},
    ]

    # Stream deltas → buffer → emit complete sentences as they form.
    buf = ""
    full = []
    async for delta in llm.chat_stream(messages, model=call_model, temperature=temperature,
                                        max_tokens=call_max_tokens):
        full.append(delta)
        buf += delta
        chunks, buf = _split_sentences(buf)
        for c in chunks:
            yield {"type": "sentence", "text": c}
    tail = buf.strip()
    if tail:
        yield {"type": "sentence", "text": tail}

    reply = "".join(full).strip()
    drift, drift_script = personality.detect_drift(reply)

    # Persist the exchange (best-effort).
    try:
        await memory.aadd_memory(
            f"user: {text}", "episodic",
            {"role": "user", "source": source, "ts": datetime.utcnow().isoformat() + "Z"},
        )
        if reply:
            await memory.aadd_memory(
                f"aria: {reply}", "episodic",
                {"role": "aria", "source": source, "mood": mood_value,
                 "ts": datetime.utcnow().isoformat() + "Z"},
            )
    except Exception as exc:
        log.warning(f"memory write failed: {exc}")

    yield {
        "type": "done",
        "reply": reply,
        "mood": mood_value,
        "mood_label": mood_label,
        "task_mode": is_task,
        "model": call_model or "chat",
        "drift_detected": bool(drift),
        "drift_script": drift_script,
    }


async def handle_reflection() -> dict:
    """One reflection tick — prompt Aria to think out loud, store the thought."""
    mood_value, _ = mood.get_current()
    mood_label = personality.mood_to_label(mood_value)
    hours_since = mood.hours_since_last_interaction()

    try:
        recent_eps = await memory.arecent(kind="episodic", n=5)
        recent_thoughts = await memory.arecent(kind="thought", n=5)
    except Exception as exc:
        log.warning(f"memory read failed: {exc}")
        recent_eps, recent_thoughts = [], []

    ctx = personality.now_context()
    ctx["last_interaction_hours_ago"] = hours_since

    sys_prompt = personality.build_system_prompt(
        mood=mood_value,
        mood_label=mood_label,
        recent_memories=[m["text"] for m in recent_eps],
        relevant_memories=[m["text"] for m in recent_thoughts],
        system_context=ctx,
    )

    user_prompt = (
        f"It's {ctx.get('time')} on a {ctx.get('day')}. "
        f"You last heard from the user {hours_since:.1f}h ago. "
        "What are you thinking right now? One sentence, in character. No preamble."
    )

    thought = await llm.chat(
        [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.9,
        max_tokens=80,
    )

    if thought:
        try:
            await memory.aadd_memory(
                thought,
                "thought",
                {"mood": mood_value, "mood_label": mood_label, "trigger": "reflection"},
            )
        except Exception as exc:
            log.warning(f"thought write failed: {exc}")

    return {"thought": thought, "mood": mood_value, "hours_since_interaction": hours_since}