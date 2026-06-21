# Aria Assistant — PC 1 (the desktop where Aria lives)

This is the machine you actually work on. Aria is a transparent,
borderless character that walks around on it.

> **Bridge + persistence (2026-06):** Aria's clients here now point at
> **`127.0.0.1`** (LM Studio :1010, brain :8770, TTS :5003, motion :8766), and
> the `bridge` service tunnels those to PC2 over the mesh. Check the link any
> time with `.\scripts\bridge-health.ps1`. Details:
> **[docs/BRIDGE_AND_PERSISTENCE.md](docs/BRIDGE_AND_PERSISTENCE.md)**.

PC 1 runs:
- The Godot project (`aria/`) — the Aria character + animation + window detection
- The Astro client (`astro_assistant/client.py`) — bridges Godot to PC 2
- The TTS client — fetches Jessica's voice audio from PC 2

It does NOT run LM Studio, the AI server, the motion server, ChromaDB, or
the Streamlit dashboard. All of those live on PC 2.

## Quick install (recommended)

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
.\install_pc1_main.ps1 -AriaServerUrl http://192.168.68.88:8765 -LmStudioUrl http://192.168.68.88:1010/v1 -TtsServerUrl http://192.168.68.88:5003
```

Replace `192.168.68.88` with PC 2's actual LAN IP if it's not the default.
The install script handles .NET 8 SDK, Python 3.11+ venv, client-side
deps, Godot 4.6.3 Mono, the chat-server firewall rule, writes `.env` with
PC 2's URLs, and smoke-tests PC 2 reachability. Asks before each external
install; idempotent.

The rest of this README is the **detailed manual walkthrough** for users
who want to install by hand or troubleshoot.

```
                PC 1
   ┌─────────────────────────────┐
   │                             │
   │   Aria (Godot 4.6.3 Mono)   │
   │       ↕                     │
   │   astro_assistant/client.py │
   │       ↓  WebSocket :8765    │
   │       ↓  HTTP :1010         │
   │       ↓  HTTP TTS           │
   │                             │
   └─────────────────────────────┘
            ║  gigabit Ethernet
            ║
            ▽  PC 2 (the AI server)
```

See **[README_PC2.md](README_PC2.md)** for the matching setup on PC 2.
**Set up PC 2 FIRST** — when you launch Aria here, the client has
something to talk to.

---

## 1. Install system prerequisites (PC 1)

| What | Where | Notes |
|------|-------|-------|
| Windows 10/11 | microsoft.com | Fully updated, rebooted |
| Python 3.10+ (3.12 recommended) | python.org | **Check "Add python.exe to PATH" during install** |
| Git for Windows | git-scm.com | Optional — only if cloning via git |
| **Godot 4.6.3 (Mono / .NET build)** | godotengine.org/download | Pick the **.NET (Mono)** build, NOT the regular one |
| .NET 8 SDK | dotnet.microsoft.com/download/dotnet/8.0 | Required by Godot Mono |
| Visual Studio Build Tools | visualstudio.microsoft.com/visual-cpp-build-tools | Check "Desktop development with C++" — needed for some Python wheels |

PC 1 does **NOT** need:
- LM Studio
- Tesseract (used by Astro for OCR — lives on PC 2)
- Coqui TTS server (also on PC 2)
- The Astro server (`server.py`)

---

## 2. Place the project

Pick a path. This guide assumes `C:\Users\Tench\Documents\AriaAssistantApp\`.
**Use this exact path** unless you want to edit every `cd` command below.

If cloning:
```powershell
cd C:\Users\Tench\Documents
git clone <your-repo-url> AriaAssistantApp
cd AriaAssistantApp
```

If from a ZIP, extract to `C:\Users\Tench\Documents\AriaAssistantApp\`.

---

## 3. Create the Python virtual environment

**This MUST happen before installing any Python packages.** A venv
keeps this project's packages isolated from your system Python and
from other projects. Skipping it is the #1 cause of "ModuleNotFound"
errors later.

```powershell
cd C:\Users\Tench\Documents\AriaAssistantApp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

You should see `(.venv)` at the start of your prompt. Every subsequent
`python` and `pip` command runs inside the venv.

If PowerShell refuses to activate the venv with a "running scripts is
disabled" error:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
Then try `.venv\Scripts\Activate.ps1` again.

---

## 4. Install Python dependencies

