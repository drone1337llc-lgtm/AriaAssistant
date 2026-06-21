# RESUME HERE — Aria (latest session 2026-06-20)

Pick-up note for the next session. Full detail in `docs/BRIDGE_AND_PERSISTENCE.md` and
`docs/PERSONAPLEX_INTEGRATION.md`. The 2026-06-19 bridge/persistence note is below this block.

## ===== SESSION 2026-06-20 — START HERE TOMORROW =====

### 0. Streaming voice — ALL CODE WRITTEN (newest, 2026-06-21). Deploy + test next.

Replaced the PersonaPlex idea with a lighter streaming pipeline on the existing brain +
Jessica (XTTS). Full design + deploy steps in `docs/STREAMING_VOICE.md`. Built this session:
`llm.chat_stream()`, `brain.handle_message_stream()` (sentence chunking), `WS /voice-stream`
(STT→sentences→TTS with barge-in cancel) in `server.py`, the streaming TTS server
`scripts/tts_server_jessica_streaming.py`, and the Godot client `aria/scripts/VoiceInput.cs`
(push-to-talk on a **mouse side-button**: press = barge-in + listen, release = send).
**NEXT: deploy** (sync brain→PC2 + restart; copy the streaming TTS server over PC2's
`Coqui-TTS-XTTS-v2-\scripts\tts_server_jessica.py`; set `WHISPER_DEVICE=cuda` in brain/.env)
**then wire `VoiceInput` into `Main.tscn`** (set `TtsBridgePath`→TTSBridge,
`BrainWsUrl=ws://127.0.0.1:8770/voice-stream`) and test in the Godot editor. `VoiceInput.cs`
is the untestable piece (audio buses/resampling/WS) — expect a round of iteration. NOTE:
the workspace bash mount went stale mid-session (showed a truncated llm.py); the real files
are correct — a normal py_compile on PC2 after sync is the true check.

### 1. PersonaPlex — PARKED (full memo: `PERSONAPLEX_NOTES.md` at project root)

**Decision 2026-06-21: shelved until a dedicated 24 GB+ GPU is available.** It ran fine on
the 3090 but ate the WHOLE card (~23 GB), and full-duplex is bad for a Bluetooth headset
(mic stays hot → stuck in narrowband HFP → static). Pivoting instead to a lighter
**streaming STT + streaming TTS + barge-in** upgrade on the existing brain+Jessica pipeline.
All install/runtime findings + how to revive are in `PERSONAPLEX_NOTES.md`. Design (for
revival) still in `docs/PERSONAPLEX_INTEGRATION.md`. The detail below is historical context.

