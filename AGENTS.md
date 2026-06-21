# Aria Project — Agent Notes

Conventions and gotchas discovered while working on this project.
Every agent (including the Aria infra worker and the coder) should read
this on every task.

## Project structure (verified 2026-06-15)

- Project root: this directory. Two sub-projects live inside:
  - `astro_assistant/` — the Python AI stack (motion server, FloodDiffusion, TTS, dashboards)
  - `aria/` — the Godot 4 client (Aria.glb, scenes/, scripts/, ani/, addons/)
- **Animation folder is `aria/ani/`, NOT `ani/` at the project root.** Specs and
  inherited code that reference `<project>/ani/` are stale — the real path is
  `<project>/aria/ani/`. There is no `ani/` at the project root.
- `astro_assistant/models/` does NOT contain a `FloodDiffusion/` subdir yet.
  The motion server's `--model` default points there; it'll be created when
  the model is downloaded.
- `astro_assistant/characters/` is reserved for character assets; not used by
  the motion server.

## Animation ingestion (FBX)

- All Aria animations are **Mixamo FBX 7.4 binary** with `J_Bip_*` bone names
  (e.g. `J_Bip_C_Hips`, `J_Bip_L_Foot`). Bone set detection: any `J_Bip_*`
  prefix → `boneSet: "mixamo"`.
- **Do NOT use `assimp` or `pyassimp` to parse these files.** The free
  `assimp` build can't handle Mixamo FBX 7.4 (empty error message, fails
  silently). `pyassimp` ships without a bundled DLL on Windows. The working
  approach is a hand-rolled FBX 7.4 binary scanner — see
  `astro_assistant/ingest_motion_library.py` for a complete reference
  implementation.
- The Godot `.import` sidecar files next to each `.fbx` (e.g.
  `idle.fbx.import`) contain `animation/fps` (30 for everything in this
  project) and the Godot `uid`. They do NOT contain duration, animation
  count, bone set, root motion, or contact frames — those have to come
  from the FBX binary itself.
- Idempotency pattern for generated manifests: read the existing JSON on
  re-run and preserve the `generatedAt` field, so byte-identical content
  produces a stable SHA-256 across runs.

## Motion server / FloodDiffusion context

- `astro_assistant/motion_library.json` is the source of truth for what
  animations are available. The motion server feeds this into FloodDiffusion
  as context. The Godot client mirrors it (per the `motion_library.json`
  spec from 2026-06-15).
- `astro_assistant/motion_library.py` exposes `load_library(path)`,
  `hash_library(path)`, `build_context_snippet(library, max_chars=4000)` for
  the motion server to embed the manifest in its prompt.
- The motion server uses SMPL 22-joint → Mixamo bone names mapping
  (`SMPL_TO_MIXAMO` dict in `motion_server.py`). The diffusion model emits
  SMPL-style output; the client re-targets to Mixamo.

## Conventions (general)

- Python venv: `astro_assistant/.venv/Scripts/python.exe` (Windows). Already
  has torch, trimesh, numpy, plus we install `assimp_py` and `pyassimp` as
  candidates — neither works for Mixamo FBX, so don't try them again.
- PowerShell is the default shell on PC 1 (user's main dev box). Use
  PowerShell syntax (`Get-ChildItem`, `Select-String`), not bash heredocs.
  Heredoc strings (`@'...'@`) don't round-trip through the bash tool well.
- For destructive file ops, use the `trash` MCP tool, NOT `Remove-Item`
  (the `bash` tool blocks `Remove-Item` for safety; `mavis mcp call trash
  trash` is the approved path).

## Bridge + cross-PC comms (verified 2026-06-19)

PC1↔PC2↔TrueNAS run a persistent mesh (`C:\Users\Tench\Documents\bridge`); Aria's
PC1 clients hit `127.0.0.1` ports that get tunneled to PC2. Full guide:
`docs/BRIDGE_AND_PERSISTENCE.md`. Gotchas that bite:

- **SSH PC1→PC2 key auth:** PC2's user is an admin, so sshd reads
  `C:\ProgramData\ssh\administrators_authorized_keys` (strict ACL), NOT
  `~/.ssh/authorized_keys`. `setup-pc2-services.ps1` uses `BatchMode=yes` (key
  only) — if you've been typing a password, key auth isn't actually set up.
- **Quoting:** PowerShell→ssh→cmd→python mangles inline `python -c "..."` (commas,
  quotes, and `<`/`>` especially — `<` becomes cmd redirection). Use a `.py` file
  (`scripts/pc2_check.py`) and exact pins like `pkg==1.2.*` (never `>=x,<y`).
- **TTS:** the in-project `Coqui-TTS-XTTS-v2-` is a stub (no setup.py) — install
  `coqui-tts` from PyPI, then pin `transformers==4.57.*` (coqui-tts needs ≥4.57;
  transformers 5.x dropped `isin_mps_friendly` that XTTS imports). Verify CUDA
  torch survived (`scripts/pc2_check.py`). Coqui lives in the project on C: now,
  not the USB D: drive.
- **ChromaDB:** `chromadb>=0.6` dropped the `[server]` extra — install plain
  `chromadb`.
- **Native deps** (chroma-hnswlib, etc.) need MSVC Build Tools on PC2; Python 3.12.
- **Persistence:** never rely on `ssh "... start /b ..."` to keep a service up
  (dies on disconnect). PC2 services are kept alive by
  `scripts/aria-pc2-supervisor.ps1` via the `AriaPC2Backend` scheduled task.
- **Firewall:** only 8443 (mesh) + 8080 (GUI) need opening per Windows node;
  service ports are reached via the bridge over PC2's loopback.
