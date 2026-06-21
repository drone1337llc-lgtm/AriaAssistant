#!/usr/bin/env pwsh
# Setup ChromaDB server on PC 2.
# Run this once on PC 2 (192.168.68.88) to install + start ChromaDB as a background service.
#
# After this script runs:
#   - ChromaDB listens on http://192.168.68.88:8000
#   - Auto-starts on boot (Windows Scheduled Task, "At startup")
#   - Data persisted under C:\chroma_data\
#
# Tested on: Windows 11, Python 3.12, uv 0.11+
#
# To run from PC 1 (this script assumes you're already on PC 2 — copy it over or RDP):
#   iwr -useb https://your.host/this_script.ps1 | iex    # OR
#   .\setup_chromadb_pc2.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== ChromaDB PC 2 setup ===" -ForegroundColor Cyan
Write-Host "This installs ChromaDB + starts it as a scheduled task on port 8000."

# 1. Install Python deps for the ChromaDB service (separate venv to keep it clean)
$ChromaDir = "C:\chroma"
$VenvDir = "$ChromaDir\.venv"
$DataDir = "C:\chroma_data"

if (-not (Test-Path $ChromaDir)) {
    New-Item -Path $ChromaDir -ItemType Directory -Force | Out-Null
}

# 2. Find uv
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    iwr -useb https://astral.sh/uv/install.ps1 | iex
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
}
if (-not $uv) {
    throw "uv not found on PATH. Install from https://astral.sh/uv first."
}

# 3. Create venv + install chromadb
Write-Host "Creating venv at $VenvDir..." -ForegroundColor Yellow
& $uv venv $VenvDir --python 3.12
# NOTE: chromadb >=0.6 folded the server into the base package; the old
# [server] extra no longer exists, so install plain chromadb.
& $uv pip install --python "$VenvDir\Scripts\python.exe" "chromadb>=0.5,<1.0" "pydantic>=2.6,<3.0"

# 4. Create the data directory
if (-not (Test-Path $DataDir)) {
    New-Item -Path $DataDir -ItemType Directory -Force | Out-Null
}

# 5. Create a tiny wrapper script that chromadb's CLI uses to start the server
$WrapperScript = "$ChromaDir\run_chroma.ps1"
@"
# ChromaDB server wrapper
`$ErrorActionPreference = "Stop"
& "$VenvDir\Scripts\chroma.exe" run --host 0.0.0.0 --port 8000 --path "$DataDir" 2>&1 | Tee-Object -FilePath "$ChromaDir\chroma.log"
"@ | Out-File -FilePath $WrapperScript -Encoding utf8

# 6. Schedule it at startup
$TaskName = "ChromaDB-AriaBrain"
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Scheduled task '$TaskName' already exists, removing..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -File `"$WrapperScript`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Description "ChromaDB server for Aria Brain memory (port 8000)"

# 7. Start it now too (don't wait for reboot)
Write-Host "Starting ChromaDB now..." -ForegroundColor Yellow
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile", "-WindowStyle", "Hidden", "-File", "`"$WrapperScript`"" -WindowStyle Hidden

# 8. Wait + verify
Write-Host "Waiting for ChromaDB to come up on port 8000..." -ForegroundColor Yellow
$up = $false
for ($i = 1; $i -le 15; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/heartbeat" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) {
            $up = $true
            break
        }
    } catch {
        # not up yet
    }
}

if ($up) {
    Write-Host ""
    Write-Host "SUCCESS: ChromaDB is running on http://0.0.0.0:8000" -ForegroundColor Green
    Write-Host "  data dir: $DataDir"
    Write-Host "  log file: $ChromaDir\chroma.log"
    Write-Host "  scheduled task: $TaskName (starts on boot)"
    Write-Host ""
    Write-Host "From PC 1, the Aria Brain will auto-discover it via CHROMADB_URL=http://192.168.68.88:8000" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "WARNING: ChromaDB didn't respond within 30s. Check $ChromaDir\chroma.log" -ForegroundColor Red
}