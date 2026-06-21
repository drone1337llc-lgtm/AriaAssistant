# Aria Bridge + Persistence — Operations & Learnings

_Last updated: 2026-06-19. Covers the `bridge` mesh, how Aria's cross-PC traffic
rides it, PC2 provisioning, persistence, and every gotcha hit while wiring it up._

---

## 1. The bridge (what it is)

`C:\Users\Tench\Documents\bridge` is a small Go program that maintains a
**persistent encrypted mesh** between three machines and **tunnels TCP ports**
across it. It replaced a flaky earlier build that "disconnected a lot."

### Nodes
| Node | IP | Role |
|------|----|----|
| PC1  | 192.168.68.15 | Aria desktop (Godot, tray, chat) |
| PC2  | 192.168.68.88 | AI box (LM Studio, brain, TTS, motion, ChromaDB) |
| TrueNAS (DeepSpace) | 192.168.68.64 | storage; mesh member only |

### Mesh design
- **Full mesh**: every node keeps one live link to every other node.
- **Dial rule**: a node only *dials* peers with a higher IP and *accepts*
  inbound from lower IPs, so each pair forms exactly one link (no duplicates,
  no flapping). A deterministic "canonical" tie-break handles simultaneous
  dials. So `.88` (highest) only ever *accepts*, which is why its **inbound
  8443 must be reachable** (see firewall).
- Auto-reconnects with backoff; a node can be offline for hours and rejoin.

### The bug that was fixed
The crashes/disconnects were **unsynchronized concurrent writes** to one
websocket (`gorilla/websocket` forbids it). Every write now goes through a
per-connection mutex. Regression + tunnel tests live in
`bridge/internal/transport/*_test.go`.

### Config
Per Windows node: `C:\Users\<user>\.bridge\config.yaml`.
TrueNAS: `/mnt/DeepSpace/apps/bridge/config.yaml`.

Key fields:
- `peers:` — the same list of all three IPs on every node (each auto-detects self).
- `tunnels:` — **PC1 only** (see below).
- `port: 8443` (mesh), `web_gui_port: 8080`.

> The bridge **rewrites config.yaml** on every start (viper re-serializes it),
> which **strips comments** and reorders keys. That's cosmetic — values persist.

### Tunnels (PC1 only)
PC1 exposes PC2's services on localhost; the bridge forwards them over the mesh.
**`target` is dialed by the bridge ON PC2, so it must be `127.0.0.1`** (some
services, e.g. the TTS server, bind loopback-only and are NOT reachable at
`192.168.68.88`).

| localhost (PC1) | → peer | → target (on PC2) | service |
|---|---|---|---|
| 127.0.0.1:1010 | .88 | 127.0.0.1:1010 | LM Studio |
| 127.0.0.1:8766 | .88 | 127.0.0.1:8766 | motion server |
| 127.0.0.1:8765 | .88 | 127.0.0.1:8765 | astro server |
| 127.0.0.1:8770 | .88 | 127.0.0.1:8770 | brain (FastAPI) |
| 127.0.0.1:5003 | .88 | 127.0.0.1:5003 | TTS (Jessica) |

PC2 and TrueNAS have **no tunnels** (services are already local on PC2).

### Web GUI
Each node serves a GUI at `http://<node>:8080` (bound to all interfaces). It now
shows a **node strip** (all 3 nodes, green/red, live) and a **peer selector** for
Remote file browsing. The remote-FS browse exposes the filesystem to the LAN —
fine on a trusted home network.

### Operating the bridge
- Installed as a Windows service `bridge-daemon` (auto-start) on PC1/PC2.
  - `dist\bridge.exe -install-service` / `-start-service` / `-stop-service` / `-uninstall-service`
  - The installed service pins `--config C:\Users\<user>\.bridge\config.yaml`
    (a service runs as LocalSystem with a different home dir).
- TrueNAS: launched by an Init/Shutdown **Post Init** command:
  `/mnt/DeepSpace/apps/bridge/bridge -config /mnt/DeepSpace/apps/bridge/config.yaml >> .../bridge.log 2>&1 &`
- **Health check from PC1:** `.\scripts\bridge-health.ps1` (add `-Watch` for a
  live monitor). Shows mesh node status + each tunnel UP/DOWN.

### Building the bridge
On PC1: `& 'C:\Program Files\Go\bin\go.exe' build -o dist\bridge.exe ./cmd/bridge`
Linux/TrueNAS: `GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o dist\bridge-linux-amd64 ./cmd/bridge`

