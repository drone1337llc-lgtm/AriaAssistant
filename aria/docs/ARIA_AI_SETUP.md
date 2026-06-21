# Aria — AI, Voice, Expression & Self-Improvement Setup

This covers the systems added on 2026-06-13: the expanded brain, the voice
(Coqui XTTS), facial expressions, the self-healing watchdog, and the daily
self-fine-tune loop. The walking/turning/idle behaviour is documented inline in
`scripts/CharacterController.cs`.

Everything here is built to **degrade gracefully** — if the voice server or the
LLM is down, Aria still runs, still moves, and still shows text. None of these
systems can crash the app; they only log and fall back.

---

## 1. The brain (`scripts/LLMBridge.cs`)

Talks to any OpenAI-compatible chat endpoint. Set these on the **LLMBridge**
node in `scenes/Main.tscn` (Inspector) or as defaults in the script:

| Field | Default | Notes |
|---|---|---|
| `LMStudioUrl` | `http://192.168.68.88:1010/v1/chat/completions` | Your LM Studio / Ollama / llama.cpp / vLLM server. |
| `ModelName` | `llama-3-8b-lexi-uncensored` (set in scene) | Whatever your server exposes. |
| `MaxTokens` | 160 | Keep small — she speaks 1–2 sentences. |
| `Temperature` | 0.85 | |
| `MemoryTurns` | 8 | How many prior turns stay in context. |
| `DatasetPath` | `C:\Users\Tench\Documents\AI Learning\aria_dataset.jsonl` | Training log (see §5). |

**Structured replies.** She now asks the model for one line of JSON:

```json
{"say":"Hi! Nice to see you back.","emotion":"joy","action":"wave"}
```

`emotion` drives the face, `action` drives a one-shot gesture. If your model
ignores the format and returns plain prose, that's fine — the parser falls back
to treating the whole reply as `say` with a neutral emotion.

