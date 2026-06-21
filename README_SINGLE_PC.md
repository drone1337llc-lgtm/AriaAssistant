# Single-PC Setup — Aria Assistant

Everything on one Windows machine. You need a discrete NVIDIA GPU
(RTX 3060 or better; RTX 4080 Super recommended) with 8 GB+ VRAM.

## Quick install (recommended)

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
.\install_single_pc.ps1
```

The install script does the steps below automatically: .NET 8 SDK, Python
3.11+ venv, Coqui TTS + Jessica, Godot 4.6.3 Mono, LM Studio, FFmpeg 8
shared, all firewall rules, and a smoke test. It asks before each external
install and is idempotent — re-run it any time and it skips what's done.

The rest of this README is the **detailed manual walkthrough** for users
who want to understand every step, install by hand, or troubleshoot.

> **Heads up:** this is a long read on purpose. Every step is here because
> at least one person hit it. If something seems obvious, read it anyway —
> the obvious step is usually the one that's different from what you'd expect.

> **Which build to use:** this README is for the base `AriaAssistantApp`
> folder. There are two derivatives in your `Documents\` folder:
>
> - **`AriaAssistantAppIK`** — adds a procedural-IK layer (FABRIK solver +
>   per-bone reach/look/lean/grip directives) on top of the base. The LLM
>   can now reach, point, look, lean, twist, and pose Aria's fingers in
>   real-time on top of the playing animation. ~300 lines of C# + a system
>   prompt expansion. **Pick this if you want fine-grained body control.**
>
> - **`AriaAssistantAppIKdiffusion`** — everything in the IK build PLUS a
>   client to PC 2's FloodDiffusion motion server, so the LLM can request
>   brand-new animation clips on demand ("teach yourself a cartwheel") and
>   have them auto-baked into the AnimationLibrary. The server is a single
>   Python process on the AI box. **Pick this if you want the LLM to teach
>   itself new motions over time.**
>
> Both derivatives build with the same Godot project + READMEs; install
> whichever one you want into a separate `Documents\` folder, then follow
> this README inside that folder.

---

## 1. Install the system prerequisites

### 1.1 Windows 10/11 + latest updates
Make sure Windows is fully updated. Reboot after.

### 1.2 Python 3.10+ (3.12 recommended)
Download from [python.org/downloads](https://www.python.org/downloads/windows/).
**During install, check "Add python.exe to PATH"** — this checkbox is
the single biggest source of "Python not found" errors later.

Verify in a new PowerShell:
```powershell
python --version    # should print 3.10, 3.11, or 3.12
pip --version
```

### 1.3 Git for Windows (optional but recommended)
[git-scm.com](https://git-scm.com/download/win). Install with default options.
Not strictly required (you can just download the AriaAssistantApp folder
as a ZIP), but you'll need git to push to GitHub.

### 1.4 Godot 4.6.3 (Mono / .NET build)
**This is the .NET (Mono) build, not the regular one.** The plain Godot
download will not work — Aria uses C# scripts.

Download: [godotengine.org/download](https://godotengine.org/download/) →
"Godot Engine v4.6.3 with .NET (Mono)" → Windows → 64-bit.

The installer puts it at:
```
C:\Users\Tench\AppData\Local\Programs\Godot\Godot_v4.6.3_mono_win64\Godot_v4.6.3_mono_win64.exe
```

`start_aria.ps1` looks there first. If your path differs, the script
auto-falls-back to a few other common locations. If none match, edit the
`$GodotExe` line in `start_aria.ps1`.

### 1.5 .NET 8 SDK
Godot Mono needs the .NET 8 SDK to build the C# assembly.
Download: [dotnet.microsoft.com/download/dotnet/8.0](https://dotnet.microsoft.com/download/dotnet/8.0) → SDK → Windows x64.
Install with defaults.

Verify:
```powershell
dotnet --version     # should print 8.x.x
```

### 1.6 Visual Studio Build Tools (C++ compiler)
A few of the Python wheels (`trimesh`, parts of `numpy` on some setups,
`chromadb`'s sqlite) need a C++ compiler to build.

Download: [visualstudio.microsoft.com/visual-cpp-build-tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
During install, check **"Desktop development with C++"** on the right.
~6 GB download; takes 10-20 minutes.

### 1.7 LM Studio
Download: [lmstudio.ai](https://lmstudio.ai/). Install with defaults.

Launch it once so it creates its config directory, then continue.

---

## 2. Place the project

Pick where you want AriaAssistantApp to live. Any folder works. The
rest of this guide assumes `C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\`.
If you put it elsewhere, all paths in the commands below need updating —
so use this exact path unless you have a good reason not to.

If you cloned via git:
```powershell
cd C:\Users\Tench\Documents
git clone <your-repo-url> AriaAssistantApp
cd AriaAssistantApp
```

If you downloaded a ZIP, extract it to `C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\`.

---

## 3. Create the Python virtual environment

**This MUST be done before installing any Python dependencies.** A venv
keeps the project's packages isolated from your system Python and from
other projects. Skipping this step is the #1 cause of "ModuleNotFoundError"
and "version conflict" errors later.

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

You should see the prompt change to include `(.venv)`. From this point
on, every `python` and `pip` command runs inside the venv.

If PowerShell refuses to run the activation script with a "running scripts
is disabled" error:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
Then try `.venv\Scripts\Activate.ps1` again.

---

## 4. Install Python dependencies

### 4.1 The Astro brain (astro_assistant/)

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\astro_assistant
pip install -r requirements.txt
```

