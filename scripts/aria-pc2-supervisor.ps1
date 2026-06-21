<#
.SYNOPSIS
  Aria PC2 backend supervisor ? runs ON PC 2.

.DESCRIPTION
  Starts and keeps alive the compute-heavy Aria services LOCALLY on PC 2 (brain,
  TTS, motion, optional telegram/watchdog). Because it runs natively on PC 2 ?
  not over SSH ? the processes persist for as long as PC 2 is on. Any service
  that dies is restarted on the next poll.

  ChromaDB is NOT managed here: it has its own SYSTEM auto-start task created by
  brain\setup_chromadb_pc2.ps1. Set -WithChroma to manage it here instead.

  Install it to run automatically at logon with:  install-aria-pc2-autostart.ps1

.USAGE
  .\aria-pc2-supervisor.ps1                 # start + monitor forever
  .\aria-pc2-supervisor.ps1 -Once           # start everything once, then exit
  .\aria-pc2-supervisor.ps1 -WithTelegram -WithWatchdog
  .\aria-pc2-supervisor.ps1 -Status         # print one health snapshot and exit
#>
param(
    [int]$IntervalSec = 15,
    [switch]$Once,
    [switch]$Status,
    [switch]$WithChroma,
    [switch]$WithTelegram,
    [switch]$WithWatchdog
)

$ErrorActionPreference = "Continue"

$Root      = "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion"
$CoquiRoot = "$Root\Coqui-TTS-XTTS-v2-"   # in-project (C: drive on PC 2, off the USB)
$LogDir    = Join-Path $Root "logs\pc2"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$SupLog = Join-Path $LogDir "supervisor.log"

function Log($msg) {
    $line = "{0}`t{1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"), $msg
    Add-Content -Path $SupLog -Value $line
    Write-Host $line
}

# FFmpeg shared DLLs (torchcodec / TTS) ? prepend to PATH for child processes if present.
$FfmpegBin = Join-Path $Root "tools\ffmpeg-shared\bin"

# --- Service definitions ----------------------------------------------------
# Each: name, exe, args[], cwd, port (0 = no port check), env{}
$Services = @(
    @{
        name = "brain"; port = 8770
        exe  = "$Root\brain\.venv\Scripts\python.exe"
        args = @("-m", "aria_brain.main")
        cwd  = "$Root\brain"
        env  = @{
            ARIA_BRAIN_HOST      = "0.0.0.0"
            LM_STUDIO_BASE_URL   = "http://127.0.0.1:1010/v1"
            CHROMADB_URL         = "http://127.0.0.1:8000"
            TTS_URL              = "http://127.0.0.1:5003/tts"
            ANONYMIZED_TELEMETRY = "False"
        }
    }
    @{
        name = "tts_server"; port = 5003
        exe  = "$CoquiRoot\.venv\Scripts\python.exe"
        args = @("scripts\tts_server_jessica.py")
        cwd  = $CoquiRoot
        env  = @{ TORCHAUDIO_USE_TORCHCODEC = "0"; TORCHAUDIO_BACKEND = "soundfile" }
    }
    @{
        name = "motion_server"; port = 8766
        exe  = "$Root\motion_lib\.venv\Scripts\python.exe"
        args = @("motion_server.py", "--port", "8766")
        cwd  = "$Root\motion_lib"
        env  = @{}
    }
)

if ($WithChroma) {
    $Services += @{
        name = "chromadb"; port = 8000
        exe  = "C:\chroma\.venv\Scripts\chroma.exe"
        args = @("run", "--host", "0.0.0.0", "--port", "8000", "--path", "C:\chroma_data")
        cwd  = "C:\chroma"
        env  = @{ ANONYMIZED_TELEMETRY = "False" }
    }
}
if ($WithTelegram) {
    $Services += @{
        name = "telegram_bot"; port = 0
        exe  = "$Root\brain\.venv\Scripts\python.exe"
        args = @("-m", "aria_brain.telegram_bot")
        cwd  = "$Root\brain"
        env  = @{ ARIA_BRAIN_HOST = "127.0.0.1" }
    }
}
if ($WithWatchdog) {
    $Services += @{
        name = "watchdog"; port = 0
        exe  = "$Root\watchdog\.venv\Scripts\python.exe"
        args = @("-m", "aisistant.main", "loop")
        cwd  = "$Root\watchdog"
        env  = @{}
    }
}

