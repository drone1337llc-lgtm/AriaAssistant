<#
.SYNOPSIS
    One-time install for Aria Assistant - PC 2 (the AI server, runs all the brain).
.DESCRIPTION
    PC 2 is the AI server. It runs:
      - LM Studio (local LLM inference, OpenAI-compatible server on port 1010)
      - Coqui TTS server (XTTS v2 + the Jessica voice fine-tune, port 5003)
      - The Astro server (Python brain, port 8765)
      - The Streamlit dashboard (web UI, port 8501)
      - (Optional) The FloodDiffusion motion server, port 8766
      - (Optional) FFmpeg 8 shared DLLs (for torchcodec)

    It does NOT run:
      - Godot (the character lives on PC 1)

    Run this script first, then run install_pc1_main.ps1 on PC 1.

    Idempotent: re-running skips what's already installed.

    After this script finishes, the daily launcher is:
        .\start_aria_server.ps1
.PARAMETER ConfirmAll
    Suppress the per-step 'Install X? [Y/n]' prompt.
.PARAMETER SkipMotion
    Don't install / configure the FloodDiffusion motion server.
.EXAMPLE
    .\install_pc2_ai.ps1
.EXAMPLE
    .\install_pc2_ai.ps1 -SkipMotion
    # PC 2 without FloodDiffusion (saves ~3 GB of model downloads)
.EXAMPLE
    .\install_pc2_ai.ps1 -ConfirmAll
    # Non-interactive install
.NOTES
    Run from the project root, e.g.:
        cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
        .\install_pc2_ai.ps1
#>

[CmdletBinding()]
param(
    [switch]$SkipMotion,
    [switch]$ConfirmAll
)

$ErrorActionPreference = 'Stop'
$ProjectDir = $PSScriptRoot
if (-not $ProjectDir) { $ProjectDir = (Get-Location).Path }

function Step($n, $msg) { Write-Host ''; Write-Host "[$n] $msg" -ForegroundColor Cyan }
function Ok($msg)       { Write-Host "    [OK]   $msg" -ForegroundColor Green }
function Warn($msg)     { Write-Host "    [WARN] $msg" -ForegroundColor Yellow }
function Fail($msg)     { Write-Host "    [FAIL] $msg" -ForegroundColor Red }
function Ask($msg) {
    if ($ConfirmAll) { return $true }
    $resp = Read-Host "    $msg [Y/n]"
    if ([string]::IsNullOrWhiteSpace($resp)) { return $true }
    return ($resp -match '^[Yy]')
}

# 0. Pre-flight
Step 0 'Pre-flight checks'

$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"") + $args
    Write-Host '[Aria install] Re-launching as Administrator...' -ForegroundColor Yellow
    Start-Process -FilePath powershell.exe -ArgumentList $argList -Verb RunAs
    exit 0
}

$psv = $PSVersionTable.PSVersion
if ($psv.Major -lt 5) { Fail "PowerShell 5.1+ required (you have $psv). Update Windows."; exit 1 }
Ok "PowerShell $psv"

$drive = (Get-Item $ProjectDir).PSDrive.Name
$freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
if ($freeGB -lt 40) {
    Fail "Need at least 40 GB free on drive $drive (have $freeGB GB). Coqui TTS + LM Studio models are big."
    if (-not (Ask 'Continue anyway?')) { exit 1 }
} else { Ok "Disk space: $freeGB GB free on $drive" }

# NVIDIA GPU check
try {
    $gpu = (Get-WmiObject Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '*NVIDIA*' } | Select-Object -First 1)
    if ($gpu) { Ok "NVIDIA GPU detected: $($gpu.Name)" }
    else { Warn 'No NVIDIA GPU detected. LM Studio / TTS will be slow or fail.' }
} catch { }

try {
    $null = Invoke-WebRequest -Uri 'https://pypi.org/simple/' -UseBasicParsing -TimeoutSec 10
    Ok 'Internet reachable'
} catch {
    Fail 'No internet / pypi.org unreachable. Fix network, re-run.'
    exit 1
}

