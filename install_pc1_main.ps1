<#
.SYNOPSIS
    One-time install for Aria Assistant - PC 1 (the main desktop, where Aria lives).
.DESCRIPTION
    PC 1 is the I/O machine. It runs:
      - Godot 4.6.3 Mono (the game engine, Aria's body)
      - The Astro client (LLM bridge to PC 2)
      - The TTS client (voice playback)
      - The window detector (ambient awareness)

    It does NOT run:
      - LM Studio
      - The Astro server
      - Coqui TTS server
      - The Streamlit dashboard (lives on PC 2)

    Run PC 2's install FIRST (install_pc2_ai.ps1). PC 1 needs the server URLs
    to point to PC 2.

    Idempotent: re-running skips what's already installed.

    After this script finishes, the daily launcher is:
        .\start_aria.ps1
.PARAMETER AriaServerUrl
    URL of the Astro server on PC 2. Default http://192.168.68.88:8765.
.PARAMETER LmStudioUrl
    URL of LM Studio on PC 2. Default http://192.168.68.88:1010/v1.
.PARAMETER TtsServerUrl
    URL of the TTS server on PC 2. Default http://192.168.68.88:5003.
.PARAMETER ConfirmAll
    Suppress the per-step 'Install X? [Y/n]' prompt.
.EXAMPLE
    .\install_pc1_main.ps1
    # Standard install, asks before each external installer
.EXAMPLE
    .\install_pc1_main.ps1 -ConfirmAll
    # Non-interactive install
.EXAMPLE
    .\install_pc1_main.ps1 -AriaServerUrl http://192.168.68.50:8765
    # PC 2 is at a custom IP
.NOTES
    Run from the project root, e.g.:
        cd C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion
        .\install_pc1_main.ps1
#>

[CmdletBinding()]
param(
    # Default to localhost: PC1 reaches PC2 services through the bridge tunnels
    # (127.0.0.1:<port> -> mesh -> PC2). Pass explicit URLs to bypass the bridge.
    [string]$AriaServerUrl = 'http://127.0.0.1:8765',
    [string]$LmStudioUrl   = 'http://127.0.0.1:1010/v1',
    [string]$TtsServerUrl  = 'http://127.0.0.1:5003',
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
if ($freeGB -lt 5) {
    Fail "Need at least 5 GB free on drive $drive (have $freeGB GB). Godot + Godot cache are big."
    if (-not (Ask 'Continue anyway?')) { exit 1 }
} else { Ok "Disk space: $freeGB GB free on $drive" }

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
Ok "Project root: $ProjectDir"

# 1. .NET 8 SDK
Step 1 '.NET 8 SDK (Godot Mono build needs it)'
$dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if ($dotnet) {
    $v = (& dotnet --version) 2>$null
    if ($v -and $v -like '8.*') { Ok ".NET $v already installed" }
    else {
        if (Ask 'Install .NET 8 SDK now via winget?') {
            winget install --id Microsoft.DotNet.SDK.8 -e --accept-package-agreements --accept-source-agreements
            $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')
        } else { Fail "Aria needs .NET 8 SDK. Install manually: https://dotnet.microsoft.com/download/dotnet/8.0" }
    }
} else {
    if (Ask 'Install .NET 8 SDK now via winget?') {
        winget install --id Microsoft.DotNet.SDK.8 -e --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')
    } else { Fail "Aria needs .NET 8 SDK. Install manually: https://dotnet.microsoft.com/download/dotnet/8.0" }
}

# 2. Python 3.11+ (Astro client + TTS client)
Step 2 'Python 3.11+ (Astro client + TTS client)'
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

# 3. Python venv + client deps only
Step 3 'Python virtual environment + client-side deps'
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

# PC 1 only needs the client-side deps. TTS server / dashboard / motion server
# live on PC 2. requirements.txt pulls in everything; we just install what we
# need and skip coqui-tts (huge).
$clientDeps = @(
    'requests>=2.31',
    'numpy',
    'Pillow',
    'torch>=2.1',
    'transformers>=4.57,<4.70'
)
& $venvPy -m pip install @clientDeps 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Ok 'Client deps installed' }
else { Warn 'Some deps failed; check the launcher output.' }

# 4. Godot 4.6.3 Mono
Step 4 'Godot 4.6.3 Mono (game engine for Aria)'
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
        Ok "Godot Mono installed at $dst"
    } else { Warn 'Skipped Godot install. Install manually from https://godotengine.org/download - pick the .NET / Mono build.' }
}

# 5. Write .env with PC 2 URLs
Step 5 'Writing .env with PC 2 server URLs'
$envFile = Join-Path $ProjectDir '.env'
$envContent = @"
# Aria environment (PC 1 -> PC 2)
ARIA_SERVER_URL=$AriaServerUrl
LM_STUDIO_URL=$LmStudioUrl
TTS_SERVER_URL=$TtsServerUrl
"@
if ((Test-Path $envFile) -and -not $ConfirmAll) {
    if (-not (Ask '.env already exists. Overwrite with new PC 2 URLs?')) {
        Ok 'Keeping existing .env'
    } else {
        Set-Content -Path $envFile -Value $envContent -Encoding UTF8
        Ok "Wrote $envFile"
    }
} else {
    Set-Content -Path $envFile -Value $envContent -Encoding UTF8
    Ok "Wrote $envFile"
}

# 6. Firewall rules
Step 6 'Windows firewall rules (PC 1 -> PC 2)'
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
# PC 1 only needs to listen on 8767 (the chat server) and 5003/8766 are outbound
# to PC 2. Still, opening 8767 inbound makes Aria reachable from the LAN.
Add-FirewallRuleSafe 'AriaChatServer (8767)' 8767

# 7. Smoke test
Step 7 'Smoke test - verify PC 2 reachable'
foreach ($url in @($AriaServerUrl, $LmStudioUrl, $TtsServerUrl)) {
    try {
        $null = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        Ok "$url reachable"
    } catch {
        Warn "$url NOT reachable. Make sure PC 2 is on, services are running, and the firewall allows port 5003/8765/1010."
    }
}

Write-Host ''
Write-Host '===============================================================' -ForegroundColor Cyan
Write-Host ' Aria PC 1 install: DONE' -ForegroundColor Green
Write-Host ''
Write-Host ' Next steps:'
Write-Host '   1. Make sure PC 2 is on and all its services are up (check its console).'
Write-Host '   2. Run the daily launcher on PC 1:'
Write-Host '        .\start_aria.ps1'
Write-Host '   3. Aria appears as a transparent borderless window. Talk to her.'
Write-Host ''
Write-Host ' If PC 2 is unreachable, the launcher will tell you which service is down.'
Write-Host '===============================================================' -ForegroundColor Cyan
