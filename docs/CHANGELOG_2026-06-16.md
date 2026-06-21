# Aria — Change Log, 2026-06-16 (silent-failure sweep)

This was a silent-failure pass — no new features, no behavioural change in
the happy path. Five places in the C# codebase were swallowing errors or
returning useless data; all five now surface what went wrong so a future
debug session doesn't have to chase ghosts.

## Fixes

**1. `AriaMotionClient.MotionFailed` always sent an empty prompt** (`aria/scripts/AriaMotionClient.cs:196`).
The poll handler captured the error, removed the request from `_pending`,
then emitted `MotionFailed(id, _pending.ContainsKey(id) ? "" : "", err)`.
Both branches of that ternary returned the empty string — the consumer
always got `""` for the prompt field. So when a motion failed server-side,
the UI / LLM had no idea which prompt triggered the failure.

Fixed by reading `pr.Prompt` from the pending entry *before* removing it,
and emitting that as the second arg. Verified with `dotnet build`:
0 warnings, 0 errors.

**2. `HealthMonitor.ResolvePath` silently fell through to `user://`** (`aria/scripts/HealthMonitor.cs:127`).
If the configured `HealthLogPath` (e.g. `C:\Users\...\AI Learning\aria_health.log`)
was unreachable — drive offline, permission denied, etc. — Aria quietly
wrote to the user-data dir and the operator never knew. Now logs the path
and reason before falling back. Original `catch {}` → `catch (Exception e)` with `GD.PrintErr`.

**3. `LLMBridge.ResolveDatasetPath` had the same pattern** (`aria/scripts/LLMBridge.cs:810`).
If the fine-tune dataset directory was unreachable, the conversation
log silently landed in `user://` and the daily fine-tune script
(`tools/aria_finetune.py`) found nothing where it expected. Now logs the
fall-back so the operator can fix the path.

**4. `MotionLibraryMirror.DefaultPath` silently used a bare filename** (`aria/scripts/MotionLibraryMirror.cs:340`).
If `ProjectSettings.GlobalizePath("res://")` failed or the sibling
`astro_assistant/motion_library.json` was unreachable, the mirror fell
through to the bare string `"motion_library.json"` and Aria had an
empty AnimSources dict with no breadcrumb. Now logs the failure.

**5. `WindowDetector.Refresh` kept the last known title on any Win32 error** (`aria/scripts/WindowDetector.cs:130`).
The original `catch {}` swallowed every Win32 error silently. If the call
started failing every poll, the screen-watcher was effectively dead and
the operator had no signal. Now logs throttled (once per 30s) so the
Output panel isn't spammed but the failure is still visible.

## Files

Changed: `aria/scripts/AriaMotionClient.cs`, `aria/scripts/HealthMonitor.cs`,
`aria/scripts/LLMBridge.cs`, `aria/scripts/MotionLibraryMirror.cs`,
`aria/scripts/WindowDetector.cs`.

## Did NOT regress

- Build: `dotnet build AriaAssistant.csproj` → 0 warnings, 0 errors.
- The fall-back behaviour is unchanged. The only difference is that when
  a fall-back is hit, you now see why in the Godot Output panel.
- No new dependencies, no new files in the runtime tree, no Godot
  scene edits. `Main.tscn` was not touched.

## Verify (no first-launch check needed; the fixes are silent until hit)

These are all "log when something goes wrong" changes. The happy path
is identical. To exercise the new logs:

- **AriaMotionClient**: queue a motion that the server can't generate
  (e.g. an invalid prompt). The MotionFailed signal will now carry the
  original prompt text — verify in your signal handler.
- **HealthMonitor / LLMBridge / MotionLibraryMirror**: rename or
  permission-deny the configured path, restart, watch the Output
  panel for the new breadcrumb.
- **WindowDetector**: kill the foreground-window API in a debugger
  (or revoke `SeDebugPrivilege`), watch the throttled error log
  appear in the Output panel once per 30s.

