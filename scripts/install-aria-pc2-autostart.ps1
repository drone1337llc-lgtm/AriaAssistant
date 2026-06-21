<#
.SYNOPSIS
  Make the Aria PC2 backend persistent. RUN THIS ON PC 2, in an ELEVATED
  (Administrator) PowerShell.

.DESCRIPTION
  Registers a Scheduled Task that launches aria-pc2-supervisor.ps1 at logon, so
  the brain / TTS / motion services come up automatically and stay up for as
  long as PC 2 is on. The task runs in the interactive user session (required
  for GPU access by TTS/motion and to share the desktop with LM Studio), at
  highest privileges, and restarts if it ever exits.

  ChromaDB keeps its own SYSTEM auto-start task (from setup_chromadb_pc2.ps1),
  so it starts before logon. Pass -WithChroma here only if you did NOT run that
  script and want the supervisor to manage ChromaDB too.

  For a truly hands-off "PC on => Aria ready" box, also enable autologon on PC2
  (see the note this script prints at the end).

.USAGE
  # on PC 2, elevated:
  .\install-aria-pc2-autostart.ps1
  .\install-aria-pc2-autostart.ps1 -WithTelegram -WithWatchdog
  .\install-aria-pc2-autostart.ps1 -Uninstall
#>
param(
    [switch]$WithChroma,
    [switch]$WithTelegram,
    [switch]$WithWatchdog,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$TaskName = "AriaPC2Backend"
$Root     = "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion"
$Sup      = "$Root\scripts\aria-pc2-supervisor.ps1"

# --- elevation check --------------------------------------------------------
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "This must be run as Administrator (registers a scheduled task)." -ForegroundColor Red
    Write-Host "Right-click PowerShell -> Run as administrator, then re-run." -ForegroundColor Yellow
    exit 1
}

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'." -ForegroundColor Green
    } else {
        Write-Host "No task '$TaskName' found." -ForegroundColor Yellow
    }
    return
}

if (-not (Test-Path $Sup)) {
    Write-Host "Supervisor not found at $Sup" -ForegroundColor Red
    Write-Host "Make sure the repo (with scripts\aria-pc2-supervisor.ps1) is synced to PC 2." -ForegroundColor Yellow
    exit 1
}

# --- safety: this must run on the AI box (PC2), NOT the client (PC1) --------
# PC1's bridge config has a 'tunnels:' section; PC2's does not. If we see
# tunnels, we're on the client and would crash-loop a brain that can't bind the
# port the bridge tunnel already owns. Refuse.
$bridgeCfg = Join-Path $env:USERPROFILE ".bridge\config.yaml"
if ((Test-Path $bridgeCfg) -and (Select-String -Path $bridgeCfg -SimpleMatch "tunnels:" -Quiet)) {
    Write-Host "ABORT: this machine's bridge config ($bridgeCfg) has 'tunnels:'," -ForegroundColor Red
    Write-Host "which means it's the CLIENT (PC1). The backend supervisor must run on" -ForegroundColor Yellow
    Write-Host "PC2 (the AI box). RDP/JetKVM into PC2 and run this there." -ForegroundColor Yellow
    exit 1
}

# --- build supervisor argument list -----------------------------------------
$supArgs = @()
if ($WithChroma)   { $supArgs += "-WithChroma" }
if ($WithTelegram) { $supArgs += "-WithTelegram" }
if ($WithWatchdog) { $supArgs += "-WithWatchdog" }
$argLine = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Sup`" $($supArgs -join ' ')"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argLine

# At logon of THIS user (interactive session => GPU works).
$me      = "$env:USERDOMAIN\$env:USERNAME"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $me

$principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Highest

# Keep it alive: no time limit, restart if it stops, start when available.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force `
    -Description "Aria backend supervisor (brain/TTS/motion) ? keeps services alive while PC2 is on." | Out-Null

Write-Host "Registered scheduled task '$TaskName' (runs aria-pc2-supervisor.ps1 at logon)." -ForegroundColor Green
Write-Host ""
Write-Host "Start it now without waiting for a re-logon:" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
Write-Host ""
Write-Host "Check what it's doing:" -ForegroundColor Cyan
Write-Host "  Get-Content `"$Root\logs\pc2\supervisor.log`" -Tail 30 -Wait"
Write-Host "  powershell -File `"$Sup`" -Status      # quick port snapshot"
Write-Host ""
Write-Host "For a hands-off 'PC on => Aria ready' box, enable autologon on PC 2 so" -ForegroundColor DarkGray
Write-Host "the logon trigger fires after a reboot without you typing a password:" -ForegroundColor DarkGray
Write-Host "  run  netplwiz  -> uncheck 'Users must enter a user name and password'." -ForegroundColor DarkGray