if (-not (Test-Path (Join-Path $ProjectDir 'astro_assistant\requirements.txt'))) {
    Fail "Doesn't look like an Aria project root (no astro_assistant\\requirements.txt). Run from the project folder."
    exit 1
}
Ok "Project root: $ProjectDir"

# 1. Python 3.11+ (Astro brain + TTS + dashboard)
Step 1 'Python 3.11+ (Astro brain + TTS + dashboard)'
$python = $null
foreach ($cand in @('python', 'python3', 'py')) {
    $p = Get-Command $cand -ErrorAction SilentlyContinue
    if ($p) { $python = $p; break }
}
if ($python) {
    $ver = & $python.Source '--version' 2>&1
    if ($ver -match 'Python (\d+)\.(\d+)') {
        $maj = [int]$Matches[1]; $min = [int]$Matches[2]
        if ($maj -ge 3 -and $min -ge 11) { Ok "$ver already installed at $($python.Source)" }
        else { Warn "$ver is too old (need 3.11+)."; $python = $null }
    }
}
if (-not $python) {
    if (Ask 'Install Python 3.11+ via winget?') {
        winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')
    } else { Fail 'Python is required. Install manually from https://python.org/downloads/ (3.11 or newer).' }
}

# 2. FFmpeg 8 shared DLLs
Step 2 'FFmpeg 8 shared (needed by torchcodec for some audio paths)'
$FfmpegBin = Join-Path $ProjectDir 'tools\ffmpeg-shared\bin'
if (Test-Path (Join-Path $FfmpegBin 'avcodec-62.dll')) {
    Ok 'FFmpeg 8 shared DLLs already in tools\ffmpeg-shared\bin'
} else {
    Warn "FFmpeg 8 shared DLLs not found at $FfmpegBin"
    if (Ask 'Download FFmpeg 8 shared essentials into tools\ffmpeg-shared\? (~80 MB, ~1 min)') {
        $toolsDir = Join-Path $ProjectDir 'tools'
        New-Item -ItemType Directory -Force -Path $FfmpegBin | Out-Null
        $url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
        $zip = Join-Path $env:TEMP 'ffmpeg-shared.zip'
        try {
            Write-Host '    Downloading FFmpeg shared ...' -NoNewline
            Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
            Write-Host ' done.'
            Write-Host '    Extracting DLLs ...' -NoNewline
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
            $needed = @('avcodec-62.dll', 'avformat-62.dll', 'avutil-60.dll', 'swresample-6.dll', 'swscale-7.dll')
            foreach ($entry in $archive.Entries) {
                foreach ($n in $needed) {
                    if ($entry.Name -eq $n -or $entry.Name -like "*$n") {
                        $out = Join-Path $FfmpegBin $entry.Name
                        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $out, $true)
                    }
                }
            }
            $archive.Dispose()
            Write-Host ' done.'
            Ok 'FFmpeg 8 shared DLLs ready'
        } catch { Fail "FFmpeg install failed: $_ (TTS may still work via the soundfile backend.)" }
        finally { Remove-Item $zip -ErrorAction SilentlyContinue }
    } else { Warn 'Skipped. TTS will use the soundfile backend.' }
}

# 3. Python venv + all server deps
Step 3 'Python virtual environment + server-side deps'
$venv = Join-Path $ProjectDir '.venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
if (Test-Path $venvPy) {
    Ok "venv exists at $venv"
} else {
    Write-Host '    Creating venv ...' -NoNewline
    & python -m venv $venv
    Write-Host ' done.'
}
& $venvPy -m pip install --upgrade pip wheel setuptools 2>&1 | Select-Object -Last 3

$reqs = @(
    (Join-Path $ProjectDir 'astro_assistant\requirements.txt'),
    (Join-Path $ProjectDir 'astro_assistant\motion_requirements.txt')
)
foreach ($r in $reqs) {
    if (Test-Path $r) {
        Write-Host "    Installing $r ..." -NoNewline
        & $venvPy -m pip install -r $r 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Host ' ok.' -ForegroundColor Green }
        else { Write-Host ' FAILED.' -ForegroundColor Red; Fail "pip install $r failed. See output above." }
    } else { Warn "Missing $r" }
}