This installs ~80 packages: torch, TTS (Coqui), chromadb, openai, streamlit,
sounddevice, etc. **First install takes 5-15 minutes** because PyTorch alone
is ~2.5 GB.

### 4.2 The Coqui TTS repo (editable install)

The Coqui XTTS v2 voice cloning code lives in `Coqui-TTS-XTTS-v2-/` and
must be importable as a Python package. Install it editable so any future
edits to the repo are picked up:

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\Coqui-TTS-XTTS-v2-
pip install -e .
```

If that fails, try the alternative from PyPI:
```powershell
pip install TTS
```
This pulls a slightly older Coqui build. Most of the project still works
but voice cloning quality may differ.

### 4.3 (Optional) Verify the install

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\astro_assistant
python -c "from voice_speak import AstroVoice; print('voice OK')"
python -c "from tools import TOOL_REGISTRY; print('tools OK')"
python -c "import chromadb; import streamlit; print('deps OK')"
```

If all four print `... OK`, the Python side is good.

---

## 5. Set up LM Studio

### 5.1 Load the chat model

In LM Studio:
1. Search bar → "**llama-3-8b-lexi-uncensored**" → download
2. Click the model → "**Load Model**" on the right
3. Wait for it to finish loading into VRAM

The first run is slow (model file is ~5 GB). After that, the model is
cached.

### 5.2 Start the server

In LM Studio's left panel:
1. Click the **Developer** tab (the `</>` icon)
2. Click **Start Server**
3. Confirm the URL is `http://localhost:1234/v1` (the default)

The default port for LM Studio is 1234. The user config in
`astro_assistant/config.json` overrides this to `1010`:
```json
"lmstudio_url": "http://192.168.68.88:1010/v1"
```
**You need to set LM Studio's port to 1010 in its Developer tab to match**,
or edit `config.json` to use 1234.

### 5.3 Smoke test

In a new PowerShell:
```powershell
curl http://localhost:1010/v1/models
```
or
```powershell
curl http://localhost:1234/v1/models
```
You should get JSON listing the loaded model.

---

## 6. Configure the Astro brain

```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\astro_assistant
copy .env.example .env
```

Open `.env` in a text editor. The defaults are usually fine for single-PC
mode. Specifically check:
- `LMSTUDIO_BASE_URL` — must match the port LM Studio is on (1010 or 1234)
- `TESSERACT_CMD` — only set if you installed Tesseract somewhere other
  than the default `C:\Program Files\Tesseract-OCR\tesseract.exe`

