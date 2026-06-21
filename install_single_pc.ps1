<#
.SYNOPSIS
    One-time install for Aria Assistant on a single machine (everything on one PC).
.DESCRIPTION
    Installs and verifies:
      - Windows prerequisites (PowerShell 5.1+, .NET 8 SDK)
      - Python 3.11+ (from python.org) with a project-local venv
      - All Python dependencies (Astro brain, motion server, dashboard, TTS client)
      - Coqui TTS (XTTS v2) + the Jessica voice fine-tune
      - LM Studio (the local LLM server)
      - Godot 4.6.3 Mono (the game engine Aria runs in)
      - FFmpeg 8 shared DLLs (for torchcodec)
      - Windows firewall rules for the Aria services

    Idempotent: re-running skips anything already installed and re-verifies what
    was already set up. The only steps that ASK before doing anything are the
    external installers (winget / choco / browser download). Never auto-installs
    a package manager or a multi-GB download without your go-ahead.

    After this script finishes, the daily launcher is:
        .\start_aria.ps1
.PARAMETER SkipGodot
    Don't install Godot 4.6.3 Mono. Useful for headless / server-only deployments.
.PARAMETER SkipLMStudio
    Don't prompt to install LM Studio. Useful if you plan to use a remote LM Studio.
.PARAMETER SkipTTS
    Don't install Coqui TTS / the Jessica voice. Aria will be silent.
.PARAMETER ConfirmAll
    Suppress the per-step 'Install X? [Y/n]' prompt. Use only after you've
    reviewed this script and understand what it does.
.PARAMETER NoAdmin
    Don't try to elevate to admin. Some steps (firewall, venv symlinks) may
    fail; the script will warn and continue.
.EXAMPLE
    .\install_single_pc.ps1
    # Standard install, asks before each external installer
.EXAMPLE
    .\install_single_pc.ps1 -SkipLMStudio -SkipTTS
    # Headless install (no LM Studio, no TTS)
.EXAMPLE
    .\install_single_pc.ps1 -ConfirmAll
    # Non-interactive install (assumes you've reviewed)
.NOTES
    Run from the project root, e.g.:
        cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
        .\install_single_pc.ps1
#>

[CmdletBinding()]
param(
    [switch]$SkipGodot,
    [switch]$SkipLMStudio,
    [switch]$SkipTTS,
    [switch]$ConfirmAll,
    [switch]$NoAdmin
)

$ErrorActionPreference = 'Stop'
$ProjectDir = $PSScriptRoot
if (-not $ProjectDir) { $ProjectDir = (Get-Location).Path }

function Step($n, $msg) {
    Write-Host ''
    Write-Host "[$n] $msg" -ForegroundColor Cyan
}
function Ok($msg)   { Write-Host "    [OK]   $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    [WARN] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "    [FAIL] $msg" -ForegroundColor Red }
function Ask($msg) {
    if ($ConfirmAll) { return $true }
    $resp = Read-Host "    $msg [Y/n]"
    if ([string]::IsNullOrWhiteSpace($resp)) { return $true }
    return ($resp -match '^[Yy]')
}

# 0. Pre-flight
Step 0 'Pre-flight checks'

$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin -and -not $NoAdmin) {
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"") + $args
    Write-Host '[Aria install] Re-launching as Administrator...' -ForegroundColor Yellow
    Start-Process -FilePath powershell.exe -ArgumentList $argList -Verb RunAs
    exit 0
}
if (-not $IsAdmin) { Warn 'Running without admin; firewall rule and some installs may fail.' }

$psv = $PSVersionTable.PSVersion
if ($psv.Major -lt 5) { Fail "PowerShell 5.1+ required (you have $psv). Update Windows."; exit 1 }
Ok "PowerShell $psv"