$serverDeps = @(
    'coqui-tts[codec]==0.27.5',
    'transformers>=4.57,<4.70',
    'streamlit>=1.30',
    'torch>=2.1'
)
& $venvPy -m pip install @serverDeps 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Ok 'Server deps installed' }
else { Warn 'Some deps failed; check the launcher output.' }

# 4. Coqui TTS (XTTS v2) + Jessica voice
Step 4 'Coqui TTS (XTTS v2) + Jessica voice'
$xtts = Join-Path $ProjectDir 'Coqui-TTS-XTTS-v2-'
if (Test-Path (Join-Path $xtts 'requirements.txt')) { Ok "Coqui TTS repo present at $xtts" }
else {
    Fail 'Coqui-TTS-XTTS-v2- folder missing. Clone the vendored repo into the project root.'
    Warn 'Skipping Coqui dep install.'
}
if (Test-Path $xtts) {
    Write-Host '    Installing Coqui deps into venv (this can take 3-5 min) ...' -ForegroundColor Cyan
    & $venvPy -m pip install -e $xtts 2>&1 | Select-Object -Last 5
    $jessica = Join-Path $xtts 'voices\jessica'
    if (Test-Path $jessica) { Ok 'Jessica voice fine-tune present' }
    else { Warn "Jessica voice not found at $jessica - TTS will fall back to a default voice." }
}

# 5. Motion server deps (optional)
if (-not $SkipMotion) {
    Step 5 'FloodDiffusion motion server (optional)'
    $motionScript = Join-Path $ProjectDir 'astro_assistant\motion_server.py'
    if (Test-Path $motionScript) { Ok 'motion_server.py present' }
    else { Warn 'motion_server.py missing (motion features will be disabled).' }

    $loader = Join-Path $ProjectDir 'astro_assistant\_flood_loader.py'
    if (Test-Path $loader) { Ok '_flood_loader.py present (Windows + no-flash-attn shim)' }
    else { Warn "_flood_loader.py missing - on Windows the server will fail to load the model. Re-pull the repo." }

    $hugCache = Join-Path $env:USERPROFILE '.cache\huggingface\hub\models--ShandaAI--FloodDiffusion'
    $modelId = 'ShandaAI/FloodDiffusion'
    if (Test-Path $hugCache) {
        Ok "FloodDiffusion model present in HF cache ($hugCache)"
    } else {
        if (Ask "Download FloodDiffusion model weights (~24 GB on disk, takes 5-15 min) now?") {
            Write-Host '    Downloading ShandaAI/FloodDiffusion ...' -NoNewline
            & $venvPy -m pip show huggingface_hub 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) { & $venvPy -m pip install 'huggingface_hub[cli]' 2>&1 | Out-Null }
            & $venvPy -m huggingface_hub.cli download $modelId --local-dir $hugCache 2>&1 | Select-Object -Last 5
            if (Test-Path $hugCache) { Write-Host ' done.' -ForegroundColor Green; Ok 'FloodDiffusion model downloaded' }
            else { Write-Host ' FAILED.' -ForegroundColor Red; Fail "model download failed. Run manually: huggingface-cli download $modelId" }
        } else { Warn "Skipped model download. Run manually: huggingface-cli download $modelId" }
    }

    if (-not (Test-Path (Join-Path $ProjectDir 'models\FloodDiffusion'))) {
        New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir 'models\FloodDiffusion') | Out-Null
    }
} else { Warn 'Skipping motion (-SkipMotion)' }

