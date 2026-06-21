# Streaming voice — design & plan

Goal: make Aria's spoken conversation feel **natural and near-instant** without the
weight of PersonaPlex. Keep the brain (smart, memory, coder-routing) + Jessica (XTTS),
but stop the "wait for whole → then next stage" lockstep. Bluetooth-friendly: the mic is
only hot while a **push-to-talk** button is held.

## The win: overlap the stages
Current pipeline is strictly sequential (record whole → transcribe whole → think whole →
synthesize whole → play). Each stage waits for the previous to finish; the stacked waits
are the dead air. Fix = **stream + overlap**:
- Brain streams its reply token-by-token and is chunked into **sentences**.
- Each finished sentence is synthesized + played while the next is still being written.
- Result: Aria starts talking ~one sentence after you finish, not after the whole reply.

## Push-to-talk + barge-in (same button for "new thought" and "interrupt")
One button does both, by design (no always-open mic → no Bluetooth HFP static):
1. **Press** → immediately **stop Aria's playback and cancel her in-flight reply**
   (this IS the barge-in), then start capturing the mic.
2. **Hold** → stream mic audio up (or buffer locally).
3. **Release** → finalize transcript → brain streams reply → sentences → streaming TTS →
   playback. Pressing again at any point interrupts and starts the next turn.

## Architecture: one brain-side voice WebSocket
Put all streaming orchestration in the brain (Python, on PC2 near the GPU). The front-end
(PC1) stays a thin audio client. New endpoint `WS /voice-stream`:
- client → brain: `{"type":"ptt_down"}` (barge-in/cancel), binary audio frames,
  `{"type":"ptt_up"}` (end of turn).
- brain → client: `{"type":"cancel"}` (stop playback now), `{"type":"transcript","text":..}`,
  `{"type":"sentence","text":..}` (display), binary audio chunks (Aria's voice), `{"type":"done"}`.
The brain cancels any in-flight generation/TTS when a new `ptt_down` arrives.

## Pieces & status
- **Brain streaming core — DONE.** `llm.chat_stream()` (SSE deltas) + `brain.handle_message_stream()`
  (reuses routing/persona/memory, yields complete sentences). Verified by review.
- **`WS /voice-stream` — TODO** (task #21). Wires STT-in → `handle_message_stream` → streaming
  TTS-out, with ptt_down cancellation. Uses `asyncio.Task` cancellation for barge-in.
- **Streaming TTS — TODO** (task #22). The XTTS Jessica server (`tts_server_jessica.py`, on PC2)
  needs a chunked endpoint using XTTS `inference_stream()` so audio flows before the whole
  line is done. **Need the current server file to modify it accurately.**
- **Streaming STT — TODO.** With PTT the endpoint is the button release, so the simplest fast
  path is: stream mic frames to the brain during the hold, run faster-whisper on the
  GPU (`WHISPER_DEVICE=cuda` on PC2) the instant of release → transcript is ready in <~300ms.
  True incremental partials are a later polish.
- **Front-end (Godot) — TODO** (task #23). PTT button (press = `Stop()` playback + `ptt_down` +
  mic capture; release = `ptt_up`); replace batch `AudioStreamWav` in `TTSBridge.cs` with an
  `AudioStreamGenerator` + `AudioStreamPlayback.PushFrame` to play incoming chunks. **Need to
  confirm mic capture + playback live in Godot (vs the Python tray).**

## File map
- `brain/src/aria_brain/llm.py` — `chat_stream()` ✅
- `brain/src/aria_brain/brain.py` — `handle_message_stream()` + `_split_sentences()` ✅
- `brain/src/aria_brain/server.py` — add `WS /voice-stream` (task #21)
- TTS server on PC2 `scripts/tts_server_jessica.py` — add streaming endpoint (task #22)
- `aria/scripts/TTSBridge.cs` — streaming playback + `Stop()` on barge-in (task #23)
- `aria/scripts/` new `VoiceInput.cs` (or extend Main) — PTT button + mic capture (task #23)

## Build status — ALL CODE WRITTEN (2026-06-21), pending deploy + in-Godot test
- `llm.chat_stream()` ✅ · `brain.handle_message_stream()` ✅ · `WS /voice-stream` ✅
  (server.py) · streaming TTS server ✅ (`scripts/tts_server_jessica_streaming.py`) ·
  Godot client `aria/scripts/VoiceInput.cs` ✅.
- Brain code verified by review + isolated syntax check (the workspace bash mount went
  stale mid-session, so the normal py_compile is unreliable — real check happens on PC2 restart).
- `VoiceInput.cs` is the untestable piece (Godot audio buses, resampling, WS frames).
  Likely tuning spots are marked; expect a round of in-editor iteration.

## Deploy & wire
1. **Brain** (PC1 → PC2): `.\scripts\sync-to-pc2.ps1` then restart `AriaPC2Backend`.
   Set `WHISPER_DEVICE=cuda` in `brain/.env` so STT is fast on release (CPU whisper is slow).
2. **Streaming TTS**: copy `scripts/tts_server_jessica_streaming.py` contents over PC2's
   `Coqui-TTS-XTTS-v2-\scripts\tts_server_jessica.py` (keeps `/tts`, adds `/tts_stream`);
   the supervisor restarts it. Needs a bridge tunnel for :5003 (already configured).
3. **Godot**: add a `VoiceInput` node to `Main.tscn` (or `AddChild` it in `Main.cs`); set
   `TtsBridgePath` to the existing `TTSBridge` node and `BrainWsUrl=ws://127.0.0.1:8770/voice-stream`
   (rides the existing :8770 tunnel). Hold the mouse side-button to talk.

## Decisions
- **PTT trigger = a mouse side-button** (hold to talk / interrupt; release to send). As Aria
  is a click-through always-on-top overlay, capturing a side-button likely needs a global
  hook (reuse the existing WndProc hook in `Main.cs`) rather than Godot focus input.

## Open inputs needed (to build the rest accurately)
1. The current **`tts_server_jessica.py`** (PC2) — so the streaming endpoint matches its
   framework (Coqui `tts-server` vs a custom FastAPI wrapper) and the Jessica model load.
   **BLOCKS task #22.** Paste it or copy it into the repo.
2. Confirm **where mic capture + audio playback should live**: the **Godot** app (C#,
   `AudioStreamGenerator` + `AudioEffectCapture`) — assumed — or the Python tray. Decides
   C# vs Python for the client half. **Gates task #23.** (Leaning Godot.)
