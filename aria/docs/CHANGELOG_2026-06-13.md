# Aria — Change Log, 2026-06-13 (autonomous run)

This was an unattended scheduled run, so every choice was made autonomously and
is noted below. **I could not launch Godot or reach your LLM/TTS servers from
this environment**, so nothing was runtime-tested — changes were written to be
compile-safe, additive, and gracefully degrading. Treat the first launch as the
verification pass and use the Godot **Output** panel (it's full of `[Aria]`,
`[Expr]`, `[TTS]`, `[Health]`, `[Speech]` breadcrumbs) to confirm each system.

## Your requests → what I did

**"Integrate the clamp" / speech bubble disappeared, want it near her head.**
The head-follow clamp is now active and the bubble is positioned from a new
`CharacterController.HeadScreen` point each frame. The real reason it
"disappeared": the `Label` had its height seeded to 0 and never resized, so the
dark bubble panel collapsed to nothing. `Main.OnResponse` now sizes the bubble
to its text, restyles it as a rounded bordered bubble, and — crucially — she now
shows an **offline fallback line** if the LLM is unreachable, so you always see
*something*. (`Main.cs`)

**"Speed up the rate she travels to match her strut."** `WalkSpeed` 68 → **160
px/s**. The prior value was far too slow (she crept while her legs strode — the
foot-slide you saw). Math + reasoning are in the comment above the field; it's an
`[Export]`, so tune live in the Inspector (140 deliberate … 200 brisk).
(`CharacterController.cs`)

**Turn animation when she starts walking / when she stops to face front.** The
Turn state is generalised: she plays a real `left turn`/`right turn` clip both
when changing into a walk *and* when finishing a walk to face the camera
(`EnterTurnToFront`), instead of snapping. Body yaw stays authoritative so she
always ends facing correctly even if a turn clip's handedness looks off.
(`CharacterController.cs`)

**"She shouldn't walk all the time — use the other animations / climb to sit."**
The idle loop was only ever playing `idle`. It now picks among `idle`, `idle2`,
`look`, `yawn`, and the occasional dance on the floor; **sits** (`sit` /
`sit_talk` / `sit_clap`) when perched on a window; and *lingers* in place far
more instead of pacing. Climbing-to-perch already existed and now ends in
sitting. New tunables: `DanceChance`, `OneShotIdleChance`, `LingerChance`,
`PerchStayChance`. (`CharacterController.cs`)

**"No voice when she speaks."** There was no TTS code at all. New `TTSBridge.cs`
sends her line to a local Coqui XTTS server and plays the returned WAV, with a
JSON-POST mode for a custom cloning wrapper. Setup + the exact server command are
in `docs/ARIA_AI_SETUP.md` §2.

**"Her expression is stuck on neutral."** Nothing drove the face. New
`ExpressionController.cs` discovers the VRoid/VRM blend shapes at runtime and
layers emotion + blinking + a talking mouth-flap. Emotion comes from the AI.
See §3 of the setup doc for the one VRM caveat I couldn't verify without running.

**"Full use of AI — help me, watch herself, be self-healing, relay emotion,
self-fine-tune."** `LLMBridge.cs` now keeps conversation memory, asks for a
structured `{say, emotion, action}` reply (emotion → face, action → gesture),
parses defensively, falls back to offline lines, and logs every turn to
`aria_dataset.jsonl`. New `HealthMonitor.cs` is the self-healing watchdog
(off-screen/NaN recovery, stalled-anim nudge, missing-clip + LLM-down logging),
writing `aria_health.log`. The daily fine-tune script is `tools/aria_finetune.py`.
Honest scope on "sentient / self-fine-tuning" is in setup doc §4–5.

**Also fixed (latent bug):** `EnterReact` was playing `"surprised"`, which isn't
in the scene's animation list — so her reaction when she spoke silently failed.
Now plays `"react"` (Standing Greeting). (`CharacterController.cs`)

## Files

Changed: `scripts/CharacterController.cs`, `scripts/Main.cs`, `scripts/LLMBridge.cs`.
New: `scripts/ExpressionController.cs`, `scripts/TTSBridge.cs`,
`scripts/HealthMonitor.cs`, `docs/ARIA_AI_SETUP.md`, this file,
`tools/aria_finetune.py`.
Untouched on purpose: `AnimationBuilder.cs`, `WindowDetector.cs`, `Main.tscn`
node graph, `project.godot`, the Aria model and its import settings.

The three new scripts are created in code by `Main._Ready` (`new …` + `AddChild`),
so **no scene rewiring or NodePaths were needed** and `Main.tscn` was not edited.
They're picked up automatically by the SDK-style `.csproj`.

## Did NOT regress (verified against the prior handoff)

Animation track path format `Armature/Skeleton3D:{bone}`; stripped Hips
translation; orthographic camera size 8 (`ApplyScreenPosition` still uses 8);
maximized/borderless/transparent/always-on-top window; the win32 click-through
region. None of these were touched.

## Verify on first launch (in this order)

1. **Compiles** — Build in Godot; watch for C# errors. (No build tool existed in
   the automated env, so this is the one thing I genuinely couldn't check.)
2. **She speaks on startup** — a bubble should appear near her head after ~2s,
   even with your LLM server off (offline line). Confirms the bubble fix.
3. **Face** — check the `[Expr] Discovered … blend shapes` log; if emotions don't
   move, follow setup doc §3 (name mapping / VRM override).
4. **Voice** — start the Coqui server (setup §2); watch for `[TTS]` errors.
5. **Movement** — she should stride at a natural pace, turn before walking and
   before facing front, and spend time idling/looking/sitting rather than pacing.
6. **Self-heal** — `aria_health.log` should get a `startup` line; `aria_dataset.jsonl`
   should gain a row each time she talks.

## Known limitations (no runtime here)

- C# not compiled — I used only stable Godot 4.6 / .NET 8 APIs and cross-checked
  every animation name against the scene, but a real build is the proof.
- VRM expression override (setup §3) and the exact Coqui server contract
  (§2) are the two runtime unknowns; both fail safe and log clearly.
- Real fine-tuning needs your GPU + local models, which the automated session
  can't reach — the logging, template, and schedule design are done; the
  training run happens on your machine.
