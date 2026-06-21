<#
.SYNOPSIS
    One-shot launcher for Aria Assistant.
    Launches services in individual windows with environment isolation.
#>

param(
    [switch]$All,
    [switch]$WithGodot, [switch]$WithBrain, [switch]$WithTts, [switch]$WithMotion, [switch]$WithDashboard,
    [switch]$NoGodot,   [switch]$NoBrain,   [switch]$NoTts,   [switch]$NoMotion,   [switch]$NoDashboard,
    [switch]$Help
)

# ── 1. Map flags ────────────────────────────────────────────────────────
$ExplicitFlags = ($PSBoundParameters.Count -gt 0)
if (-not $ExplicitFlags) { $All = $true }
if ($All) { $WithGodot = $true; $WithBrain = $true; $WithTts = $true; $WithMotion = $true; $WithDashboard = $true }
if ($NoGodot)     { $WithGodot = $false }
if ($NoBrain)     { $WithBrain = $false }
if ($NoTts)       { $WithTts = $false }
if ($NoMotion)    { $WithMotion = $false }
if ($NoDashboard) { $WithDashboard = $false }

# ── 2. Admin Elevation ──────────────────────────────────────────────────
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"") + $args
    Start-Process -FilePath powershell.exe -ArgumentList $argList -Verb RunAs
    exit 0
}

# ── 3. Path Setup ───────────────────────────────────────────────────────
$ProjectDir  = $PSScriptRoot
$VenvPython  = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$GodotExe    = "C:\Users\Tench\Documents\Godot_v4.6.3-stable_mono_win64\Godot_v4.6.3-stable_mono_win64\Godot_v4.6.3-stable_mono_win64.exe"
$GodotProject = Join-Path $ProjectDir "aria"
$BrainExe    = Join-Path $ProjectDir "brain\.venv\Scripts\aria_brain.exe"

# ── 3a. FFmpeg shared DLLs (for torchcodec in TTS / motion_server) ─────
# torchcodec (pulled in by torchaudio 2.11+ when used by coqui-tts[codec])
# needs FFmpeg 8 shared DLLs (avcodec-62.dll etc.) on PATH at process start.
# We ship them in tools\ffmpeg-shared\bin so the project is self-contained.
$FfmpegBin = Join-Path $ProjectDir "tools\ffmpeg-shared\bin"
if (Test-Path $FfmpegBin) {
    $env:Path = "$FfmpegBin;$env:Path"
} else {
    Write-Host "[Aria] WARN: $FfmpegBin not found. If TTS fails to load speaker latents, install FFmpeg 8 shared and put the bin on PATH." -ForegroundColor Yellow
}

# ── 4. Helper: Launch in new Window ─────────────────────────────────────
function Launch-InWindow {
    param($Title, $WorkingDir, $Command)
    
    $tmpBat = Join-Path $env:TEMP ("aria_" + [Guid]::NewGuid().ToString().Substring(0,8) + ".bat")
    
    # We add an explicit override for the audio backend
    $batContent = @"
@echo off
cd /d "$WorkingDir"
set TORCHAUDIO_USE_TORCHCODEC=0
set TORCHAUDIO_BACKEND=soundfile
echo [Aria] Starting $Title...
"$VenvPython" $Command
echo [Aria] Process exited.
pause
"@
    $batContent | Out-File -FilePath $tmpBat -Encoding ascii
    Start-Process -FilePath cmd.exe -ArgumentList "/c start `"$Title`" `"$tmpBat`"" -WindowStyle Normal
}

# ── 5. Launch services ──────────────────────────────────────────────────
Write-Host "[Aria] Initializing services..." -ForegroundColor Green

if ($WithBrain) {
    if (Test-Path $BrainExe) {
        $tmpBat = Join-Path $env:TEMP ("aria_brain_" + [Guid]::NewGuid().ToString().Substring(0,8) + ".bat")
        @"
@echo off
cd /d "$(Join-Path $ProjectDir 'brain')"
echo [Aria] Starting Brain server...
"$BrainExe"
echo [Aria] Brain exited.
pause
"@ | Out-File -FilePath $tmpBat -Encoding ascii
        Start-Process -FilePath cmd.exe -ArgumentList "/c start `"Aria Brain`" `"$tmpBat`"" -WindowStyle Normal
        Write-Host "[Aria] Brain server launching..." -ForegroundColor Cyan
    } else {
        Write-Host "[Aria] WARN: Brain exe not found at $BrainExe" -ForegroundColor Yellow
    }
}

if ($WithGodot) {
    if (Test-Path $GodotExe) {
        # Launch Godot with the project path — runs the game directly (no editor UI).
        # Pass --verbose so startup errors appear in the Godot console.
        Start-Process -FilePath $GodotExe -ArgumentList "--path `"$GodotProject`" --verbose"
        Write-Host "[Aria] Godot launching ($GodotProject)..." -ForegroundColor Cyan
    } else {
        Write-Host "[Aria] WARN: Godot not found at $GodotExe" -ForegroundColor Yellow
    }
}

if ($WithTts) {
    $TtsScript = Join-Path $ProjectDir "Coqui-TTS-XTTS-v2-\scripts\tts_server_jessica.py"
    if (Test-Path $TtsScript) {
        Launch-InWindow "Aria TTS" (Split-Path $TtsScript) "tts_server_jessica.py --port 5003"
    }
}

if ($WithMotion) {
    $MotionScript = Join-Path $ProjectDir "astro_assistant\motion_server.py"
    if (Test-Path $MotionScript) {
        Launch-InWindow "Aria Motion" (Split-Path $MotionScript) "motion_server.py --port 8766 --preload"
    }
}

if ($WithDashboard) {
    $DashScript = Join-Path $ProjectDir "astro_assistant\dashboard.py"
    if (Test-Path $DashScript) {
        Launch-InWindow "Aria Dashboard" (Split-Path $DashScript) "dashboard.py"
    }
}

Write-Host "[Aria] Startup script complete. Check launched windows for errors." -ForegroundColor Yellow