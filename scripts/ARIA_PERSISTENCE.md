# Aria — make the backend persistent + bring up the full stack

Goal: as long as the PCs are on, the Aria **backend** (PC 2) is running and ready,
and you launch the **front-end** (Godot pet / chat) on PC 1 whenever you want her.

The **bridge** comms layer is already done and persistent:
- PC 1: `bridge-daemon` Windows service (auto-start) — verified Running.
- PC 2: `bridge-daemon` Windows service (auto-start).
- TrueNAS (.64): bridge via Init/Shutdown Post-Init script.

What remains is provisioning PC 2's Python services and making them auto-start.
The C++ Build Tools are now installed on PC 2, so the installs that failed
before will succeed.

---

## 1. Provision the remaining PC 2 services

Run from **PC 1** (SSH to PC 2 works from your interactive shell). Each is a
one-time setup.

**Brain** — already done (you installed it manually). Nothing to do.

**TTS + watchdog venvs** (heavy: pulls CUDA torch + Coqui TTS, ~10–20 min):
```powershell
.\scripts\setup-pc2-services.ps1
```
Then copy the ~7 GB Jessica voice model **once** (the script prints this exact line):
```powershell
scp -r "D:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\run\training" "tench@192.168.68.88:C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\Coqui-TTS-XTTS-v2-\run\"
```

**ChromaDB** — run **on PC 2** (RDP or JetKVM `http://192.168.68.122`), elevated.
It installs ChromaDB and registers its own SYSTEM auto-start task (port 8000):
```powershell
.\brain\setup_chromadb_pc2.ps1
```

**Motion (optional)** — provision its venv on PC 2:
```powershell
ssh tench@192.168.68.88 "cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\motion_lib && py -3.12 -m venv .venv && .venv\Scripts\python.exe -m pip install -r motion_requirements.txt"
```

> Sanity-check a venv any time:
> `ssh tench@192.168.68.88 "<path>\.venv\Scripts\python.exe -c \"print('ok')\""`

---

## 2. Make the PC 2 backend persistent

These run **on PC 2** (the supervisor must run natively there — not over SSH —
so the services survive your SSH session closing). Make sure the repo is synced
to PC 2 first (`scripts\sync-to-pc2.ps1`) so `aria-pc2-supervisor.ps1` is present.

On **PC 2**, in an **elevated** PowerShell:
```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
.\scripts\install-aria-pc2-autostart.ps1            # add -WithTelegram -WithWatchdog if you want those too
Start-ScheduledTask -TaskName AriaPC2Backend        # start now, don't wait for re-logon
```

This registers a Scheduled Task that runs `aria-pc2-supervisor.ps1` **at logon**,
in your user session (so TTS/motion get the GPU), and restarts it if it ever
exits. The supervisor starts brain / TTS / motion and **restarts any that die**.
ChromaDB is left to its own SYSTEM task from step 1.

Watch it work:
```powershell
Get-Content C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\logs\pc2\supervisor.log -Tail 30 -Wait
powershell -File .\scripts\aria-pc2-supervisor.ps1 -Status     # quick port snapshot
```

**Hands-off boot** (optional): so the logon trigger fires after a reboot with no
password, enable autologon on PC 2 — run `netplwiz`, uncheck "Users must enter a
user name and password." (LM Studio is a GUI app, so PC 2 needs to be logged in
anyway for the LLM.)

---

## 3. Verify the whole stack over the bridge (from PC 1)

```powershell
.\scripts\bridge-health.ps1
```
You want all three mesh nodes connected and every tunnel **UP**:
`LM Studio`, `Brain`, `TTS`, `Motion` (and `Astro` if you run the astro server).
Leave `-Watch` running while you use Aria to confirm zero flapping.

End-to-end smoke test (talks to Aria through the tunnels):
```powershell
$b = @{ text = "hey Aria, you up?" } | ConvertTo-Json
(Invoke-WebRequest -UseBasicParsing -Method POST http://127.0.0.1:8770/message -Body $b -ContentType 'application/json' -TimeoutSec 90).Content
```

---

## 4. Run the front-end on PC 1 (when needed)

The PC 2 backend stays up on its own now, so on PC 1 you only launch the display
pieces. The bridge service is already running, so the tunnels are live.

```powershell
.\start_aria.ps1 -NoBrain -NoTts -NoMotion -NoDashboard   # just Godot + (tray/chat)
```
or launch Godot / the chat window directly. They're pointed at `127.0.0.1`, so
they reach PC 2 through the bridge tunnels automatically.

---

## Notes / caveats

- **What's verified vs. not:** the bridge, mesh, tunnels, and the brain path are
  tested end-to-end (Aria replied through the tunnel). Steps 1–2 run on PC 2,
  which I can't reach from here, so confirm each with the status/health commands
  above and paste anything that errors.
- **TTS is the heavy one** — needs a working CUDA torch and the 7 GB model; give
  its first start a minute (the supervisor won't kill it for being slow to bind).
- `start-aria-stack.ps1 start` still works, but its remote-launch over SSH is no
  longer the mechanism keeping PC 2 alive — the supervisor is. The two coexist
  (the stack script will see services already running and skip them).