You can leave `XTTS_MODEL_DIR` and `XTTS_SAMPLES_DIR` commented out — the
scripts will fall back to the default paths under
`AriaAssistantApp\Coqui-TTS-XTTS-v2-\`.

---

## 7. Open the Godot project

1. Launch **Godot 4.6.3 (Mono)** — not the regular one.
2. Click **Import** (top right).
3. Navigate to `C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\aria\`
4. Select `project.godot` → **Open**
5. Wait for first-time import (60-90 seconds — Godot is compiling C# and
   importing the Aria model + 19 FBX animations).

The first time you do this, Godot will say "This project uses C#, build the
solution now?" — click **Yes**. If it asks for a build target, leave it
at `Debug` and any CPU. The build finishes in a few seconds.

### Verify the build
In the Godot editor, bottom panel → **Output**. You should see:
```
[Main] Build OK: head-calib + adaptive bubble + 0.30s blink + walk-stop cap active
[AnimBuilder] Target skeleton: /root/Main/CharacterController/Aria/Armature/Skeleton3D (148 bones)
[AnimBuilder] Done. 19 animations baked, 0 skipped.
```

If you see "stale C# build" errors or the build marker is missing, hit
**Ctrl+Shift+B** in the editor (or Project → Tools → C# → Create C# solution)
to force a rebuild.

---

## 8. Run the project

### Option A — Use the launcher (recommended)

In a normal (non-admin) PowerShell:
```powershell
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
.\start_aria.ps1
```

The script will:
1. Request admin elevation (for the global hotkeys)
2. Activate `.venv`
3. Start the Astro client in a new window
4. Start the Coqui TTS server in a new window
5. Start the Streamlit dashboard in a new window
6. Launch Godot (editor mode, since there's no exported game yet)

To force editor mode every time:
```powershell
.\start_aria.ps1 -Editor
```

To run without the venv (if you've installed deps system-wide):
```powershell
.\start_aria.ps1 -NoVenv
```

Other useful flags (any can be combined):

```powershell
# Skip Godot — services only (Astro + TTS + dashboard, no window pops up).
# Good for headless testing or when you want to restart the AI side without
# closing Aria's window.
.\start_aria.ps1 -NoGodot

# Server-only mode — TTS + dashboard + motion server, no Astro client.
# Useful when the user is connecting from a different PC.
.\start_aria.ps1 -ServerOnly

# Open the procedural-IK debug scene in the editor. Has a HUD with
# active-chain readouts, click-to-ik_reach, and keyboard hotkeys
# (R=reach, L=look, T=lean, Y=twist, G/H=grip, K=release).
# Only available in the AriaAssistantAppIK and AriaAssistantAppIKdiffusion
# builds.
.\start_aria.ps1 -Editor -IKDebug
```

Example: open the IK debug scene without activating the venv (because you
installed deps system-wide):
```powershell
.\start_aria.ps1 -Editor -IKDebug -NoVenv
```

### Option B — Run things manually

Four PowerShell windows, one per service:

```powershell
# Window 1 — Astro client
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\astro_assistant
.\.venv\Scripts\Activate.ps1
python client.py

# Window 2 — Coqui TTS server
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\Coqui-TTS-XTTS-v2-\scripts
..\..\..\venv\Scripts\Activate.ps1    # (path relative to current dir)
python tts_server_jessica.py

# Window 3 — Streamlit dashboard
cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\astro_assistant
.\.venv\Scripts\Activate.ps1
.\run_dashboard.bat

