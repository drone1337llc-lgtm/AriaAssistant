<#
  Ensure LM Studio's local server is up on :1010  --  run on PC2 (AIassistant).

  Uses LM Studio's `lms` CLI to start the server headless (no GUI needed) and
  preload the always-used small models. The heavy coder/vision models load
  on-demand (Just-In-Time) so the 24 GB card isn't over-committed.

  Intended to run at logon (see registration one-liner in the comments below),
  so the brain always finds LM Studio waiting on :1010.

  NOTE: model identifiers below must match what `lms ls` shows. If a load fails
  with "model not found", run `lms ls` and copy the exact key in.
#>
$ErrorActionPreference = "SilentlyContinue"

# --- Locate the lms CLI (ships with LM Studio) -----------------------------
$lms = (Get-Command lms -ErrorAction SilentlyContinue).Source
if (-not $lms) { $lms = "$env:USERPROFILE\.lmstudio\bin\lms.exe" }
if (-not (Test-Path $lms)) {
    Write-Host "[lmstudio] lms CLI not found. Open LM Studio once and enable the CLI" -ForegroundColor Yellow
    Write-Host "           (or run:  npx lmstudio install-cli  ), then re-run this script." -ForegroundColor Yellow
    exit 1
}

# --- Start the server on the port the brain expects ------------------------
Write-Host "[lmstudio] starting local server on :1010 ..."
& $lms server start --port 1010

# --- Preload the always-on small models; others JIT on first request -------
# (Enable "Just-In-Time model loading" in LM Studio settings so the coder/vision
#  models auto-load when the brain requests them.)
$preload = @(
    "humanish-roleplay-llama-3.1-8b-i1",          # chat
    "text-embedding-qwen3-embedding-0.6b"         # embeddings
)
foreach ($m in $preload) {
    Write-Host "[lmstudio] loading $m ..."
    & $lms load $m --gpu max -y
}

& $lms ps   # show what's loaded
Write-Host "[lmstudio] ready on http://127.0.0.1:1010" -ForegroundColor Green

# ---------------------------------------------------------------------------
# To run this automatically every time PC2 logs in, register a logon task once
# (elevated PowerShell on PC2):
#
#   $f = "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\scripts\start-lmstudio-pc2.ps1"
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" `
#          -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$f`""
#   $t = New-ScheduledTaskTrigger -AtLogOn
#   Register-ScheduledTask -TaskName "AriaLMStudio" -Action $a -Trigger $t -RunLevel Highest -Force
#
# Alternative (no script): in LM Studio settings turn on "Run on login" +
# "Start server on app launch" (port 1010) + "Just-In-Time model loading".
# ---------------------------------------------------------------------------