Design is locked in `docs/PERSONAPLEX_INTEGRATION.md`. Architecture chosen by user:
**PersonaPlex = fast full-duplex voice (Jessica's voice, generates its own words); the
brain = slow conductor that eavesdrops on the live transcript, runs specialists
(coder/vision/memory) in the background while PersonaPlex keeps talking, then injects a
finished line via a new `POST /api/control` when ready ("hold" → run specialist →
"relay").** Confirmed from source: Jessica voice works (WAV voice-prompt), Aria's
transcript already streams as `0x02` text, single injection point is `LMGen.step`.

**Install state on PC2 (the 3090 box, hostname AIassistant):**
- Repo cloned to `C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\personaplex`.
- venv at `personaplex\.venv` (system Python 3.12). `moshi-personaplex 0.1.0` installed.
- torch pinned to **2.4.1+cu121** (CUDA True). `sphn` installed clean (no Windows issue).
- Server loads the 7B onto the 3090 and reaches warmup. **Crash at warmup = Triton missing**
  (Windows has no Triton; moshi uses `torch.compile`). FIX FOUND, not yet confirmed working.

**EXACT NEXT STEP (resume here):** in the `(.venv)` PowerShell in the `personaplex` dir:
```powershell
$ssl = New-Item -ItemType Directory -Force -Path "$env:TEMP\ppssl"
$env:NO_TORCH_COMPILE = "1"      # skip torch.compile/Triton → eager mode
python -m moshi.server --hf-repo "nvidia/personaplex-7b-v1" --ssl $ssl.FullName --host 0.0.0.0
# if it then errors on CUDA graphs: also $env:NO_CUDA_GRAPH = "1" and relaunch
```
Then open `https://<PC2-ip>:8998`, accept the self-signed cert, allow mic, pick a stock
voice + an Aria persona text-prompt, and TALK. **Phase-1 goal = judge naturalness + voice +
latency.** Eager mode is slower than best-case — don't reject on latency alone; the fix is
`pip install triton-windows` later. **Must unload LM Studio models first** so PersonaPlex
gets the full 24 GB (bf16 needs ~16–18 GB; no quantization flag exists — confirmed in
`loaders.py`; the Q8 GGUF is a dead end, wrong format for moshi.server).
If `NO_TORCH_COMPILE` works → Phase 3 (brain observer). Tasks #15–#19 track the phases.

Jessica voice (after a stock voice works): drop a clean ~15s `jessica.wav` (from the XTTS
training clips `data/jessica_voice/wavs/` on PC2) into a folder, relaunch with
`--voice-prompt-dir`, request `voice_prompt=jessica.wav`. `load_voice_prompt()` takes a WAV
directly — no `.pt` baking needed.

### 2. Brain changes made this session — NEED PC2 SYNC + RESTART to go live
- **Models:** triage/PARSER changed `qwen2.5-3b-instruct` → **`qwen2.5-coder-1.5b-instruct`**
  in `brain/.env`, `.env.example`, `config.py`. (chat/vision/embed/coder unchanged.) The new
  triage model must be loaded in LM Studio or PARSER calls 404.
- **Aria refusing to help with code — FIXED.** `brain.py` now routes real tasks
  (`personality.looks_like_task()`) to the **coder model** with 1500 tokens / 120s / tighter
  temp; casual chat stays on the chat model. `personality.py` gained a "Helping with real
  work" persona section (never refuse) + a `task_mode` system-prompt branch that lifts the
  1-3 sentence limit. All compiles; classifier tested.
- **Deploy (run on PC1):** `.\scripts\sync-to-pc2.ps1` then
  `ssh tench@192.168.68.88 "schtasks /End /TN AriaPC2Backend & schtasks /Run /TN AriaPC2Backend"`.
  Verify: `/message` reply shows `"task_mode":true,"model":"nvidia_nvidia-nemotron-nano-9b-v2"`.

### 3. Aria climb bugs — FIXED in code, need an in-editor verify run
`aria/scripts/CharacterController.cs`: (a) post-climb **teleport** fixed — she now starts at
the climb edge and walks to her spot (was snapping feet to the destination). (b) stiff
**slide-down** fixed — fall clip is time-scaled to the drop (cap 3x) so the real fall plays,
not the frozen wind-up. New logs: `[Climb] topped out: startX=… -> walkTo=…`, `[Fall] … clipRate=…x`.

### 4. Hair/bust/skirt physics — root cause re-diagnosed (see big section lower down)
NOT the model. Source weights are present & dominant (40% of hair verts, weight 1.00) in
BOTH `Ariaversion4.glb` AND the new `Ariav8.vrm` — proven by GLB parse. So re-rigging is
unnecessary; it's a Godot import/runtime issue. This session: flipped
`Ariaversion4.glb.import` to `generate_lods=false` + `force_disable_compression=true`; user
tested Forward+ renderer too — neither confirmed fixed yet. Added a `WEIGHTDIAG` probe to
`SpringBoneSimulator.cs` (DebugForceSway currently **true**) that dumps the IMPORTED hair
mesh's per-vertex bone weights. **Next: reimport `Ariaversion4.glb` (right-click→Reimport),
run, read the `[SpringBone] WEIGHTDIAG … domJSec=…%` line.** ~40% = weights survived import
(bug is the modifier write path); ~0% = Godot dropped them on import (attack import layer).
This is lower priority than PersonaPlex now. `models/Ariav8.vrm` left in place (harmless).

---

## Where we are

**Bridge mesh: DONE and stable.** All three nodes (PC1 .15, PC2 .88, TrueNAS .64)
connected, no flapping. Tunnels verified. Aria's brain + LM Studio proven
end-to-end through the tunnel (she replied to a `/message` test).

**PC2 provisioning:**
- ✅ brain venv (`pip install -e .`) — works, brain runs on :8770
- ✅ watchdog venv
- ✅ TTS: `coqui-tts` + `transformers==4.57.*`, torch CUDA on the 3090, `TTS_IMPORT: OK`
- ✅ Jessica model in place at the new in-project Coqui path
- 🔶 ChromaDB: installed (chromadb 0.6.3, `[server]` extra warning is harmless);
      **verify it's listening** and that the brain uses it
- 🔶 motion: venv install was the last thing kicked off — **verify**

**Not yet done:**
- [ ] Confirm ChromaDB up: `ssh tench@192.168.68.88 "netstat -ano | findstr :8000"`
- [ ] Confirm motion venv built + (optional) CUDA torch in it
- [ ] Copy updated `.env` (new models) to PC2 + sync scripts to PC2
- [ ] Turn on persistence (supervisor scheduled task) on PC2
- [ ] Full `bridge-health.ps1` green board
- [ ] Front-end test (launch Godot / chat window on PC1)

## Exact next commands

```powershell
# 1. verify chromadb + motion (from PC1)
ssh tench@192.168.68.88 "netstat -ano | findstr :8000"
ssh tench@192.168.68.88 "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\motion_lib\.venv\Scripts\python.exe C:\Users\Tench\pc2_check.py"

# 2. push config + corrected scripts to PC2
scp "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\brain\.env" tench@192.168.68.88:"C:/Users/Tench/Documents/AriaAssistantAppIKdiffusion/brain/.env"
.\scripts\sync-to-pc2.ps1

# 3. turn on persistence — RUN ON PC2, ELEVATED
.\scripts\install-aria-pc2-autostart.ps1
Start-ScheduledTask -TaskName AriaPC2Backend

# 4. test all at once (from PC1)
.\scripts\bridge-health.ps1          # want every tunnel UP
curl.exe http://127.0.0.1:8770/health
$b = @{ text = "morning Aria" } | ConvertTo-Json
(Invoke-WebRequest -UseBasicParsing -Method POST http://127.0.0.1:8770/message -Body $b -ContentType 'application/json').Content
```

## Watch-outs for tomorrow
- After the supervisor starts TTS, tail `logs\pc2\tts_server.err.log` — first
  Jessica model load is slow; XTTS could still surface a transformers runtime
  issue (we only proved *import*).
- If `/health` shows `memory.backend: local` after a brain restart, the brain's
  chromadb client (0.5.x) vs server (0.6.3) mismatch is the cause — optional fix,
  local fallback works.
- Bridge config.yaml rewrites itself on start (strips comments) — that's normal.
- Don't run a service-launching script over SSH expecting it to persist; that's
  what the supervisor + scheduled task are for.

## Hair/bust/skirt physics — diagnosed, not yet fixed

The `SpringBoneSimulator` (skirt/hair/bust jiggle) runs but produces NO visible
motion. Ruled OUT this session (all verified): bones exist (93 `J_Sec_*`),
categorized correctly, modifier invoked every frame, `influence=1`, and the
meshes ARE skinned to those bones (`SKINDIAG`: Body/Face/Hair each
`binds=148 J_Sec_binds=93`, same `Skeleton3D` the body uses).

Root cause: in **Godot 4.6.3**, `SetBonePoseRotation` on the `J_Sec_*` bones
doesn't reach the skinned mesh — a forced ±34deg sway via BOTH the
`SkeletonModifier3D` path AND a `_Process` path moved nothing, while IK on the
`J_Bip_*` body bones works fine. So it's an engine-path quirk specific to these
bones, not a data/skin/wiring problem.

**DEFINITIVE FINDING (2026-06-20):** it is NOT a code problem. Confirmed by a
manual test — selecting `J_Sec_Hair2_01` in the Godot editor's Skeleton3D dock
and rotating it 45° moves the hair mesh **not at all**. Also tried in code:
forced ±34° sway on all 93 J_Sec_ bones via the modifier path, the _Process
path, AND `SetBoneGlobalPose` (the VRM addon's own write method) — none deformed
the mesh, while IK on the J_Bip_ body bones works fine. `SpringBoneSimulator` is
the SOLE, LAST modifier (no competition). So the imported `Ariaversion4.glb`
mesh simply does not deform from the secondary bones, despite the skin reporting
93 J_Sec_ binds. Animations are irrelevant (every clip is 51 J_Bip_ tracks only).

**The fix is a model-pipeline job, not code:** re-bring the model in so the
secondary bones actually drive the mesh. Best path (she's a VRoid model):
export from VRoid Studio as **.vrm** and import THAT via the `addons/vrm` addon
— it sets up correct skinning AND native spring bones (hair/skirt/bust jiggle
works out of the box, and the custom `SpringBoneSimulator` becomes unnecessary).
This is a Godot-hands-on task (re-import, re-point `CharacterController` at the
new skeleton, re-bake the Mixamo anims). Alternative: re-skin in Blender and
re-export `.glb` with the J_Sec_ weights intact. Do NOT re-download animations —
they are not the cause.

Diagnostics left in `SpringBoneSimulator.cs` (all dormant/off): `DebugForceSway`,
`DriveFromProcess`, the `SKINDIAG` + modifier-list startup logs, and the
forced-sway now uses `SetBoneGlobalPose`. Safe to delete that instrumentation
when the model is fixed.

## PersonaPlex (next big feature — design locked, Phase 1 pending)

Full plan + grounded design in `docs/PERSONAPLEX_INTEGRATION.md`. Architecture: PersonaPlex
= fast full-duplex voice (Jessica's voice, generates its own words); brain = slow conductor
that eavesdrops, runs specialists (coder/vision/memory) in the background, and injects a
finished line via a new `POST /api/control` when ready. Confirmed from source: Jessica voice
works (WAV voice-prompt), Aria's transcript already streams as `0x02` text, single injection
point is `LMGen.step`. **Next action = Phase 1 (USER runs on PC2 3090): accept HF license,
stand up the server via Docker/WSL2, bake `Jessica.pt`, judge latency/quality.** Nothing
downstream proceeds until that's good. Tasks #15–#19 track the phases.

## Open / optional backlog
- Enable autologon on PC2 for hands-off boot (`netplwiz`).
- Telegram bot needs `TELEGRAM_BOT_TOKEN` in `brain/.env` if wanted.
- Align chromadb client/server versions if shared memory is desired.
- Point single-PC `start_aria.ps1` at the in-project Coqui path (consistency).