```powershell
cd C:\Users\Tench\Documents\AriaAssistantApp\astro_assistant
pip install -r requirements.txt
```

This installs ~80 packages: torch, TTS (Coqui), chromadb, openai,
streamlit, sounddevice, websockets, etc. **First install takes 5-15
minutes** (PyTorch alone is ~2.5 GB).

You do **NOT** need to install Coqui from `../Coqui-TTS-XTTS-v2-/`
on PC 1 — the TTS server runs on PC 2.

---

## 5. Point the Astro client at PC 2

Edit `C:\Users\Tench\Documents\AriaAssistantApp\astro_assistant\config.json`.
Find the two URLs and replace them with **PC 2's actual IP**:

```json
{
  "lmstudio_url": "http://192.168.10.2:1010/v1",
  "server_url":   "http://192.168.10.2:8765"
}
```

`client.py` accepts both `http://host:port` and `ws://host:port` — it
normalizes to `ws://` internally for the WebSocket connection.

If you set up PC 2 with the `192.168.68.88` network range from the
PC 2 README, use that IP here instead.

Copy the env file:
```powershell
cd C:\Users\Tench\Documents\AriaAssistantApp\astro_assistant
copy .env.example .env
```
Defaults are fine for client-side. Don't need to edit unless your
`XTTS_MODEL_DIR` lives somewhere unusual (it doesn't, by default).

---

## 6. Open the Godot project

1. Launch **Godot 4.6.3 (Mono)** — not the regular one
2. Click **Import** (top right of the Project Manager)
3. Navigate to `C:\Users\Tench\Documents\AriaAssistantApp\aria\`
4. Select `project.godot` → **Open**
5. Wait for first-time import (60-90 seconds — Godot compiles C# and
   imports the Aria model + 19 FBX animations)
6. When prompted "This project uses C#, build the solution now?" → **Yes**
7. When it asks for a build target, leave it at `Debug | Any CPU`

### Verify the build
In the Godot editor, bottom panel → **Output**. You should see:
```
[Main] Build OK: head-calib + adaptive bubble + 0.30s blink + walk-stop cap active
[AnimBuilder] Target skeleton: /root/Main/CharacterController/Aria/Armature/Skeleton3D (148 bones)
[AnimBuilder] Done. 19 animations baked, 0 skipped.
```

If the build marker is missing, press **Ctrl+Shift+B** in the editor
(or Project → Tools → C# → Create C# solution) to force a rebuild.

---

## 7. Run the project

### Option A — Use the launcher (recommended)

In a normal (non-admin) PowerShell:
```powershell
cd C:\Users\Tench\Documents\AriaAssistantApp
.\start_aria.ps1
```

The script:
1. Requests admin elevation (for the global hotkeys)
2. Activates `.venv`
3. Starts the Astro client in a new window
4. Starts the TTS client in a new window
5. Launches Godot (editor mode, since there's no exported game yet)

> **Note:** the Streamlit dashboard is **not** launched on PC 1 — it runs on
> PC 2 (the AI server) so you can tweak the LLM/TTS settings from there.
> See `README_PC2.md` §5 for dashboard setup.

To always open in editor mode:
```powershell
.\start_aria.ps1 -Editor
```

If you've installed deps system-wide and don't want a venv:
```powershell
.\start_aria.ps1 -NoVenv
```

Other flags you can combine with the above:

```powershell
# Don't launch Godot at all (run just the Astro + TTS services).
# Useful when PC 1 is just a desktop and Godot isn't ready yet.
.\start_aria.ps1 -NoGodot

# Skip the Astro client too — run ONLY the TTS (and motion server, in
# the diffusion build). The user is connecting from a different PC.
.\start_aria.ps1 -ServerOnly

# Open the procedural-IK debug scene in the editor instead of Main.tscn.
# Has a HUD, click-to-ik_reach, and keyboard hotkeys (R/L/T/Y/G/H/K).
# Only available in the AriaAssistantAppIK and AriaAssistantAppIKdiffusion
# builds (the base AriaAssistantApp has no IKDebug scene).
.\start_aria.ps1 -Editor -IKDebug
```

Flags can be combined freely: `.\start_aria.ps1 -Editor -IKDebug -NoVenv` opens
the IK debug scene in the Godot editor without activating the venv.

### Option B — Run things manually

Three PowerShell windows, then the Godot GUI:

```powershell
# Window 1 — Astro client
cd C:\Users\Tench\Documents\AriaAssistantApp\astro_assistant
.\.venv\Scripts\Activate.ps1
python client.py

# Window 2 — TTS client
cd C:\Users\Tench\Documents\AriaAssistantApp\astro_assistant
.\.venv\Scripts\Activate.ps1
python tts_client.py    # (or whichever wrapper your PC 2 has)
```

Then in Godot (Window 3), press **F5** to run the scene.

> **Note:** the Streamlit dashboard is a PC 2 thing — don't run it on
> PC 1. See `README_PC2.md` §5.

---

## 8. What you should see

Within ~5 seconds of pressing F5 in Godot:
- A transparent, borderless window covers your monitor
- Aria is visible standing on the taskbar at the bottom
- A speech bubble appears: "Hello there! ..."

Within ~30 seconds, she:
- Wanders to a window on the desktop
- Climbs up and perches on it
- Walks back down

In the **Astro client** PowerShell window, you should see:
```
[Client] Connected to ws://192.168.10.2:8765
```

If anything's missing, see the **Troubleshooting** section below.

---

## 9. Day-to-day

1. PC 2 should already be running (`start_aria_server.ps1` + LM Studio)
2. PC 1: run `start_aria.ps1`
3. Aria appears on PC 1's desktop
4. Talk to her / right-click her / let her roam
5. When done: close Godot on PC 1, then stop `start_aria_server.ps1` on PC 2

If PC 2 goes down, Aria on PC 1 keeps running — she just falls back
to no-LLM responses (scripted lines) until PC 2 comes back.

---

## Troubleshooting

### "Python is not recognized"
Python wasn't added to PATH. Re-run the installer, choose "Modify",
check "Add python.exe to PATH", or install fresh with that option.

### "pip install" fails on torch / TTS
Free up ~10 GB on C:. If the wheel download fails, force the CUDA
build:
```powershell
pip install --upgrade pip
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```
`cu121` is CUDA 12.1. Try `cu118` or `cu117` if your GPU is older.

### Godot: "Cannot open file 'res://...'" in Output
C# scripts haven't compiled. Press **Ctrl+Shift+B** in the editor.
If that doesn't help, close Godot, delete `aria/.godot/`, and reopen
`aria/project.godot` (Godot reimports everything).

### Aria is frozen in T-pose, sliding across the screen
Animation tracks can't find the bones. Press **Ctrl+Shift+B** to
recompile. If still broken, delete `aria/.godot/imported/*.sample` and
reimport.

### "Connection refused" or `[Client] could not connect`
PC 2's Astro server isn't running, or PC 1 can't reach it. Test in order:
```powershell
ping 192.168.10.2                  # network reachable?
Test-NetConnection 192.168.10.2 -Port 8765
curl http://192.168.10.2:1010/v1/models
```
Fix PC 2's setup if any of these fail (see `README_PC2.md`).

### Aria appears but is silent
TTS server on PC 2 isn't running, or the audio fetch is failing.
Check PC 2's TTS server window for errors. Test it directly from PC 1:
```powershell
curl http://192.168.10.2:5003/tts -X POST -H "Content-Type: application/json" -d '{"text":"test"}' --output test.wav
```

### Hotkeys don't fire
`start_aria.ps1` self-elevates. If you run `client.py` manually, the
PowerShell must already be Administrator (right-click → Run as
administrator).

### "Out of memory" when Godot launches
Close Chrome and any other GPU-hungry apps. Godot's first import loads
the Aria model + 19 FBX animations + compiles C# — peaks around 4 GB.

### Speech bubble is cut off
Already fixed in `aria/scripts/Main.cs` (the old mouse-passthrough
polygon used to act as a window region clip). Make sure you have the
latest code (Ctrl+Shift+B to recompile).

### Right-click on Aria doesn't trigger the playful poke
The hit-box is 320-350 px around Aria's feet (160 px each side, -340
to +10 vertical). Right-clicks outside that box pass through to apps
behind — that's intentional click-through behavior, not a bug.

### Send a message to Aria without right-clicking
There are three ways:

1. **Press F2** in the Godot window — a chat input strip drops down from
   the top of the screen. Type your message, hit **Enter** (or click
   "Send"). Press **F2** or **Esc** to close. The strip sits on
   `CanvasLayer` 11 (above the speech bubble at layer 10), so it works
   even when Aria is mid-sentence.

2. **Use the Streamlit dashboard on PC 2** — open the **💬 Chat with
   Aria (PC 1)** expander near the top, type a message, click Send.
   The dashboard POSTs to PC 1's chat server on port 8767; Aria's
   Godot app forwards it into the same LLM/animation pipeline.
   `start_aria.ps1` auto-creates a Windows firewall rule to allow
   inbound TCP 8767 from the LAN.

3. **Right-click on Aria's body** (if her hit-box is reachable — it's
   a 320-350 px region around her feet, since the window is otherwise
   click-through).

---

## 10. LLM directive vocabulary (what the brain can do)

The brain writes directives in JSON. The full vocabulary (each one
maps to a concrete body action on Aria):

### Body-level (locomotion, gestures, the 8-state machine)
| Directive       | Args                                  | Effect                                        |
|-----------------|---------------------------------------|-----------------------------------------------|
| `idle`          | `duration` (s)                        | Settle here for N seconds                     |
| `turn_to`       | `yaw_deg` OR `target`                 | Rotate body to a yaw / named target           |
| `walk_to`       | `x`, `y` OR `target`                  | Walk to absolute pixel / named target         |
| `walk_toward`   | `target`                              | Walk toward a named target                    |
| `climb`         | `window_id` (optional)                | Walk to and climb a window                    |
| `hop_off`       | —                                     | Step off a perch                              |
| `gesture`       | `name`, `duration`                    | One-shot gesture (wave, dance, react, …)     |
| `pause`         | `duration`                            | Wait N seconds                                |

### Procedural IK (real-time, layered over the animation)
| Directive       | Args                                  | Effect                                        |
|-----------------|---------------------------------------|-----------------------------------------------|
| `ik_reach`      | `name` (chain), `target` or `x,y`     | Reach a chain tip to a point                  |
| `ik_point`      | `name`, `target`                      | Like reach, but orients the hand              |
| `ik_look`       | `target` or `x,y`                     | Head/eyes look at a point                     |
| `ik_lean`       | `direction`, `amount`                 | Bend the spine in a direction                 |
| `ik_twist`      | `yaw_deg`, `pitch_deg`                | Upper-body twist                              |
| `ik_step`       | `hand`, `x`, `y`, `height`            | Plant a foot at a relative offset             |
| `ik_lift_leg`   | `hand`, `height`                      | Lift a foot (kick / step up)                  |
| `ik_grip`       | `hand`, `name` (open/closed/point/peace/thumbs_up), `amount` | Finger pose preset |
| `ik_hold_pose`  | `duration`                            | Freeze the current IK pose for N seconds      |
| `ik_release`    | `name` (chain)                        | Clear IK on a single chain                    |
| `ik_release_all`| —                                     | Clear IK on every chain                       |

Chain names for `ik_reach` / `ik_point`: `arm_left`, `arm_right`,
`arm_left_full`, `spine`, `torso`, `head`, `leg_left`, `leg_right`,
`thumb_l`/`thumb_r`, `index_l`/`index_r`, `middle_l`/`middle_r`,
`ring_l`/`ring_r`, `pinky_l`/`pinky_r`.

### Motion generation (only in `AriaAssistantAppIKdiffusion`)
| Directive       | Args                                  | Effect                                        |
|-----------------|---------------------------------------|-----------------------------------------------|
| `request_motion`| `prompt`, `frames`, `name`            | Asks PC 2's FloodDiffusion server to generate a new clip, queues it (cap 100, single-job), and auto-bakes it into the AnimationLibrary when it arrives |

A `prompt` is a plain-English description: "Aria does a happy spin with
arms out", "Aria waves from the hip", etc. The new clip becomes a
first-class animation Aria can use on subsequent turns.

### A worked example

User says: *"reach for that window and grab it"*

Brain replies:
```json
{
  "say": "Got it!",
  "emotion": "fun",
  "action": "none",
  "move": "stay",
  "directives": [
    {"action": "turn_to", "target": "nearest_window"},
    {"action": "ik_reach", "name": "arm_right", "target": "nearest_window"},
    {"action": "ik_grip",  "hand": "right", "name": "closed"}
  ]
}
```

Aria turns to face the nearest window, reaches her right arm toward it,
and closes her hand. All three run in sequence, layered over whatever
animation is currently playing.

