# setup-ssh-to-ai-pc.ps1  -  one-time setup so passwordless SSH works from PC 1 to PC 2.
#
# Run once. After this, ssh user@192.168.68.88 "echo ok" will work without a password.
#
# What it does:
#   1. Generate an ed25519 keypair at ~/.ssh/id_ed25519 (no passphrase)
#   2. Copy the public key to PC 2's authorized_keys (will prompt for the password once)
#   3. Verify passwordless login works

$AIPc = "192.168.68.88"

Write-Host "=== Setup passwordless SSH from PC 1 to PC 2 ($AIPc) ===" -ForegroundColor Cyan
Write-Host ""
$user = Read-Host "PC 2 username (same as your Windows login is a safe bet)"

# 1. Generate keypair
$sshDir = Join-Path $env:USERPROFILE ".ssh"
if (-not (Test-Path $sshDir)) { New-Item -Path $sshDir -ItemType Directory -Force | Out-Null }
$keyPath = Join-Path $sshDir "id_ed25519"
$pubPath = "$keyPath.pub"
if (Test-Path $keyPath) {
    Write-Host "Key already exists: $keyPath (skipping generate)" -ForegroundColor Yellow
} else {
    Write-Host "Generating ed25519 keypair (no passphrase)..." -ForegroundColor Yellow
    & ssh-keygen -t ed25519 -f $keyPath -N '""'
}

# 2. Get public key content
$pubKey = Get-Content $pubPath -Raw
Write-Host ""
Write-Host "Public key (will be appended to PC 2's authorized_keys):"
Write-Host $pubKey -ForegroundColor DarkGray

# 3. Copy to PC 2 (will prompt for password once)
Write-Host ""
Write-Host "Copying key to ${user}@${AIPc}..." -ForegroundColor Yellow
Write-Host ">>> You will be prompted for ${user}'s password ONE time <<<" -ForegroundColor Magenta

# PC 2 is Windows, so use PowerShell commands via SSH rather than bash/chmod.
# Base64-encode the key to avoid all quoting issues when embedding it in a
# remote PowerShell -Command string.
$b64Key = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pubKey.Trim()))
$installPs = @"
`$d = "`$env:USERPROFILE\.ssh";
[IO.Directory]::CreateDirectory(`$d) | Out-Null;
`$kf = "`$d\authorized_keys";
`$key = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$b64Key'));
`$existing = if (Test-Path `$kf) { Get-Content `$kf -Raw } else { '' };
if (`$existing -notmatch [regex]::Escape(`$key.Trim())) { Add-Content -Path `$kf -Value `$key; Write-Host 'key installed' } else { Write-Host 'key already present' }
"@
# Collapse to a single line for the SSH command argument
$oneLiner = $installPs -replace "`r?`n", " "
$exitCode = 0
& ssh -o StrictHostKeyChecking=accept-new "${user}@${AIPc}" "powershell -NoProfile -NonInteractive -Command `"$oneLiner`""
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "PowerShell install failed (exit $exitCode). Trying bash fallback (for Git Bash / WSL shells)..." -ForegroundColor Yellow
    $bashCmd = "mkdir -p ~/.ssh && echo '$($pubKey.Trim())' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo 'key installed'"
    & ssh -o StrictHostKeyChecking=accept-new "${user}@${AIPc}" "$bashCmd"
}

# 4. Verify
Write-Host ""
Write-Host "Verifying passwordless login..." -ForegroundColor Yellow
$test = ssh -o BatchMode=yes -o ConnectTimeout=5 "${user}@${AIPc}" "echo OK_$([System.Guid]::NewGuid().ToString('N').Substring(0,8))" 2>&1
if ($LASTEXITCODE -eq 0 -and $test -like "OK_*") {
    Write-Host ""
    Write-Host "SUCCESS: passwordless SSH works." -ForegroundColor Green
    Write-Host "You can now run: ssh ${user}@${AIPc} 'your-command-here'"
} else {
    Write-Host ""
    Write-Host "FAILED: $test" -ForegroundColor Red
    Write-Host "Things to check:"
    Write-Host "  - OpenSSH Server is installed + running on PC 2 (Settings > Apps > Optional Features > OpenSSH Server)"
    Write-Host "  - Firewall allows port 22 on PC 2"
    Write-Host "  - Your Windows username + password work for the user '$user'"
}