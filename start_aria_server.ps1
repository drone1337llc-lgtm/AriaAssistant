param (
    [switch]$NoVenv,
    [switch]$NoMotion   # skip starting the FloodDiffusion motion server
)

# 1. Self-Elevate to Run as Administrator
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "[Aria] Requesting Administrator privileges..."
    $Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($NoVenv) { $Arguments += " -NoVenv" }
    if ($NoMotion) { $Arguments += " -NoMotion" }
    Start-Process powershell -ArgumentList $Arguments -Verb RunAs
    exit
}

# 2. Resolve paths
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir  = (Resolve-Path "$ScriptDir\..").Path
$VenvActivate = "$ProjectDir\.venv\Scripts\Activate.ps1"

$ActivateVenv = ""
if (-not $NoVenv -and (Test-Path $VenvActivate)) {
    $ActivateVenv = "& '$VenvActivate'"
} elseif (-not $NoVenv) {
    Write-Warning "[Aria] .venv not found at $VenvActivate. Use -NoVenv to skip, or create the venv first (see README_DUAL_PC.md)."
}

Write-Host "========================================"
Write-Host "    Starting Aria AI Server (PC 2)     "
Write-Host "  Project: $ProjectDir"
Write-Host "========================================"

# 3. Launch the Astro server (it binds to 0.0.0.0:8765 and waits for PC 1)
Write-Host "[Aria] Starting Astro server.py..."
$ServerCommand = "Set-Location '$ProjectDir\astro_assistant'; $ActivateVenv; python server.py"
Start-Process powershell -ArgumentList "-NoTitle", "-NoExit", "-Command", "& { $ServerCommand }"

# 4. Launch the dashboard (Streamlit) on this machine
Write-Host "[Aria] Starting dashboard on this machine..."
$DashboardCommand = "Set-Location '$ProjectDir\astro_assistant'; $ActivateVenv; .\run_dashboard.bat"
Start-Process powershell -ArgumentList "-NoTitle", "-NoExit", "-Command", "& { $DashboardCommand }"

# 5. Launch the FloodDiffusion motion server (optional, GPU-bound)
#    - Bound to 0.0.0.0:8765 + 1 (so it doesn't collide with the Astro server)
#    - Single-job, queue cap 100, model auto-loads on first request
#    - Skip with -NoMotion if you don't have a GPU or don't need it
if (-not $NoMotion) {
    Write-Host "[Aria] Starting FloodDiffusion motion server on :8766..."
    $MotionCommand = "Set-Location '$ProjectDir\astro_assistant'; $ActivateVenv; python motion_server.py --port 8766 --capacity 100"
    Start-Process powershell -ArgumentList "-NoTitle", "-NoExit", "-Command", "& { $MotionCommand }"
} else {
    Write-Host "[Aria] -NoMotion specified — skipping FloodDiffusion server"
}

# 5. Reminder: LM Studio must be running on this machine with the chat model loaded
Write-Host ""
Write-Host "========================================"
Write-Host "  REMINDER: ensure LM Studio is running"
Write-Host "  on this PC with the chat model loaded."
Write-Host "  Default: http://localhost:1234/v1"
Write-Host "========================================"

Write-Host "[Aria] Server startup sequence complete!"
Write-Host ""
Write-Host "  Listening ports (inbound, may need firewall rules):"
Write-Host "    8765  Astro server (PC 1 -> PC 2 brain bridge)"
Write-Host "    8766  FloodDiffusion motion server (AI-generated clips, optional)"
Write-Host "    8501  Streamlit dashboard (browse from PC 1: http://$($env:COMPUTERNAME):8501)"
Write-Host "    5003  TTS server (Aria's voice, run separately)"