# Window 4 — Godot (use the GUI)
```
Then in Godot, press **F5** to run the scene.

---

## 9. What you should see

Within ~5 seconds of pressing F5 in Godot:
- A transparent, borderless window appears covering your whole monitor
- Aria is visible standing on the taskbar at the bottom
- A speech bubble appears: "Hello there! ..."

Within ~30 seconds, she:
- Wanders to a window on the desktop
- Climbs up and perches on it
- Walks back down

If anything's missing, see the **Troubleshooting** section below.

---

## 10. Optional but recommended

### 10.1 Tesseract OCR
Some Astro features (text-aware scanning) use Tesseract.
Download: [UB-Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) → 64-bit.
Install to `C:\Program Files\Tesseract-OCR\` (the default).

### 10.2 Piper TTS (fallback voice)
A small offline voice used when the XTTS model isn't loaded.
```powershell
pip install piper-tts
```
Download `en_US-lessac-medium.onnx` + `.onnx.json` from
[piper releases](https://github.com/rhasspy/piper/releases) into
`astro_assistant/`.

### 10.3 Nightly memory job
A 3 AM Task Scheduler job that compiles the day's interactions into
ChromaDB so Aria remembers past sessions.
```powershell
# Inside astro_assistant/
python voice_schedule.py
```

### 10.4 Auto-start Aria on login
In Task Scheduler:
- Create Basic Task → Trigger: "When I log on"
- Action: Start a program
  - Program: `powershell.exe`
  - Arguments: `-ExecutionPolicy Bypass -File "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\start_aria.ps1"`
  - Start in: `C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion`

---

## Troubleshooting

### "Python is not recognized"
Python wasn't added to PATH during install. Re-run the installer, choose
"Modify", and check "Add python.exe to PATH". Or install a fresh Python
with that option checked.

### "pip install" fails on torch / TTS
Make sure you have ~10 GB free on the C: drive and your internet isn't
blocking PyPI. If the wheel fails to download, try:
```powershell
pip install --upgrade pip
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```
(That installs the CUDA 12.1 build of PyTorch; if your GPU is older, try
`cu118` or `cu117`.)

### "Cannot open file 'res://...'" in Godot output
The C# scripts haven't compiled. Press **Ctrl+Shift+B** in the editor. If
that doesn't help, close Godot, delete `aria/.godot/`, and reopen
`aria/project.godot` (Godot will reimport everything).

### Aria is frozen in T-pose, sliding across the screen
The animation tracks can't find the bones. Press **Ctrl+Shift+B** to
recompile. If the build is up to date and it's still broken, delete
`aria/.godot/imported/*.sample` (the cached samples) and reimport.

### Aria appears but walks with feet sliding
Open `aria/scenes/Main.tscn`, click the `CharacterController` node, look
at the `WalkSpeed` property in the Inspector. Try values between 60 and 200.
The default is 160 (matched to the walking.fbx clip's stride).

### "Connection refused" to LM Studio
LM Studio isn't running, or its port doesn't match `config.json`. Check
both — see **Section 5.2**.

### Jessica voice silent / out of memory
The XTTS model is ~2 GB on the GPU. If you're already loaded with another
large model, XTTS will OOM. Close other GPU apps or use Piper as a fallback.

### Godot window is invisible / off-screen
On some monitor configurations, Godot's borderless-maximized window lands
at the wrong screen Y. The fix is in the Godot project settings:
`Display → Window → Size → Position → Y = 0`.

### Speech bubble is cut off / only shows bottom edge
This was caused by the old mouse-passthrough polygon acting as a window
region clip. Already fixed — make sure you have the latest
`aria/scripts/Main.cs` (Ctrl+Shift+B to recompile).

### The desktop becomes unclickable where Aria is
Aria's window is fully click-through. If clicking doesn't reach the apps
behind, it's a Windows-level issue, not Aria. Make sure the window isn't
maximized in a way that focuses it on click (Godot's `no_focus=true` should
prevent this).

### Hotkeys don't fire
The Astro client needs admin privileges to install global keyboard hooks.
`start_aria.ps1` self-elevates; if you run `client.py` manually, launch
the PowerShell as Administrator first.

### "Cannot find voice model directory"
The XTTS model path is hardcoded in `voice_speak.py` to:
`Coqui-TTS-XTTS-v2-/run/training/XTTS_v2_Jessica_Voice-June-08-2026_05+55PM-dbf1a08a`
If you've retrained and the folder name is different, either rename the
folder or set `XTTS_MODEL_DIR` in `.env` to the new path.

### "The user just clicked on you" never fires when I right-click Aria
Right-clicks on Aria trigger the playful-poke. Make sure your click is
inside her 320×350 px hit-box (her head is around the top of that box,
her feet at the bottom). Clicks outside that area pass through to apps
behind — that's intentional, not a bug.

### Aria is silent but the speech bubble appears
TTS server isn't running. Check the second PowerShell window from
`start_aria.ps1` — there should be no errors there. If it crashed on
start, see the "voice_speak import failed" error in its log.

### Streamlit dashboard says "Registry error"
Run the dashboard as Administrator. The "registry" it complains about
is a Windows thing that the Streamlit cache uses, and it sometimes
needs admin to write on first run.
