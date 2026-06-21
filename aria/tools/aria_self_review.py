#!/usr/bin/env python3
"""
aria_self_review.py - Aria's daily self-review / self-improvement pass.

This is the realistic core of "she gets a little better every day". Runtime
self-healing (HealthMonitor.cs) recovers from known glitches live; this script
is the *reflective* half: once a day it reads the two data streams Aria writes
while she runs -

  * aria_health.log     (HealthMonitor: anomalies + recoveries, tab-separated)
  * aria_dataset.jsonl  (LLMBridge: one JSON object per spoken turn)

- summarises them, and emits a dated Markdown report with concrete, prioritised
suggestions (e.g. "LLM was unreachable for 40% of turns - check the server",
"enough clean examples to fine-tune now: run aria_finetune.py"). It changes no
source code; it tells you (or the next agent run) exactly what to look at.

Safe by construction: read-only except for the report it writes; every file is
optional; missing/garbled lines are skipped, never fatal.

Usage:
    python aria_self_review.py                 # use default AI Learning paths
    python aria_self_review.py --print         # also echo the report to stdout
    python aria_self_review.py --health X --dataset Y --out-dir Z

Schedule it daily (Windows Task Scheduler or a Cowork scheduled task) right
after aria_finetune.py to close the loop.
"""

from __future__ import annotations
import argparse
import json
import os
from collections import Counter
from datetime import date, datetime

DEF_HEALTH  = r"C:\Users\Tench\Documents\AI Learning\aria_health.log"
DEF_DATASET = r"C:\Users\Tench\Documents\AI Learning\aria_dataset.jsonl"
DEF_OUTDIR  = r"C:\Users\Tench\Documents\AI Learning\reviews"

FINETUNE_MIN_EXAMPLES = 20   # keep in sync with aria_finetune.py


def read_health(path: str) -> dict:
    out = {"present": False, "kinds": Counter(), "messages": Counter(),
           "recent": [], "total": 0}
    if not os.path.exists(path):
        return out
    out["present"] = True
    lines = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            kind = parts[1].strip() if len(parts) > 1 else "?"
            msg = parts[2].strip() if len(parts) > 2 else line
            out["kinds"][kind] += 1
            out["messages"][msg] += 1
            lines.append((parts[0] if parts else "", kind, msg))
    out["total"] = len(lines)
    out["recent"] = lines[-8:]
    return out


def read_dataset(path: str) -> dict:
    out = {"present": False, "turns": 0, "offline": 0, "usable": 0,
           "emotions": Counter(), "actions": Counter(), "models": Counter(),
           "days": Counter(), "samples": [], "malformed": 0}
    if not os.path.exists(path):
        return out
    out["present"] = True
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                out["malformed"] += 1
                continue
            rows.append(row)
            out["turns"] += 1
            if row.get("offline"):
                out["offline"] += 1
            else:
                out["usable"] += 1
            out["emotions"][row.get("emotion", "?")] += 1
            out["actions"][row.get("action", "?")] += 1
            out["models"][row.get("model", "?")] += 1
            ts = row.get("ts", "")
            if ts:
                out["days"][ts[:10]] += 1
    out["samples"] = rows[-5:]
    return out


