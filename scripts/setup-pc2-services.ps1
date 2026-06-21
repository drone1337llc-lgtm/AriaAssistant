# setup-pc2-services.ps1  -  one-time setup so brain, TTS, watchdog, and
# telegram_bot can run on PC 2 (192.168.68.88).
#
# Run this AFTER:
#   1. setup-ssh-to-ai-pc.ps1  (passwordless SSH must already work)
#   2. sync-to-pc2.ps1         (copies source + Coqui TTS scripts/data)
#
# What it does:
#   1. Ensures Python 3.12 is available (chromadb/crewai/torch have no 3.14 wheels yet)
#   2. Creates / updates brain/.venv   on PC 2  (Python 3.12)
#   3. Creates / updates watchdog/.venv on PC 2  (Python 3.12, if watchdog/ exists)
#   4. Creates D:\...\Coqui-TTS-XTTS-v2-\.venv and installs TTS deps (Python 3.12)
#   5. Opens Windows Firewall on PC 2 for port 8770 (brain)
#   6. Prints a status summary + model copy instructions
#
# JetKVM fallback (if SSH to PC 2 is flaky):
#   Web UI  : http://192.168.68.122
#   SSH     : ssh root@192.168.68.122  (no password, from PC 1 only)

$AIPc      = "192.168.68.88"
$User      = $env:USERNAME
$Root      = "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion"
$CoquiRoot = "$Root\Coqui-TTS-XTTS-v2-"   # TTS install on PC 2 (in-project, C: drive)

# SSH shorthand (no function - direct call to avoid PS 5.1 call-depth issues)
$SSH_OPTS = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=15")

Write-Host ""
Write-Host "=== PC 2 service setup ($AIPc) ===" -ForegroundColor Cyan
Write-Host ""

# --- verify SSH works -------------------------------------------------------
Write-Host "Checking SSH connectivity..." -ForegroundColor Yellow
$ping = & ssh @SSH_OPTS "${User}@${AIPc}" "echo PONG" 2>&1
if ($LASTEXITCODE -ne 0 -or $ping -notmatch "PONG") {
    Write-Host "SSH failed (exit $LASTEXITCODE). Run setup-ssh-to-ai-pc.ps1 first." -ForegroundColor Red
    Write-Host "SSH output: $ping"
    exit 1
}
Write-Host "SSH OK" -ForegroundColor Green
Write-Host ""

# --- ensure Python 3.12 (chromadb/crewai/torch have no Python 3.14 wheels) --
Write-Host "Checking Python 3.12 on PC 2..." -ForegroundColor Yellow
$py312Out = & ssh @SSH_OPTS "${User}@${AIPc}" "py -3.12 --version" 2>&1
if ($py312Out -match "Python 3\.12") {
    Write-Host "Python 3.12 found: $($py312Out -replace '\s+$','')" -ForegroundColor Green
} else {
    Write-Host "Python 3.12 not found - installing via winget (takes ~2-3 min)..." -ForegroundColor Yellow
    & ssh @SSH_OPTS "${User}@${AIPc}" "winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements"
    $py312Check = & ssh @SSH_OPTS "${User}@${AIPc}" "py -3.12 --version" 2>&1
    if ($py312Check -notmatch "Python 3\.12") {
        Write-Host "ERROR: Python 3.12 install failed." -ForegroundColor Red
        Write-Host "Install it manually on PC 2 from https://www.python.org/downloads/ then re-run."
        exit 1
    }
    Write-Host "Python 3.12 installed OK" -ForegroundColor Green
}
# All venvs use Python 3.12 - the py launcher picks the right interpreter
$PyCmd = "py -3.12"
Write-Host ""

# --- brain/.venv (Python 3.12) ----------------------------------------------
Write-Host "Setting up brain/.venv on PC 2..." -ForegroundColor Yellow