---

# Aria — Change Log, 2026-06-16 (install scripts + ingester robustness)

This pass makes Aria ship-ready for a new user: 3 install scripts (one per
deployment shape), better ingester duplicate handling, and a small README
update pointing new users at the new flow.

## Install scripts

Three new top-level PowerShell scripts replace the previous "follow the
README, install everything by hand" flow:

| Script | Use when | Installs |
|--------|----------|----------|
| `install_single_pc.ps1` | All of Aria on one machine (RTX 4080 Super / 3090 / similar) | .NET 8 SDK, Python 3.11+ venv, Coqui TTS + Jessica, Godot 4.6.3 Mono, LM Studio, FFmpeg 8 shared, all deps, firewall rules, smoke test |
| `install_pc1_main.ps1` | PC 1 (main desktop) in a two-PC setup | .NET 8 SDK, Python 3.11+ venv, client-side deps only, Godot 4.6.3 Mono, writes `.env` with PC 2 URLs, smoke-tests PC 2 reachability |
| `install_pc2_ai.ps1` | PC 2 (AI server) in a two-PC setup | Python 3.11+ venv, Coqui TTS + Jessica, optional FloodDiffusion model dir, LM Studio, FFmpeg 8 shared, firewall rules INBOUND, writes `.env` with server config |

All three are **idempotent** — re-running skips what's already installed and
re-verifies what was already set up. The only steps that ASK before doing
anything are the external installers (winget / choco / browser download).
A multi-GB install (Godot, Coqui) NEVER auto-runs without a `[Y/n]` prompt
unless `-ConfirmAll` is passed.

Each script:
- Pre-flight: admin elevation, PowerShell 5.1+ check, 25 GB / 5 GB / 40 GB free-disk check (per script), internet check, project-root sanity.
- Confirms each external install before running.
- Creates the project-local `.venv` if missing.
- Installs `requirements.txt` + `motion_requirements.txt` + Aria-specific deps (`coqui-tts[codec]==0.27.5`, `transformers>=4.57,<4.70`, `streamlit`).
- Verifies every core dep imports before declaring success.
- Adds the right Windows firewall rule (AriaChatServer 8767 inbound on PC 1; TTS 5003, motion 8766, dashboard 8501, AstroServer 8765, LM Studio 1010 inbound on PC 2).
- Smoke-tests: PC 1 pings PC 2's three URLs; PC 2 runs a Python import probe including TTS.

### Order of operations (two-PC)

1. **PC 2 first**: `.\install_pc2_ai.ps1` (installs server stack, opens inbound firewall).
2. **PC 2 daily**: `.\start_aria_server.ps1` (starts LM Studio, Astro server, TTS, motion, dashboard).
3. **PC 1 install**: `.\install_pc1_main.ps1` with the right `-AriaServerUrl`, `-LmStudioUrl`, `-TtsServerUrl` (defaults assume PC 2 is at `192.168.68.88`).
4. **PC 1 daily**: `.\start_aria.ps1` (starts Godot, Astro client, TTS client).

### One-PC

1. `.\install_single_pc.ps1` (installs everything).
2. `.\start_aria.ps1`.

## Ingester duplicate-name handling

The user drops multiple Mixamo files with the same stem into
`aria/ani/incoming/` thinking they're different versions of the same anim
(e.g. `wave.fbx` + `wave (1).fbx`). Previously the second one OVERWROTE
the first in the library (because `derive_name()` strips both
` (1)`-style suffixes and the second had the same `name` field). Now
`build_library()` in `ingest_motion_library.py` detects collisions and
suffixes the second+ occurrence with `_v2`, `_v3`, etc. The original
Mixamo filename is preserved in the entry's new `originalName` field
for debugging.

## Did NOT regress

- Build: `dotnet build AriaAssistant.csproj` → still 0 warnings, 0 errors.
- The 38 FBX files already in `aria/ani/` still map to 38 library entries
  (the collision handler is dormant until two files share a stem).