def build_suggestions(h: dict, d: dict) -> list:
    s = []
    # Brain reachability
    if d["turns"] >= 3:
        off_ratio = d["offline"] / max(1, d["turns"])
        if off_ratio >= 0.30:
            s.append(f"**Brain often unreachable** - {d['offline']}/{d['turns']} "
                     f"({off_ratio:.0%}) turns fell back to offline lines. Confirm the "
                     f"LLM server URL/port in LLMBridge and that the model is loaded.")
    # Emotion variety (the "stuck on neutral" symptom, seen from the data side)
    if d["usable"] >= 5:
        neutral = d["emotions"].get("neutral", 0)
        if neutral / max(1, sum(d["emotions"].values())) >= 0.85:
            s.append("**Emotion almost always 'neutral'** - the model may be ignoring the "
                     "structured JSON format. Lower temperature, strengthen the system "
                     "prompt's format instruction, or switch to a model that follows JSON.")
    # Action variety
    if d["usable"] >= 5 and len(d["actions"]) <= 1:
        s.append("**She never gestures** - every reply used action='none'. Same root cause "
                 "as above (structured replies); verify the model emits the action field.")
    # Health: recurring recoveries
    rec = h["kinds"].get("recover", 0)
    if rec >= 3:
        s.append(f"**{rec} self-heal recoveries logged** - recurring drift. Inspect the most "
                 f"common recovery message below; if it's off-screen resets, re-check screen "
                 f"geometry / camera size; if it's stalled-anim nudges, check the FBX retarget.")
    if h["kinds"].get("error", 0) > 0:
        s.append("**Hard errors in the health log** (kind=error) - likely the animation "
                 "library failed to build. Check the [AnimBuilder] lines in Godot's Output.")
    # Fine-tune readiness
    if d["usable"] >= FINETUNE_MIN_EXAMPLES:
        s.append(f"**Enough data to fine-tune** - {d['usable']} clean examples "
                 f"(>= {FINETUNE_MIN_EXAMPLES}). Run `python aria_finetune.py`, then point "
                 f"Aria's ModelName at the new adapter.")
    elif d["usable"] > 0:
        s.append(f"Only {d['usable']} clean examples so far (need {FINETUNE_MIN_EXAMPLES} to "
                 f"fine-tune) - keep chatting with her to grow the dataset.")
    if not s:
        s.append("No issues detected. Aria is healthy; nothing to change today.")
    return s


def render(h: dict, d: dict, suggestions: list) -> str:
    L = []
    L.append(f"# Aria - Daily Self-Review ({date.today().isoformat()})")
    L.append(f"\n_Generated {datetime.now():%Y-%m-%d %H:%M} from her own runtime logs. "
             f"No code was changed; this is a reflective report._\n")

    L.append("## Suggested next steps\n")
    for i, item in enumerate(suggestions, 1):
        L.append(f"{i}. {item}")

    L.append("\n## Conversation health\n")
    if not d["present"]:
        L.append("_No dataset yet (she hasn't spoken with the server reachable, or the path "
                 "is wrong)._")
    else:
        L.append(f"- Total turns logged: **{d['turns']}**  "
                 f"(clean: {d['usable']}, offline-fallback: {d['offline']})")
        L.append(f"- Active days: {len([k for k in d['days'] if k])}")
        L.append(f"- Emotions: {dict(d['emotions'])}")
        L.append(f"- Actions: {dict(d['actions'])}")
        L.append(f"- Models: {dict(d['models'])}")
        if d["malformed"]:
            L.append(f"- Malformed lines skipped: {d['malformed']}")
        if d["samples"]:
            L.append("\n  Recent lines:")
            for r in d["samples"]:
                say = (r.get("say", "") or "")[:80]
                L.append(f"    - [{r.get('emotion','?')}/{r.get('action','?')}] {say}")

    L.append("\n## Self-heal / health log\n")
    if not h["present"]:
        L.append("_No health log yet._")
    else:
        L.append(f"- Total events: **{h['total']}**  (by kind: {dict(h['kinds'])})")
        if h["recent"]:
            L.append("\n  Most recent events:")
            for ts, kind, msg in h["recent"]:
                L.append(f"    - {kind}: {msg[:90]}")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Aria daily self-review")
    ap.add_argument("--health", default=DEF_HEALTH)
    ap.add_argument("--dataset", default=DEF_DATASET)
    ap.add_argument("--out-dir", default=DEF_OUTDIR)
    ap.add_argument("--print", action="store_true", dest="echo")
    args = ap.parse_args()

    h = read_health(args.health)
    d = read_dataset(args.dataset)
    suggestions = build_suggestions(h, d)
    report = render(h, d, suggestions)

    try:
        os.makedirs(args.out_dir, exist_ok=True)
        out_path = os.path.join(args.out_dir, f"aria-review-{date.today().isoformat()}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[self-review] wrote {out_path}")
    except OSError as e:
        print(f"[self-review] could not write report ({e}); printing instead.")
        args.echo = True

    print(f"[self-review] {d['turns']} turns, {d['offline']} offline, "
          f"{h['total']} health events, {len(suggestions)} suggestion(s).")
    if args.echo:
        print("\n" + report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
