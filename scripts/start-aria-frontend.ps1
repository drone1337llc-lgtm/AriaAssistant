<#
  Aria front-end launcher  --  run on PC1 (SurgeMain).

  The PC2 backend (brain / TTS / motion / LM Studio) is always-on, so this is the
  ONLY thing you run day to day. It brings up everything you SEE on PC1:
      • the Godot character (the desktop pet)
      • the chat tray (system-tray icon)
      • the chat window (PyQt chat box)
      • the dashboard webpage (Streamlit, opens in your browser)

  Double-click it (via a shortcut) or run from PowerShell. Already-running pieces
  are skipped, so it's safe to run again.

  Switches:  -NoGodot  -NoTray  -NoChat  -NoDashboard  -NoHealth
#>
param(
    [switch]$NoGodot,
    [switch]$NoTray,
    [switch]$NoChat,
    [switch]$NoDashboard,
    [switch]$NoHealth
)

$ErrorActionPreference = "SilentlyContinue"

# --- Config (edit here if a path ever moves) -------------------------------
$ProjectRoot = "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion"
$GodotExe    = "C:\Users\Tench\Documents\Godot_v4.6.3-stable_mono_win64\Godot_v4.6.3-stable_mono_win64\Godot_v4.6.3-stable_mono_win64.exe"
$BrainPy     = "$ProjectRoot\brain\.venv\Scripts\python.exe"
$DashUrl     = "http://127.0.0.1:8501"

# PC1 clients reach the PC2 backend through the bridge tunnels at localhost.
$env:ARIA_BRAIN_HOST    = "127.0.0.1"
$env:TTS_URL            = "http://127.0.0.1:5003/tts"
$env:LM_STUDIO_BASE_URL = "http://127.0.0.1:1010/v1"

function Test-Running([string]$pattern) {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match [regex]::Escape($pattern) } |
        Select-Object -First 1
}

function Launch([string]$name, [string]$exe, [string[]]$argList, [string]$cwd, [string]$runningPattern) {
    if (Test-Running $runningPattern) { Write-Host "  $name : already running" -ForegroundColor DarkGray; return }
    if (-not (Test-Path $exe)) { Write-Host "  $name : SKIP - not found: $exe" -ForegroundColor Yellow; return }
    Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $cwd | Out-Null
    Write-Host "  $name : launched" -ForegroundColor Green
}

Write-Host "=== Launching Aria front-end (PC1) ===" -ForegroundColor Cyan

# 0. Backend reachable? (warn only — the bridge tunnels point at PC2)
if (-not $NoHealth) {
    $h = & curl.exe -s --max-time 4 http://127.0.0.1:8770/health 2>$null
    if ($h -match '"status":"ok"') { Write-Host "  backend brain : UP" -ForegroundColor Green }
    else { Write-Host "  backend brain : NOT RESPONDING - is PC2 on + LM Studio loaded? (launching anyway)" -ForegroundColor Yellow }
}

# 1. Godot character
if (-not $NoGodot)     { Launch "godot"     $GodotExe @("--path", "$ProjectRoot\aria") "$ProjectRoot\aria" "AriaAssistantAppIKdiffusion\aria" }

# 2. Chat tray
if (-not $NoTray)      { Launch "tray"      $BrainPy  @("-m", "aria_brain.tray")        "$ProjectRoot\brain" "aria_brain.tray" }

# 3. Chat window
if (-not $NoChat)      { Launch "chat"      $BrainPy  @("-m", "aria_brain.chat_window") "$ProjectRoot\brain" "aria_brain.chat_window" }

# 4. Dashboard webpage (Streamlit) + open browser
if (-not $NoDashboard) {
    Launch "dashboard" $BrainPy @("-m", "streamlit", "run", "$ProjectRoot\brain\dashboard.py",
                                  "--server.port", "8501", "--server.headless", "true") "$ProjectRoot\brain" "streamlit run"
    Start-Sleep -Seconds 3
    Start-Process $DashUrl   # open the dashboard in the default browser
    Write-Host "  dashboard : opened $DashUrl" -ForegroundColor Green
}

Write-Host "=== Aria front-end up. Services keep running after this window closes. ===" -ForegroundColor Cyan