$drive = (Get-Item $ProjectDir).PSDrive.Name
$freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
if ($freeGB -lt 25) {
    Fail "Need at least 25 GB free on drive $drive (have $freeGB GB). Coqui + models + Godot are big."
    if (-not (Ask 'Continue anyway?')) { exit 1 }
} else {
    Ok "Disk space: $freeGB GB free on $drive"
}

try {
    $null = Invoke-WebRequest -Uri 'https://pypi.org/simple/' -UseBasicParsing -TimeoutSec 10
    Ok 'Internet reachable'
} catch {
    Fail 'No internet / pypi.org unreachable. Fix network, re-run.'
    exit 1
}

if (-not (Test-Path (Join-Path $ProjectDir 'aria\project.godot'))) {
    Fail "Doesn't look like an Aria project root (no aria\project.godot). Run from the project folder."
    exit 1
}
if (-not (Test-Path (Join-Path $ProjectDir 'astro_assistant\requirements.txt'))) {
    Fail 'Missing astro_assistant\requirements.txt.'
    exit 1
}
Ok "Project root: $ProjectDir"

# 1. .NET 8 SDK
Step 1 '.NET 8 SDK (Godot Mono build needs it)'
$dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if ($dotnet) {
    $v = (& dotnet --version) 2>$null
    if ($v -and $v -like '8.*') { Ok ".NET $v already installed" }
    else {
        Warn "Found dotnet $v but Aria wants 8.x. Will install alongside."
        if (Ask 'Install .NET 8 SDK now via winget?') {
            winget install --id Microsoft.DotNet.SDK.8 -e --accept-package-agreements --accept-source-agreements
        } else { Warn "Skipping .NET install; Aria won't build until you install 8.x yourself." }
    }
} else {
    if (Ask 'Install .NET 8 SDK now via winget?') {
        winget install --id Microsoft.DotNet.SDK.8 -e --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')
    } else { Fail 'Aria needs .NET 8 SDK. Install manually: https://dotnet.microsoft.com/download/dotnet/8.0' }
}

# 2. Python 3.11+
Step 2 'Python 3.11+'
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

# 3. FFmpeg 8 shared DLLs
Step 3 'FFmpeg 8 shared (needed by torchcodec for some audio paths)'
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
    } else { Warn 'Skipped. TTS will use the soundfile backend (no ffmpeg required, some codecs limited).' }
}

# 4. Python venv + dependencies
Step 4 'Python virtual environment + dependencies'
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

$AriaDeps = @(
    'coqui-tts[codec]==0.27.5',
    "transformers>=4.57,<4.70",
    "streamlit>=1.30"
)
& $venvPy -m pip install @AriaDeps 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Ok 'Coqui TTS + transformers + streamlit installed' }
else { Warn 'Some Aria deps failed; check the warning. TTS may still partially work.' }

$verify = @('torch', 'streamlit', 'requests', 'PIL', 'numpy')
foreach ($m in $verify) {
    & $venvPy -c "import $m; print('  ok', '$m', getattr($m, '__version__', 'n/a'))" 2>&1 | Select-Object -First 1
}

# 5. Coqui TTS (XTTS v2) + Jessica voice
if (-not $SkipTTS) {
    Step 5 'Coqui TTS (XTTS v2) + Jessica voice'
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
} else { Warn 'Skipping Coqui TTS (-SkipTTS)' }