# Delete stale venv if it was created with Python 3.14 (wrong version)
$brainPyVer = & ssh @SSH_OPTS "${User}@${AIPc}" "if exist `"$Root\brain\.venv\Scripts\python.exe`" (`"$Root\brain\.venv\Scripts\python.exe`" --version)" 2>&1
if ($brainPyVer -match "Python 3\.1[4-9]") {
    Write-Host "  Existing brain/.venv is Python 3.14+ - recreating with 3.12..." -ForegroundColor Yellow
    & ssh @SSH_OPTS "${User}@${AIPc}" "rmdir /s /q `"$Root\brain\.venv`""
}
# Also delete if venv exists but chromadb failed to install (e.g. previous run had MSVC error)
$brainVenvExists = & ssh @SSH_OPTS "${User}@${AIPc}" "if exist `"$Root\brain\.venv\Scripts\python.exe`" echo YES" 2>&1
if ($brainVenvExists -match "YES") {
    $brainChromaOk = & ssh @SSH_OPTS "${User}@${AIPc}" "`"$Root\brain\.venv\Scripts\python.exe`" -c `"import chromadb; print('OK')`"" 2>&1
    if ($brainChromaOk -notmatch "OK") {
        Write-Host "  brain/.venv has incomplete packages (chromadb missing) - recreating..." -ForegroundColor Yellow
        & ssh @SSH_OPTS "${User}@${AIPc}" "rmdir /s /q `"$Root\brain\.venv`""
    }
}
& ssh @SSH_OPTS "${User}@${AIPc}" "if not exist `"$Root\brain\.venv`" $PyCmd -m venv `"$Root\brain\.venv`""
& ssh @SSH_OPTS "${User}@${AIPc}" "cd `"$Root\brain`" && `"$Root\brain\.venv\Scripts\python.exe`" -m pip install --quiet --no-cache-dir --upgrade pip && `"$Root\brain\.venv\Scripts\python.exe`" -m pip install --quiet --no-cache-dir -e ."
if ($LASTEXITCODE -eq 0) {
    Write-Host "brain/.venv OK" -ForegroundColor Green
} else {
    Write-Host "brain/.venv install had errors - check output above" -ForegroundColor Yellow
}
Write-Host ""

# --- watchdog/.venv (Python 3.12) -------------------------------------------
Write-Host "Checking watchdog on PC 2..." -ForegroundColor Yellow
$wdExists = & ssh @SSH_OPTS "${User}@${AIPc}" "if exist `"$Root\watchdog\pyproject.toml`" echo YES" 2>&1
if ($wdExists -match "YES") {
    $wdPyVer = & ssh @SSH_OPTS "${User}@${AIPc}" "if exist `"$Root\watchdog\.venv\Scripts\python.exe`" (`"$Root\watchdog\.venv\Scripts\python.exe`" --version)" 2>&1
    if ($wdPyVer -match "Python 3\.1[4-9]") {
        Write-Host "  Existing watchdog/.venv is Python 3.14+ - recreating with 3.12..." -ForegroundColor Yellow
        & ssh @SSH_OPTS "${User}@${AIPc}" "rmdir /s /q `"$Root\watchdog\.venv`""
    }
    & ssh @SSH_OPTS "${User}@${AIPc}" "if not exist `"$Root\watchdog\.venv`" $PyCmd -m venv `"$Root\watchdog\.venv`""
    & ssh @SSH_OPTS "${User}@${AIPc}" "cd `"$Root\watchdog`" && `"$Root\watchdog\.venv\Scripts\python.exe`" -m pip install --quiet --no-cache-dir --upgrade pip && `"$Root\watchdog\.venv\Scripts\python.exe`" -m pip install --quiet --no-cache-dir -e ."
    if ($LASTEXITCODE -eq 0) {
        Write-Host "watchdog/.venv OK" -ForegroundColor Green
    } else {
        Write-Host "watchdog/.venv install had errors" -ForegroundColor Yellow
    }
} else {
    Write-Host "watchdog/ not found on PC 2 - skipping" -ForegroundColor DarkGray
}
Write-Host ""

# --- Coqui TTS .venv (Python 3.12, runs from D:\...\Coqui-TTS-XTTS-v2-) ----
Write-Host "Setting up Coqui TTS .venv on PC 2..." -ForegroundColor Yellow

# Ensure Coqui root directory exists.
& ssh @SSH_OPTS "${User}@${AIPc}" "if not exist `"$CoquiRoot`" mkdir `"$CoquiRoot`""

# Delete stale venv if it was created with Python 3.14
$coquiPyVer = & ssh @SSH_OPTS "${User}@${AIPc}" "if exist `"$CoquiRoot\.venv\Scripts\python.exe`" (`"$CoquiRoot\.venv\Scripts\python.exe`" --version)" 2>&1
if ($coquiPyVer -match "Python 3\.1[4-9]") {
    Write-Host "  Existing Coqui .venv is Python 3.14+ - recreating with 3.12..." -ForegroundColor Yellow
    & ssh @SSH_OPTS "${User}@${AIPc}" "rmdir /s /q `"$CoquiRoot\.venv`""
}
& ssh @SSH_OPTS "${User}@${AIPc}" "if not exist `"$CoquiRoot\.venv`" $PyCmd -m venv `"$CoquiRoot\.venv`""
& ssh @SSH_OPTS "${User}@${AIPc}" "`"$CoquiRoot\.venv\Scripts\python.exe`" -m pip install --quiet --no-cache-dir --upgrade pip"

# Check if TTS is already installed.
$ttsCheck = & ssh @SSH_OPTS "${User}@${AIPc}" "`"$CoquiRoot\.venv\Scripts\python.exe`" -c `"from TTS.tts.models.xtts import Xtts; print('TTS OK')`"" 2>&1
if ($ttsCheck -match "TTS OK") {
    Write-Host "Coqui TTS .venv ready" -ForegroundColor Green
} else {
    Write-Host "Installing TTS + torch (this can take 10-20 min on first run)..." -ForegroundColor Yellow
    # Install torch with CUDA 12.1 first so TTS doesn't pull in CPU-only torch
    & ssh @SSH_OPTS "${User}@${AIPc}" "`"$CoquiRoot\.venv\Scripts\python.exe`" -m pip install --quiet --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121"
    & ssh @SSH_OPTS "${User}@${AIPc}" "`"$CoquiRoot\.venv\Scripts\python.exe`" -m pip install --quiet --no-cache-dir numpy scipy"
    # Install the TTS library. The in-project Coqui-TTS-XTTS-v2- folder is just
    # the server script + model + data (no setup.py), so install the maintained
    # PyPI package (coqui-tts) which provides the `TTS` import + XTTS-v2 and has
    # Python 3.12 wheels. (If you keep the FULL vendored source there instead,
    # swap this line for: cd /d "$CoquiRoot" ... pip install -e .)
    & ssh @SSH_OPTS "${User}@${AIPc}" "`"$CoquiRoot\.venv\Scripts\python.exe`" -m pip install --no-cache-dir coqui-tts"
    # coqui-tts 0.27.x needs transformers>=4.57, but transformers 5.x removed
    # isin_mps_friendly, which XTTS imports. The 4.57.x line satisfies both.
    & ssh @SSH_OPTS "${User}@${AIPc}" "`"$CoquiRoot\.venv\Scripts\python.exe`" -m pip install --no-cache-dir transformers==4.57.*"
    $ttsCheck2 = & ssh @SSH_OPTS "${User}@${AIPc}" "`"$CoquiRoot\.venv\Scripts\python.exe`" -c `"from TTS.tts.models.xtts import Xtts; print('TTS OK')`"" 2>&1
    if ($ttsCheck2 -match "TTS OK") {
        Write-Host "Coqui TTS .venv installed OK" -ForegroundColor Green
    } else {
        Write-Host "TTS install may have failed - check output above" -ForegroundColor Yellow
        Write-Host "Retry on PC 2 with:"
        Write-Host "  cd /d `"$CoquiRoot`""
        Write-Host "  `"$CoquiRoot\.venv\Scripts\python.exe`" -m pip install -e ."
    }
}
Write-Host ""

# --- Model files check -------------------------------------------------------
Write-Host "Checking Jessica voice model on PC 2..." -ForegroundColor Yellow
$modelPath = "$CoquiRoot\run\training\XTTS_v2_Jessica_Voice-June-08-2026_05+55PM-dbf1a08a\best_model.pth"
$modelExists = & ssh @SSH_OPTS "${User}@${AIPc}" "if exist `"$modelPath`" echo YES" 2>&1
if ($modelExists -match "YES") {
    Write-Host "Jessica model found on PC 2 - TTS server can start" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "*** Jessica voice model NOT found on PC 2 ***" -ForegroundColor Red
    Write-Host "The model is ~7 GB (best_model.pth + original_model_files/)."
    Write-Host "Copy it ONCE from PC 1 (run from a terminal on PC 1):"
    Write-Host ""
    Write-Host "  scp -r `"D:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\run\training`" `"${User}@${AIPc}:$CoquiRoot\run\`"" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Or SSH into JetKVM and run it there:  ssh root@192.168.68.122  (no password)"
}
Write-Host ""

# --- firewall: port 8770 (brain) --------------------------------------------
Write-Host "Opening firewall port 8770 (brain) on PC 2..." -ForegroundColor Yellow
# Use -EncodedCommand so PowerShell syntax survives SSH -> cmd.exe quoting
$fwLines  = @()
$fwLines += "if (-not (Get-NetFirewallRule -DisplayName 'AriaBrain 8770' -ErrorAction SilentlyContinue)) {"
$fwLines += "    New-NetFirewallRule -DisplayName 'AriaBrain 8770' -Direction Inbound -Protocol TCP -LocalPort 8770 -Action Allow | Out-Null"
$fwLines += "    Write-Host 'firewall rule added'"
$fwLines += "} else {"
$fwLines += "    Write-Host 'firewall rule already exists'"
$fwLines += "}"
$fwScript  = $fwLines -join "`n"
$fwEncoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($fwScript))
& ssh @SSH_OPTS "${User}@${AIPc}" "powershell -NoProfile -NonInteractive -EncodedCommand $fwEncoded"
Write-Host ""

# --- summary ----------------------------------------------------------------
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "PC 2 should now be able to run:"
Write-Host "  chromadb      port 8000  (run brain/setup_chromadb_pc2.ps1 if not done)"
Write-Host "  tts_server    port 5003  ($CoquiRoot\.venv  +  Jessica fine-tune model)"
Write-Host "  brain         port 8770  ($Root\brain\.venv, listens on 0.0.0.0)"
Write-Host "  telegram_bot  -          (brain/.venv)"
Write-Host "  watchdog      -          (watchdog/.venv)"
Write-Host "  motion_server port 8766  (motion_lib/.venv - separate setup)"
Write-Host ""
Write-Host "JetKVM: http://192.168.68.122  /  ssh root@192.168.68.122 (no password, PC1 only)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Next: run  .\scripts\start-aria-stack.ps1 start" -ForegroundColor Green