# Track running processes by service name.
$Running = @{}

function Test-Port($port) {
    if ($port -eq 0) { return $true }
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect("127.0.0.1", $port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(800)
        if ($ok -and $c.Connected) { $c.Close(); return $true }
        $c.Close(); return $false
    } catch { return $false }
}

function Test-Alive($svc) {
    $p = $Running[$svc.name]
    $procOk = ($p -ne $null) -and (-not $p.HasExited)
    if (-not $procOk) { return $false }
    # If the process is up but the port never opens, let it be ? startup (esp.
    # TTS model load) can take a while. We only treat process exit as "dead".
    return $true
}

function Start-Svc($svc) {
    if (-not (Test-Path $svc.exe)) {
        Log "[$($svc.name)] SKIP - interpreter not found: $($svc.exe) (provision its venv first)"
        return
    }
    $outLog = Join-Path $LogDir ("{0}.out.log" -f $svc.name)
    $errLog = Join-Path $LogDir ("{0}.err.log" -f $svc.name)

    # Apply env (incl. FFmpeg on PATH) to this process scope, launch, then restore.
    $saved = @{}
    foreach ($k in $svc.env.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, "Process")
        [Environment]::SetEnvironmentVariable($k, $svc.env[$k], "Process")
    }
    $savedPath = $env:Path
    if (Test-Path $FfmpegBin) { $env:Path = "$FfmpegBin;$env:Path" }

    try {
        $p = Start-Process -FilePath $svc.exe -ArgumentList $svc.args `
                           -WorkingDirectory $svc.cwd -PassThru -WindowStyle Hidden `
                           -RedirectStandardOutput $outLog -RedirectStandardError $errLog
        $Running[$svc.name] = $p
        Log "[$($svc.name)] started pid=$($p.Id)"
    } catch {
        Log "[$($svc.name)] FAILED to start: $($_.Exception.Message)"
    } finally {
        $env:Path = $savedPath
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k], "Process") }
    }
}

function Show-Status {
    Log "=== status ==="
    foreach ($svc in $Services) {
        $alive = Test-Alive $svc
        $port  = if ($svc.port -ne 0) { if (Test-Port $svc.port) { "port:up" } else { "port:down" } } else { "?" }
        Log ("  {0,-14} {1,-7} {2}" -f $svc.name, $(if ($alive) { "RUNNING" } else { "DEAD" }), $port)
    }
}

if ($Status) {
    # One-shot snapshot using port checks only (no process tracking across runs).
    Log "=== Aria PC2 status snapshot ==="
    foreach ($svc in $Services) {
        $port = if ($svc.port -ne 0) { if (Test-Port $svc.port) { "UP" } else { "DOWN" } } else { "n/a" }
        Log ("  {0,-14} :{1,-5} {2}" -f $svc.name, $svc.port, $port)
    }
    return
}

Log "=== Aria PC2 supervisor starting (interval ${IntervalSec}s) ==="
# Initial start in definition order (brain has a local fallback, so order is soft).
foreach ($svc in $Services) {
    Start-Svc $svc
    Start-Sleep -Seconds 2
}

if ($Once) { Log "started all (-Once); exiting"; return }

while ($true) {
    Start-Sleep -Seconds $IntervalSec
    foreach ($svc in $Services) {
        if (-not (Test-Alive $svc)) {
            Log "[$($svc.name)] not running - restarting"
            Start-Svc $svc
        }
    }
}