- All previous install / start behaviour preserved. The new scripts are
  additive — `start_aria.ps1` and `start_aria_server.ps1` are unchanged.

---

# Aria — Change Log, 2026-06-16 (FloodDiffusion install + Windows shim)

The user reported trouble installing `FloodDiffusion` (the text-to-motion
diffusion model the motion server uses for `request_motion`). End-to-end
install path now works on this Windows + CUDA box. Three findings worth
recording for the next time someone hits this.

## Findings (the three traps)

**1. Upstream `LDFModel.from_pretrained` has a broken `trust_remote_code` check.**
The custom code at `hf_pipeline.py:110` does:
```python
if not kwargs.get('trust_remote_code', False):
    raise ValueError("Loading this model requires trust_remote_code=True.")
```
But `AutoModel.from_pretrained` strips `trust_remote_code` from the kwargs
before delegating to the classmethod, so the check always fails — even when
the user passes `trust_remote_code=True` correctly. This is a bug in the
upstream `ShandaAI/FloodDiffusion` hub repo. The fix is to bypass
`AutoModel` and import `LDFModel` directly from the local snapshot.

**2. `wan_model.py` calls `flash_attention(...)` directly, which asserts
`flash_attn` is installed.** No official Windows wheel for `flash_attn`;
building from source is impractical. The high-level `attention(...)` function
in the same file has an SDPA fallback (`torch.nn.functional.scaled_dot_product_attention`),
but it's never reached because the call site uses the low-level `flash_attention`.
Fix: monkey-patch `wan_model.flash_attention` to call `attention(...)` instead.
This is a no-op on Linux where `flash_attn` is installed (it just adds a
function-pointer swap that re-routes to the same code path); on Windows it
forces the SDPA fallback.

**3. SDPA fallback defaults to BF16 output, but the model's linear layers
are FP32.** A naive `attention()` substitution gives "mat1 and mat2 must have
the same dtype" because the BF16 attention output hits an FP32
`nn.Linear`. Fix: wrap the substitution in a 1-liner that forces
`dtype=torch.float32` on every call:
```python
def fp32_attention(*args, **kwargs):
    kwargs["dtype"] = torch.float32
    return attn.attention(*args, **kwargs)
wm.flash_attention = fp32_attention
```
Slower than BF16+FlashAttention by ~2-3x per inference step, but the model
itself is the bottleneck, not attention.

## What shipped

- `astro_assistant/_flood_loader.py` — public `load_FloodDiffusion(model_id)`
  and `is_FloodDiffusion_available()`. Resolves the local HF snapshot path,
  adds the snapshot's `ldf_models/`, `ldf_deps/`, `ldf_utils/` subdirs to
  `sys.path` so the dynamic imports inside `_load_models()` find them, and
  applies both shims (2) and (3) before instantiating. Self-test at the
  bottom: `python -m astro_assistant._flood_loader`.