# 6. LM Studio
Step 6 'LM Studio (local LLM server)'
$lmsExe = Join-Path $env:LOCALAPPDATA 'LM-Studio\LM Studio.exe'
if (Test-Path $lmsExe) { Ok 'LM Studio installed' }
else {
    if (Ask 'Open the LM Studio download page in your browser? (then run the installer manually)') {
        Start-Process 'https://lmstudio.ai/download'
        Warn 'Browser opened. Run the installer, then come back here.'
    } else { Warn 'Skipped. Install manually: https://lmstudio.ai/download' }
}

# 7. Firewall rules - PC 2 is the server, so it MUST allow inbound
Step 7 'Windows firewall rules (PC 2 inbound - reachable from PC 1)'
function Add-FirewallRuleSafe($name, $port) {
    $existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
    if ($existing) { Ok "Firewall rule '$name' already present" }
    else {
        try {
            New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null
            Ok "Added firewall rule '$name' (TCP $port)"
        } catch { Warn "Couldn't add firewall rule '$name' (try as admin): $_" }
    }
}
Add-FirewallRuleSafe 'AriaTTS (5003)' 5003
Add-FirewallRuleSafe 'AriaMotion (8766)' 8766
Add-FirewallRuleSafe 'AriaDashboard (8501)' 8501
Add-FirewallRuleSafe 'AstroServer (8765)' 8765
Add-FirewallRuleSafe 'LMStudio (1010)' 1010

# 8. .env with PC 1 reachable + LM Studio URL
Step 8 'Writing .env with server config'
$envFile = Join-Path $ProjectDir '.env'
$envContent = @"
# Aria environment (PC 2 - server)
ARIA_SERVER_HOST=0.0.0.0
ARIA_SERVER_PORT=8765
LM_STUDIO_URL=http://127.0.0.1:1010/v1
TTS_SERVER_HOST=0.0.0.0
TTS_SERVER_PORT=5003
MOTION_SERVER_HOST=0.0.0.0
MOTION_SERVER_PORT=8766
"@
if ((Test-Path $envFile) -and -not $ConfirmAll) {
    if (-not (Ask '.env already exists. Overwrite with new server config?')) {
        Ok 'Keeping existing .env'
    } else {
        Set-Content -Path $envFile -Value $envContent -Encoding UTF8
        Ok "Wrote $envFile"
    }
} else {
    Set-Content -Path $envFile -Value $envContent -Encoding UTF8
    Ok "Wrote $envFile"
}

# 9. Smoke test
Step 9 'Smoke test - verify deps import'
$probeScript = @'
import sys
failed = []
for m in ['torch', 'streamlit', 'requests', 'PIL', 'numpy', 'transformers', 'TTS']:
    try:
        __import__(m)
    except Exception as e:
        failed.append((m, str(e)))
if failed:
    for m, e in failed:
        print('  FAIL  ' + m + ': ' + e)
    sys.exit(1)
print('  ok   all core deps import (including TTS)')
'@
$probeFile = Join-Path $env:TEMP 'aria_install_probe2.py'
Set-Content -Path $probeFile -Value $probeScript -Encoding UTF8
& $venvPy $probeFile
Remove-Item $probeFile -ErrorAction SilentlyContinue
if ($LASTEXITCODE -eq 0) { Ok 'All core deps import' }
else { Warn 'Some core deps failed to import. The launcher will tell you which.' }

Write-Host ''
Write-Host '===============================================================' -ForegroundColor Cyan
Write-Host ' Aria PC 2 install: DONE' -ForegroundColor Green
Write-Host ''
Write-Host ' Next steps:'
Write-Host '   1. Start LM Studio, load a model (qwen2.5-3b-instruct recommended'
Write-Host '      for the bulk brain, minimax-m2.7 for the slow / accurate path).'
Write-Host '   2. Enable the OpenAI-compatible server on port 1010.'
Write-Host '   3. Run the daily launcher on PC 2:'
Write-Host '        .\start_aria_server.ps1'
Write-Host '   4. Now run install_pc1_main.ps1 on PC 1.'
Write-Host ''
Write-Host ' If anything is missing, re-run this script - it skips what is already done.'
Write-Host '===============================================================' -ForegroundColor Cyan
