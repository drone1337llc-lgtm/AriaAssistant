# PersonaPlex — findings & parking note

**Status: PARKED (2026-06-21).** Proven to run; shelved on purpose. Revisit when a
**dedicated 24 GB+ GPU** is available (the 7900XTX box, or any spare CUDA card) so it
isn't stealing the 3090 from the brain/specialist models. Full integration design is in
`docs/PERSONAPLEX_INTEGRATION.md` — this file is the "what we learned, why we stopped,
how to pick it back up" memo.

## What it is / why we wanted it
PersonaPlex (NVIDIA, 7B, built on Kyutai Moshi/Helium) is a real-time **full-duplex
speech-to-speech** model: it listens and talks at the same time, handles interruptions,
backchannels, and natural turn-taking — the "feels alive" conversational layer the current
STT→brain→TTS pipeline can't do. Repo: https://github.com/NVIDIA/personaplex ·
weights: https://huggingface.co/nvidia/personaplex-7b-v1 (NVIDIA Open Model License).

## Architecture we chose (still the plan if revived)
Fast layer = PersonaPlex (natural voice, generates its own words). Slow layer = our brain
as **conductor**: eavesdrops the live transcript, runs specialists (coder/vision/memory)
in the background while PersonaPlex keeps talking, then injects a finished line via a new
`POST /api/control` ("hold" → run specialist → "relay"). Three seams to add to the server:
event-out (transcript already streams), control-in (`/api/control`), selective injection in
`LMGen.step`. Details + phase plan: `docs/PERSONAPLEX_INTEGRATION.md` (Phases 3–6, tasks #17–19).

## What we PROVED works (don't re-derive)
- **Jessica voice is supported** — `LMGen.load_voice_prompt(path)` accepts a **WAV**
  (only `.pt` are pre-baked embeddings). Use a clean ~15s clip from `data/jessica_voice/wavs/`.
- **Aria's transcript already streams** out of the server as `0x02`+utf8 messages — free
  event-out for the brain. Audio is `0x01`+Opus; handshake `0x00`.
- **Single injection point** = `tokens = lm_gen.step(codes)`; `tokens[0,0,0]` = text token,
  `tokens[:,1:9]` = agent audio. One session (single `LMGen` + `asyncio.Lock`).
- **No quantization path exists** — `get_moshi_lm` is bf16 only (confirmed in `loaders.py`);
  only low-VRAM lever is `--cpu-offload` (accelerate, slower). The **Q8 GGUF is a dead end**:
  wrong format for `moshi.server`, and llama.cpp can't run Moshi's audio architecture.

## Install recipe that WORKED on Windows (PC2, the 3090)
1. Clone the repo (NOT `pip install moshi` from PyPI — that's vanilla Kyutai without PersonaPlex):
   `git clone https://github.com/NVIDIA/personaplex.git`
2. venv on **Python 3.12** (3.11 wasn't installed; any 3.10–3.12 works).
3. `pip install .\moshi` — installs `moshi-personaplex`. `sphn` installed clean (no Windows
   opus problem). **But it clobbers torch with a CPU/2.4.1 build**, so reinstall CUDA torch:
   `pip uninstall -y torchvision torchaudio` then
   `pip install --force-reinstall torch==2.4.1+cu121 --index-url https://download.pytorch.org/whl/cu121`
   (moshi pins torch **2.4.1**; verify `torch.cuda.is_available()` → True).
4. `hf auth login` (after accepting the model license in a browser).
5. **Triton crash at warmup is a Windows issue** (moshi uses `torch.compile`; no Triton on
   Windows). Disable it: `\$env:NO_TORCH_COMPILE = "1"` (type by hand — don't paste, a
   zero-width char snuck in once). Optional second toggle if CUDA-graph errors: `\$env:NO_CUDA_GRAPH = "1"`.
6. Launch:
   ```powershell
   \$ssl = New-Item -ItemType Directory -Force -Path "\$env:TEMP\ppssl"
   \$env:NO_TORCH_COMPILE = "1"
   python -m moshi.server --hf-repo "nvidia/personaplex-7b-v1" --ssl \$ssl.FullName --host 0.0.0.0
   ```
   → Web UI at `https://<ip>:8998` (self-signed cert → Advanced→Proceed; allow mic).
   Jessica later: `--voice-prompt-dir <folder with jessica.wav>`, request `voice_prompt=jessica.wav`.

## Runtime findings (the reasons we parked it)
- **VRAM: ~23 GB — the ENTIRE 3090** (with LM Studio fully unloaded). Confirms it can't
  co-reside with the specialist LLMs; voice and "thinking" would time-share the GPU.
- **Voice:** NATF1 (Natural female 1) sounded best of the stock voices.
- **Latency:** noticeable in **eager mode** (compile off). `pip install triton-windows` would
  re-enable `torch.compile` and cut latency — only worth it if we revive on a CUDA box.
- **Conversation quality:** feels scripted / over-eager — it improvises a plausible answer to
  fill the turn instead of saying "I don't know" or asking to clarify. Expected for a 7B speech
  model with no knowledge; this is exactly what the brain-conductor was meant to fix. Persona
  prompt granting permission to be uncertain helps the *feel* but not the substance.
- **Bluetooth static (important):** classic BT can't do hi-fi playback (A2DP) + mic (HFP) at
  once. Full-duplex keeps the mic **open continuously**, so a BT headset is stuck in the
  narrowband headset profile the whole conversation → staticy, in-and-out audio. **Full-duplex
  is the worst case for a Bluetooth headset**, and the headset isn't changing. Triton/PersonaPlex
  can't fix this; a turn-based system can (mic only hot while you talk).

## Why parked
Too heavy for the payoff: a whole 7B model + the entire 3090, just for the conversational
*layer*, while the actual intelligence is in the brain — plus a Bluetooth full-duplex audio
penalty. Not worth dedicating the 3090. **Revisit only on a separate GPU.**

## How to revive (later)
- **Best:** drop PersonaPlex on a **dedicated 24 GB+ CUDA GPU** (cleanest — install recipe
  above just works, add `triton-windows` for latency). Then build Phases 3–6 from
  `docs/PERSONAPLEX_INTEGRATION.md`.
- **AMD option (the 7900XTX 24 GB box):** Linux + **ROCm** PyTorch only (ROCm-on-Windows
  isn't there). PyTorch-ROCm exposes AMD cards through the `torch.cuda` API, so moshi's
  `device="cuda"` may target the 7900XTX with little/no code change — **risk is whether
  Moshi's kernels are ROCm-clean.** The Arc A770 is not usable (needs IPEX/XPU).
- Either way the Bluetooth-headset full-duplex audio penalty remains — keep that in mind.

## Meanwhile
Pursuing the lighter path on the existing pipeline: **streaming STT + streaming TTS +
barge-in (interruption)** on brain + Jessica (XTTS). Keeps the 3090 free for the specialists,
gets most of the "natural, instantaneous" feel, and is friendlier to a Bluetooth headset.
