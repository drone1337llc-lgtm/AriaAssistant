# sync_to_aipc.ps1
# Push AI-PC server files from PC1 (this machine) to PC2 (192.168.68.88).
# Run directly or double-click sync_to_aipc.bat.
#
# First-time setup: run these as admin on PC2 to enable SSH:
#   Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
#   Start-Service sshd
#   Set-Service -Name sshd -StartupType Automatic

param(
    [string]$RemoteUser = "Tench",
    [string]$RemoteHost = "192.168.68.88",
    [string]$RemoteDir  = "C:/Users/Tench/Documents/AI Learning/astro_assistant",
    [string]$LocalDir   = $PSScriptRoot
)

# Files that live and run on the AI PC.
# Add or remove entries here as the project grows.
$files = @(
    "server.py",
    "transport.py",
    "tools.py",
    "lmstudio_client.py",
    "config.json"
)

Write-Host ""
Write-Host "=== Aria AI-PC Sync ===" -ForegroundColor Cyan
Write-Host "  From : $LocalDir"
Write-Host "  To   : ${RemoteUser}@${RemoteHost}:${RemoteDir}"
Write-Host ""

# Ensure the remote directory exists before copying (2>nul silences "already exists" noise).
$remoteWin = $RemoteDir -replace '/', '\'
ssh -o StrictHostKeyChecking=no "${RemoteUser}@${RemoteHost}" "cmd /c mkdir `"$remoteWin`" 2>nul" | Out-Null

$ok = 0; $fail = 0; $skip = 0
foreach ($f in $files) {
    $src = Join-Path $LocalDir $f
    if (-not (Test-Path $src)) {
        Write-Host "  [skip] $f  (not found locally)" -ForegroundColor Yellow
        $skip++
        continue
    }
    # Wrap remote path in quotes to handle spaces ("AI Learning")
    $dst = "${RemoteUser}@${RemoteHost}:`"${RemoteDir}/${f}`""
    Write-Host "  $f  →  " -NoNewline
    # -o StrictHostKeyChecking=no avoids the interactive "trust this host?" prompt
    # on a private home network — safe to leave on.
    scp -q -o StrictHostKeyChecking=no "$src" "$dst" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK" -ForegroundColor Green
        $ok++
    } else {
        Write-Host "FAILED (scp exit $LASTEXITCODE)" -ForegroundColor Red
        $fail++
    }
}

Write-Host ""
Write-Host "Done: $ok copied, $skip skipped, $fail failed." -ForegroundColor $(if ($fail -gt 0) {"Red"} else {"Green"})
if ($fail -gt 0) { exit 1 }