---

## 2. Aria over the bridge

PC1's Aria clients were repointed from `192.168.68.88:<port>` to
`127.0.0.1:<port>` so their traffic rides the resilient tunnels:

- `aria/scripts/LLMBridge.cs` → `LMStudioUrl` = `http://127.0.0.1:1010/v1/chat/completions`
- `aria/scripts/AriaMotionClient.cs` + `Main.cs` → `http://127.0.0.1:8766/motion`
- `aria/scripts/TTSBridge.cs` → `http://127.0.0.1:5003/tts` (was a stale `:5002/api/tts`)
- `scripts/start-aria-stack.ps1` → tray/chat env `ARIA_BRAIN_HOST=127.0.0.1`, `TTS_URL=http://127.0.0.1:5003/tts`
- `install_pc1_main.ps1` → default URLs now `127.0.0.1`

No `.tscn` overrides these, so the `[Export]` defaults in the `.cs` files are
what's used. Relaunch Godot so it rebuilds the C#.

### Model config (LM Studio)
Changed the role models (verified the IDs exist in LM Studio's `/v1/models`):
- **coder** = `nvidia_nvidia-nemotron-nano-9b-v2`
- **vision** = `qwen/qwen2.5-vl-7b`

Set in `brain/.env`, `brain/.env.example`, and `brain/src/aria_brain/config.py`
(default backstop). **The brain runs on PC2 and reads PC2's `brain/.env`**, so
copy `.env` to PC2 after changing models:
`scp brain\.env tench@192.168.68.88:".../brain/.env"`.

---

## 3. PC2 provisioning (what it takes)

Prereqs, in order:
1. **SSH key auth** PC1→PC2 (see gotchas — the admin-key trap).
2. **C++ Build Tools** on PC2 (native deps: chroma-hnswlib, etc.).
3. **Python 3.12** (no 3.13/3.14 wheels for the stack).

Then `.\scripts\setup-pc2-services.ps1` (run from PC1) sets up:
- `brain/.venv` → `pip install -e .` (brain package; needs the compiler for hnswlib)
- `watchdog/.venv`
- `Coqui-TTS-XTTS-v2-/.venv` → **`pip install coqui-tts` then `transformers==4.57.*`**
  (the in-project Coqui folder is a stub with no `setup.py`; the library comes
  from PyPI, not editable source)

Separate, run **on PC2 elevated**:
- `brain\setup_chromadb_pc2.ps1` → ChromaDB + its own SYSTEM auto-start task (port 8000)

Motion (optional): `cd motion_lib && py -3.12 -m venv .venv && .venv\Scripts\python.exe -m pip install -r motion_requirements.txt`

### Coqui location
Coqui moved **off the USB `D:` drive into the project** on PC2:
`C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\Coqui-TTS-XTTS-v2-`.
All scripts now derive it from the project root (`$Root\Coqui-TTS-XTTS-v2-`).
PC1's `D:\...\Coqui-TTS-XTTS-v2-` remains the **model source** for the scp copy.

---

## 4. Persistence ("PC on => Aria ready")

| Layer | Mechanism |
|---|---|
| Bridge (all nodes) | Windows service (PC1/PC2), TrueNAS Post-Init |
| ChromaDB (PC2) | own SYSTEM Scheduled Task, `setup_chromadb_pc2.ps1` |
| brain / TTS / motion (PC2) | **supervisor** `scripts\aria-pc2-supervisor.ps1`, run by Scheduled Task `AriaPC2Backend` (logon, user session for GPU) |
| Front-end (PC1) | launched on demand (Godot / chat / tray) |

Enable the PC2 backend supervisor (run **on PC2, elevated**, after syncing scripts):
```
.\scripts\install-aria-pc2-autostart.ps1            # add -WithTelegram -WithWatchdog if wanted
Start-ScheduledTask -TaskName AriaPC2Backend
```
The supervisor starts brain/TTS/motion locally (no SSH), restarts any that die,
skips services whose venv doesn't exist yet, and logs to `logs\pc2\supervisor.log`.

For fully hands-off boot, enable **autologon** on PC2 (`netplwiz`) so the logon
trigger fires after a reboot.

---

## 5. Gotchas learned (read before touching this again)

**Bridge / network**
- Concurrent websocket writes crash gorilla — always serialize per connection.
- Each Windows node needs **inbound 8443 (mesh) + 8080 (GUI)** allowed in the
  firewall. Per-service ports (1010/5003/8766/8770/8000) do **NOT** need opening —
  they're reached via the bridge over PC2's own loopback.
- Tunnel `target` must be `127.0.0.1` (dialed locally on the peer).
- Windows service failing to start with **1053** = the binary didn't implement
  the Service Control Manager handshake (fixed) and/or wrong `--config` path.

**SSH (PC1→PC2)**
- `setup-pc2-services.ps1` uses `BatchMode=yes` (key only). If you've been
  *typing a password*, key auth isn't really set up.
- On Windows, if the PC2 user is an **administrator**, sshd ignores
  `~/.ssh/authorized_keys` and only reads
  `C:\ProgramData\ssh\administrators_authorized_keys` (and the file must have a
  strict ACL: `icacls ... /inheritance:r /grant "Administrators:F" "SYSTEM:F"`).
  Writing it needs an **elevated** shell on PC2.
- Nested **PowerShell → ssh → cmd → python** quoting is brutal. Don't inline
  `python -c "..."` with commas/quotes/`<`/`>`. Use a **`.py` file**
  (`scripts/pc2_check.py`), **exact pins** (`pkg==1.2.*`, not `>=x,<y`), and for
  remote dirs the running process can lock files (kill it before recreating a venv).

**Python deps (PC2)**
- `chroma-hnswlib` / many ML deps compile from source → need **MSVC Build Tools**.
- The in-project `Coqui-TTS-XTTS-v2-` is a **stub** (no `setup.py`); install the
  TTS library from PyPI: **`coqui-tts`**.
- **transformers pin is fussy**: `coqui-tts 0.27.x` needs `transformers>=4.57`,
  but transformers **5.x removed `isin_mps_friendly`** that XTTS imports. The fix
  is the overlap: **`transformers==4.57.*`**.
- `coqui-tts` can pull a **CPU torch** over your CUDA build — always verify
  `torch.cuda.is_available()` after (use `scripts/pc2_check.py`).
- `chromadb >=0.6` **dropped the `[server]` extra** — install plain `chromadb`.
- Possible mismatch: the brain pins `chromadb<0.6` (client 0.5.x) while the
  server is 0.6.3. If `/health` stays `backend: local` after a brain restart,
  align the versions. Local fallback works regardless.
- **Motion:** `motion_requirements.txt` is `torch>=2.1` with no CUDA index, so a
  fresh install gets **CPU torch**. For GPU, reinstall `torch` from the cu121
  index in `motion_lib\.venv`. But FloodDiffusion's default model wants ~16 GB
  VRAM and shares the 3090 with LM Studio — co-running can OOM; use
  `--model ShandaAI/FloodDiffusionTiny`, run motion on demand, or leave it on CPU.
  My `pc2_check.py` always tests `import TTS`, so `TTS_IMPORT: FAIL` in the
  *motion* venv is expected and meaningless.

---

## 5a. Voice is client-side (don't chase `audio_url`)

`POST /message` returns `audio_url: null` unless you pass `speak: true` — and even
then, the brain runs on PC2 so its `audio_url` is a **PC2 filesystem path**,
useless from PC1. By design, the PC1 clients (`chat_window`, Godot) **ignore
`audio_url`** and call the TTS server **directly** at the `:5003` tunnel, then
play the returned WAV locally (`chat_window._speak_direct`). So:
- LLM/memory working = a text `reply` comes back from `/message`.
- Voice working = `POST http://127.0.0.1:5003/tts {"text":"..."}` returns a WAV
  (that's what the clients do). A raw curl/Invoke-WebRequest never makes sound;
  only the client plays it.

## 6. Quick reference — verify the whole stack

From PC1:
```
.\scripts\bridge-health.ps1                 # mesh + tunnels
curl.exe http://127.0.0.1:1010/v1/models    # LM Studio via tunnel
curl.exe http://127.0.0.1:8770/health       # brain via tunnel (shows memory backend, llm_url)
# end-to-end talk:
$b = @{ text = "hey Aria" } | ConvertTo-Json
(Invoke-WebRequest -UseBasicParsing -Method POST http://127.0.0.1:8770/message -Body $b -ContentType 'application/json').Content
```
On PC2:
```
powershell -File .\scripts\aria-pc2-supervisor.ps1 -Status    # port snapshot
netstat -ano | findstr :8000                                  # chromadb
```