**Using several models.** You have multiple LLMs available. The simplest path:
point `LMStudioUrl`/`ModelName` at whichever model you want as her primary
voice. If you want automatic routing (a fast small model for chit-chat, a bigger
one for real help), run them behind one OpenAI-compatible proxy (LiteLLM,
or LM Studio's "JIT model loading") and switch `ModelName` per request — the
bridge already sends `model` on every call, so routing is a one-line change in
`SendMessage` when you want it.

---

## 2. The voice (`scripts/TTSBridge.cs` + Coqui XTTS-v2)

Created in code by `Main.cs`; configure it from the **Main** node's Inspector:
`VoiceEnabled`, `TtsUrl`, `TtsSpeaker`, `TtsLanguage`.

### Start your Coqui XTTS server

From `C:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-` (your venv there), the
stock Coqui server speaks the contract `TTSBridge` expects by default
(`GET /api/tts`):

```bat
python -m TTS.server.server --model_name tts_models/multilingual/multi-dataset/xtts_v2 --port 5002
```

Then leave `TtsUrl = http://127.0.0.1:5002/api/tts`. XTTS needs a speaker and a
language: set `TtsSpeaker` to a built-in XTTS speaker (e.g. `Ana Florence`) or to
your **cloned voice id**, and `TtsLanguage = en`.

### If you use a custom XTTS wrapper (voice cloning from a reference WAV)

Many XTTS-v2 setups expose a small Flask/FastAPI endpoint that takes JSON and a
`speaker_wav`. For that, flip `TTSBridge.UseJsonPost = true` and point `TtsUrl`
at it. The bridge will POST:

```json
{"text":"...","speaker":"<TtsSpeaker>","language":"<TtsLanguage>"}
```

and expects `audio/wav` (8- or 16-bit PCM) back. If your wrapper wants different
field names or a `speaker_wav` path, edit `PostAsync` in `TTSBridge.cs` (one
method, clearly marked).

### Why you heard no voice before

There was **no TTS code at all** — the old `LLMBridge` only emitted text. The
bridge is the new piece. If it's still silent after starting the server, check
the Godot **Output** panel for `[TTS] synthesis failed …` — that line tells you
whether the server was unreachable, returned non-WAV, etc.

---

## 3. The face (`scripts/ExpressionController.cs`)

Your VRoid/VRM model carries facial **blend shapes** (morph targets) like
`Fcl_ALL_Joy`, `Fcl_MTH_A`, `Fcl_EYE_Close`. This controller discovers them at
runtime and layers: a held **emotion** (from the AI), automatic **blinking**,
and a **mouth flap** while she speaks. That's why her face was stuck neutral —
nothing was ever driving the morphs.

On startup it logs exactly what it found:

```
[Expr] Discovered 52 blend shapes. Slots → joy=fcl_all_joy, fun=fcl_all_fun, …
[Expr] All names: [fcl_all_neutral, fcl_all_angry, fcl_all_fun, …]
```

**If emotions don't show**, read that `All names` line and compare to the
candidate lists in `Setup()` (e.g. add your model's real name to the `Resolve(…)`
call for the slot that's missing). 

**VRM caveat:** the godot-vrm addon sometimes runs its own expression driver that
can fight per-frame morph writes. If the face still won't move after fixing
names, the addon's expression system is overriding us — drive its expression API
instead, or disable its runtime expression node. This is the one piece I
couldn't verify without launching the project; the log will tell you which case
you're in.

Tunables on the (code-created) ExpressionController: `EmotionLerp`, `BlinkMin/MaxInterval`,
`MouthLevel`, `MouthSpeed`. Adjust defaults in the script.

---

## 4. Self-healing (`scripts/HealthMonitor.cs`)

A watchdog that runs every few seconds and recovers from the failure modes we
know about:

- feet drift off-screen / go NaN → teleport back to the floor;
- AnimationPlayer has no clips → log it (import/retarget broke);
- animation stalled → nudge back to Idle;
- LLM unreachable → noted (the brain already falls back to offline lines).

Every anomaly and recovery is appended to
`C:\Users\Tench\Documents\AI Learning\aria_health.log`.

**"Truly self-healing for any bug"** can't mean rewriting her own running code —
that isn't safe to do live. The realistic architecture is this watchdog **plus**
the daily agent loop (§5): the background run reads `aria_health.log` and the
conversation dataset and proposes *real* code/parameter fixes for you to accept.
That daily run is literally the scheduled Cowork task that produced this update.

---

## 5. Daily self-improvement loop

Two data streams are now being written every time she talks:

- `aria_dataset.jsonl` — `{ts, user, say, emotion, action, model, offline}` per turn.
- `aria_health.log` — anomalies + recoveries.

### a) Fine-tune on her own conversations

`tools/aria_finetune.py` is a ready-to-edit LoRA template: it reads
`aria_dataset.jsonl`, filters out `offline` turns, formats them as chat pairs,
and runs a short LoRA pass. **You must set the base-model path** (one of your
local models) and confirm the GPU/training libs in your `AI Learning` venv. Run
it manually first; once it's clean, schedule it.

### b) Schedule it daily

Either a Windows Task Scheduler job that runs the script overnight, or a Cowork
scheduled task that (1) runs the fine-tune and (2) reads `aria_health.log` to
suggest fixes. Point Aria's `ModelName` at the newest adapter each morning so she
"gets a little better every day."

> Honest scope note: real fine-tuning needs your GPU + model files, which aren't
> reachable from the automated session that wrote this. The logging, the script
> template, and the schedule design are done; the actual training run has to
> happen on your machine where the models live.

---

## 6. Quick tuning cheat-sheet

| Want… | Change | Where |
|---|---|---|
| Faster/slower travel | `WalkSpeed` (now 160) | CharacterController |
| Less pacing, more lounging | raise `LingerChance` / `PerchStayChance` | CharacterController |
| More/less dancing | `DanceChance` | CharacterController |
| Climb windows more | raise `ClimbChance` | CharacterController |
| Turn flourish length | `TurnAnimDuration`, `TurnAnimPlaybackSpeed` | CharacterController |
| Bubble on-screen time | `say.Length * 0.06` clamp | Main.OnResponse |
| Voice on/off, server, speaker | `VoiceEnabled`, `TtsUrl`, `TtsSpeaker` | Main node Inspector |
| Mouth openness | `MouthLevel` | ExpressionController |

See `docs/CHANGELOG_2026-06-13.md` for the full list of what changed and why.