# 6. Godot 4.6.3 Mono
if (-not $SkipGodot) {
    Step 6 'Godot 4.6.3 Mono (game engine for Aria)'
    $godot = $null
    foreach ($p in @(
        "$env:LOCALAPPDATA\Godot\Godot_4.6.3_mono_win64\Godot_v4.6.3-stable_mono_win64.exe",
        "$env:ProgramFiles\Godot\Godot_v4.6.3-stable_mono_win64\Godot_v4.6.3-stable_mono_win64.exe",
        "$env:ProgramFiles(x86)\Godot\Godot_v4.6.3-stable_mono_win64\Godot_v4.6.3-stable_mono_win64.exe"
    )) {
        if (Test-Path $p) { $godot = $p; break }
    }
    if ($godot) { Ok "Godot Mono found at $godot" }
    else {
        if (Ask 'Download Godot 4.6.3 Mono (~150 MB)?') {
            $url = 'https://github.com/godotengine/godot/releases/download/4.6.3-stable/Godot_v4.6.3-stable_mono_win64.zip'
            $zip = Join-Path $env:TEMP 'godot-mono.zip'
            $dst = Join-Path $env:LOCALAPPDATA 'Godot\Godot_4.6.3_mono_win64'
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            Write-Host '    Downloading Godot Mono ...' -NoNewline
            Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
            Write-Host ' done.'
            Write-Host '    Extracting ...' -NoNewline
            Expand-Archive -Path $zip -DestinationPath $dst -Force
            Remove-Item $zip -ErrorAction SilentlyContinue
            Write-Host ' done.'
            Ok "Godot Mono installed at $dst (start_aria.ps1 auto-detects it)"
        } else { Warn 'Skipped Godot install. Install manually from https://godotengine.org/download - pick the .NET / Mono build.' }
    }
} else { Warn 'Skipping Godot (-SkipGodot)' }

# 7. LM Studio
if (-not $SkipLMStudio) {
    Step 7 'LM Studio (local LLM server)'
    $lmsExe = Join-Path $env:LOCALAPPDATA 'LM-Studio\LM Studio.exe'
    if (Test-Path $lmsExe) { Ok 'LM Studio installed' }
    else {
        if (Ask 'Open the LM Studio download page in your browser? (then run the installer manually)') {
            Start-Process 'https://lmstudio.ai/download'
            Warn 'Browser opened. Run the installer, then come back here.'
        } else { Warn 'Skipped. Install manually: https://lmstudio.ai/download' }
    }
} else { Warn 'Skipping LM Studio (-SkipLMStudio)' }

# 8. Firewall rules
Step 8 'Windows firewall rules for Aria services'
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
Add-FirewallRuleSafe 'AriaChatServer (8767)' 8767
Add-FirewallRuleSafe 'AriaTTS (5003)' 5003
Add-FirewallRuleSafe 'AriaMotion (8766)' 8766
Add-FirewallRuleSafe 'AriaDashboard (8501)' 8501

# 9. Smoke test
Step 9 'Smoke test - verify core deps import'
$probeScript = @'
import sys
failed = []
for m in ['torch', 'streamlit', 'requests', 'PIL', 'numpy', 'transformers']:
    try:
        __import__(m)
    except Exception as e:
        failed.append((m, str(e)))
if failed:
    for m, e in failed:
        print('  FAIL  ' + m + ': ' + e)
    sys.exit(1)
print('  ok   all core deps import')
'@
$probeFile = Join-Path $env:TEMP 'aria_install_probe.py'
Set-Content -Path $probeFile -Value $probeScript -Encoding UTF8
& $venvPy $probeFile
Remove-Item $probeFile -ErrorAction SilentlyContinue
if ($LASTEXITCODE -eq 0) { Ok 'All core deps import' }
else { Warn 'Some core deps failed to import. The launcher will tell you which.' }

Write-Host ''
Write-Host '===============================================================' -ForegroundColor Cyan
Write-Host ' Aria install: DONE' -ForegroundColor Green
Write-Host ''
Write-Host ' Next steps:'
Write-Host '   1. Start LM Studio, load a model, enable the OpenAI-compatible'
Write-Host '      server on port 1010 (or any free port - set ARIA_LMSTUDIO_URL in .env).'
Write-Host '   2. Run the daily launcher:'
Write-Host '        .\start_aria.ps1'
Write-Host '   3. Aria appears as a transparent borderless window. Talk to her.'
Write-Host ''
Write-Host ' If anything is missing, re-run this script - it skips what is already done.'
Write-Host '===============================================================' -ForegroundColor Cyan