- `astro_assistant/motion_server.py` — the broken
  `AutoModel.from_pretrained(self.model_id, trust_remote_code=True)` line in
  `_ensure_model` is now replaced with
  `load_FloodDiffusion(self.model_id)` (with a fallback direct import so
  the server still works when run as `python motion_server.py` from inside
  `astro_assistant/`, where the `astro_assistant` package isn't on `sys.path`).

- `install_pc2_ai.ps1` — the `Step 5` FloodDiffusion section now also
  (a) verifies `_flood_loader.py` is present, (b) prompts to download
  `ShandaAI/FloodDiffusion` weights via `huggingface-cli` if the HF cache
  is empty, (c) creates the empty `models/FloodDiffusion/` directory the
  ingester expects for its `--model` flag.

## Verified on this box (2026-06-17)

- `.venv` already had `torch 2.7.1+cu118`, `transformers`, `huggingface_hub`,
  `numpy`. RTX 4080 SUPER with 17.2 GB VRAM, CUDA 11.8 driver.
- HF cache already had `ShandaAI/FloodDiffusion` (~24 GB on disk).
- `python -m astro_assistant._flood_loader` self-test: model loads in
  ~55s, single 60-frame inference in ~17s (FP32 + SDPA).
- `motion_server.py --port 8770 --preload` boots in ~50s, `/healthz` returns
  `{"ok": true, "model_loaded": true}`. Real `/motion` request
  (`A person standing and breathing gently`, 30 frames) enqueued, processed
  in 6.2s, `/motion/get` returned 48,949 bytes of valid motion data
  (30 frames × 21 SMPL bones × quaternion rotations).
- `dotnet build AriaAssistant.csproj` → 0 warnings, 0 errors (untouched).

## Known issues / footguns for the next installer

- **Port 8766 is a zombie.** A `motion_server.py` process from
  2026-06-16 (pid 48384) is still bound to the default port. `Stop-Process`
  fails with "Access is denied" — likely running under a different user
  context. Use `Get-NetTCPConnection -LocalPort 8766` to confirm, then
  either reboot or launch the new server with `--port 8770` (or any other
  free port). Consider changing the default port in
  `motion_server.py` from 8766 to something less likely to be squatted on.

- **`/motion/status` returns "not found" for ids that DO exist**
  (pre-existing bug — `status()` reads from `_all` but the lookup key path
  is broken for ids returned by `/motion` POST). `/motion/get?id=<id>` works
  correctly and returns the full motion. The Godot client uses `/motion/get`,
  not `/motion/status`, so this is a debug-only inconvenience.

- **The .bat launcher (or `Start-Process cmd /c`) may end up running
  `C:\Program Files\Python312\python.exe` instead of the .venv python** on
  some Windows configs (PATH ordering). The .bat should use the fully
  qualified `& "$ProjectDir\.venv\Scripts\python.exe" -u ...` path, NOT a
  bare `python`, to avoid this. Symptom: model loads, server listens, but
  HTTP requests fail with `ModuleNotFoundError: No module named 'torch'`
  in the wrong Python's import.

- **`python -u` is required** when running the server via `cmd > log 2>&1`.
  Without `-u`, the ENQUEUE / START / DONE log lines for /motion
  requests can be buffered for minutes. The new launchers use `-u`;
  if you write a new launcher, include it.

## Fixes (round 2 — applied 2026-06-17)

**1. Killed the zombie `motion_server.py` on port 8766.** The process
(pid 48384, started 2026-06-16 10:23) was holding port 8766 and
blocking fresh launches. `Stop-Process -Force` worked once the
user gave the agent admin. The new server now binds the default
port 8766 cleanly. If you ever see the same symptom (port 8766 in
use by a python you don't recognize), check
`Get-NetTCPConnection -LocalPort 8766` and kill the owning pid
manually.

**2. `GET /motion/status?id=<id>` now works.** The endpoint was
only registered for `POST` (the Godot client's contract is POST
with `{"ids":[...]}` in the body). A bare `GET /motion/status?id=xxx`
from a browser or `Invoke-WebRequest` fell through to the
`not found` 404. Added a GET branch in `do_GET` that parses the
query string, normalizes the `id` param to a list, and dispatches
to the existing `_handle_status({"ids": ids})`. Both the POST
(Godot) and GET (manual debugging) paths now work. Verified:
- POST `{"ids":["fc05f30efdd0","nonexistent_id"]}` returns
  `{"results":[{...}]}` for the existing id, silently drops the
  missing one (pre-existing behaviour of `status()`).
- GET `?id=fc05f30efdd0` returns the same result.

**3. End-to-end on port 8766 with a real motion request.** The
request `A person standing and breathing gently` (30 frames)
enqueued at 10:40, status polled as `running` then `done` (5.8s
elapsed), `/motion/get` returned 48,949 bytes of valid
`bones[21] x rotations[30] x quaternion[4]` motion data.


