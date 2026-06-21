# sync-to-pc2.ps1  -  copies Aria source files to PC 2 (192.168.68.88).
#
# What it syncs (source only, no venvs/caches):
#   brain/                          Python brain server
#   watchdog/                       CrewAI watchdog
#   motion_lib/                     Motion server source
#   FloodDiffusion/                 Motion diffusion model source
#   scripts/                        Deployment scripts (including this one)
#
#   D:\...\Coqui-TTS-XTTS-v2-\scripts\          TTS server + helpers (~100 KB)
#   D:\...\Coqui-TTS-XTTS-v2-\data\jessica_voice\   Reference clips for voice conditioning (~45 MB)
#   D:\...\Coqui-TTS-XTTS-v2-\TTS\              TTS Python package source
#
# What it does NOT sync (too large):
#   aria/             Godot project (8+ GB) - PC 2 only needs an empty aria/ dir
#   Any .venv/        Venvs are created fresh on PC 2 by setup-pc2-services.ps1
#   .git/ .godot/     Not needed
#   logs/ chroma_local/  Machine-local data
#   Coqui run/        Model checkpoints (~7 GB) - copy ONCE manually via SCP:
#     scp -r "D:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\run\training" tench@192.168.68.88:"D:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\run\"
#
# Prerequisites:
#   - Passwordless SSH to PC 2 must be set up (run setup-ssh-to-ai-pc.ps1 first)
#   - Run this from a real PowerShell terminal (SSH needs interactive context)
#
# Usage:
#   .\scripts\sync-to-pc2.ps1
#   .\scripts\sync-to-pc2.ps1 -DryRun    # show what would be copied, don't transfer

param([switch]$DryRun)

$Src      = "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion"
$CoquiSrc = "D:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-"   # D: drive - the real trained TTS
$AIPc     = "192.168.68.88"
$User     = $env:USERNAME
$PC2Dst   = "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion"
$PC2Coqui = "$PC2Dst\Coqui-TTS-XTTS-v2-"   # in-project on PC 2 (C: drive, off the USB)
$Stage    = "$env:TEMP\aria_pc2_stage"
$CoquiStage = "$env:TEMP\aria_coqui_stage"
$ZipPath  = "$env:TEMP\aria_pc2_sync.zip"
$CoquiZip = "$env:TEMP\aria_coqui_sync.zip"

# Robocopy exit codes 0-7 are success (bit field: 1=copied, 2=extra, 4=mismatched, 8+=error)
function Invoke-Robocopy {
    param($From, $To, [string[]]$ExcludeDirs = @(), [string[]]$ExcludeFiles = @())
    $args_ = @($From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/R:1", "/W:1")
    if ($ExcludeDirs.Count)  { $args_ += "/XD"; $args_ += $ExcludeDirs }
    if ($ExcludeFiles.Count) { $args_ += "/XF"; $args_ += $ExcludeFiles }
    & robocopy @args_
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE) from $From" }
}

# ---- 1. Build staging area -------------------------------------------------
Write-Host ""
Write-Host "=== Aria PC2 Sync ===" -ForegroundColor Cyan
Write-Host "Source : $Src"
Write-Host "Target : ${User}@${AIPc}:$PC2Dst"
Write-Host ""

if ($DryRun) { Write-Host "[DRY RUN - no files will be transferred]" -ForegroundColor Yellow; Write-Host "" }

Write-Host "Staging source files..." -ForegroundColor Yellow

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -Path $Stage -ItemType Directory -Force | Out-Null

$excludeVenv = @(".venv", "__pycache__", ".git", "logs", "chroma_local")
$excludeFiles = @("*.pyc", "*.log", "*.tmp", "aria_health.log")

# brain/ - the main Python server
Invoke-Robocopy "$Src\brain"     "$Stage\brain"     $excludeVenv $excludeFiles

# watchdog/ - CrewAI watchdog
if (Test-Path "$Src\watchdog") {
    Invoke-Robocopy "$Src\watchdog"  "$Stage\watchdog"  $excludeVenv $excludeFiles
}

# motion_lib/ and FloodDiffusion/ - already on PC 2 but sync for updates
if (Test-Path "$Src\motion_lib") {
    Invoke-Robocopy "$Src\motion_lib"    "$Stage\motion_lib"    $excludeVenv $excludeFiles
}
if (Test-Path "$Src\FloodDiffusion") {
    Invoke-Robocopy "$Src\FloodDiffusion" "$Stage\FloodDiffusion" $excludeVenv $excludeFiles
}

# scripts/ - deployment scripts including this one
Invoke-Robocopy "$Src\scripts"   "$Stage\scripts"   @() $excludeFiles

$stagedFiles = (Get-ChildItem $Stage -Recurse -File).Count
$stagedMB    = [math]::Round(
    (Get-ChildItem $Stage -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host "Project staged: $stagedFiles files  ($stagedMB MB)" -ForegroundColor Green

# ---- 1b. Stage Coqui TTS (scripts + data only - NOT the ~7 GB model .pth files) ----------
Write-Host ""
Write-Host "Staging Coqui TTS (scripts + voice data)..." -ForegroundColor Yellow

if (Test-Path $CoquiStage) { Remove-Item $CoquiStage -Recurse -Force }
New-Item -Path $CoquiStage -ItemType Directory -Force | Out-Null

if (Test-Path $CoquiSrc) {
    # scripts/ - tts_server_jessica.py and helpers
    Invoke-Robocopy "$CoquiSrc\scripts" "$CoquiStage\scripts" @("__pycache__","my_voice_recordings") $excludeFiles
    # data/jessica_voice/ - reference clips for voice conditioning (45 MB)
    if (Test-Path "$CoquiSrc\data\jessica_voice") {
        Invoke-Robocopy "$CoquiSrc\data\jessica_voice" "$CoquiStage\data\jessica_voice" @("__pycache__") $excludeFiles
    }
    # TTS Python package source (needed for sys.path import in tts_server_jessica.py)
    if (Test-Path "$CoquiSrc\TTS") {
        Invoke-Robocopy "$CoquiSrc\TTS" "$CoquiStage\TTS" @("__pycache__",".venv","dist","build","*.egg-info") $excludeFiles
    }
    # Root-level packaging files required for 'pip install -e .' on PC 2
    foreach ($f in @("setup.py", "setup.cfg", "pyproject.toml", "requirements.txt", "MANIFEST.in")) {
        if (Test-Path "$CoquiSrc\$f") {
            Copy-Item "$CoquiSrc\$f" "$CoquiStage\$f" -Force
        }
    }
    $coquiFiles = (Get-ChildItem $CoquiStage -Recurse -File).Count
    $coquiMB    = [math]::Round(
        (Get-ChildItem $CoquiStage -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    Write-Host "Coqui TTS staged: $coquiFiles files  $coquiMB MB" -ForegroundColor Green
} else {
    Write-Host "Coqui TTS not found at $CoquiSrc - skipping." -ForegroundColor DarkGray
    Write-Host "  (TTS server will not work on PC 2 until the model is copied manually)"
}

if ($DryRun) {
    Write-Host ""
    Write-Host "Dry run complete."
    Write-Host "  Project: $stagedMB MB -> ${User}@${AIPc}:$PC2Dst"
    Write-Host "  Coqui  : $coquiMB MB -> ${User}@${AIPc}:$PC2Coqui"
    Write-Host ""
    Write-Host "Model files (copy ONCE manually, ~7 GB):"
    Write-Host "  scp -r `"$CoquiSrc\run\training`" `"${User}@${AIPc}:$PC2Coqui\run\`""
    exit 0
}

# ---- 2. Compress -----------------------------------------------------------
Write-Host ""
Write-Host "Compressing project files..." -ForegroundColor Yellow
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
$items = (Get-ChildItem -Path $Stage).FullName
Compress-Archive -Path $items -DestinationPath $ZipPath -CompressionLevel Optimal
$zipMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Host "Project zip: $zipMB MB" -ForegroundColor Green

Write-Host "Compressing Coqui TTS files..." -ForegroundColor Yellow
if (Test-Path $CoquiZip) { Remove-Item $CoquiZip -Force }
if ((Get-ChildItem $CoquiStage -Recurse -File).Count -gt 0) {
    $coquiItems = (Get-ChildItem -Path $CoquiStage).FullName
    Compress-Archive -Path $coquiItems -DestinationPath $CoquiZip -CompressionLevel Optimal
    $coquiZipMB = [math]::Round((Get-Item $CoquiZip).Length / 1MB, 1)
    Write-Host "Coqui zip: $coquiZipMB MB" -ForegroundColor Green
}

# ---- 3. Verify SSH ---------------------------------------------------------
Write-Host ""
Write-Host "Verifying SSH to PC 2..." -ForegroundColor Yellow
$ping = & ssh -o BatchMode=yes -o ConnectTimeout=5 "${User}@${AIPc}" "echo PONG" 2>&1
if ($LASTEXITCODE -ne 0 -or $ping -notmatch "PONG") {
    Write-Host "SSH not working. Run setup-ssh-to-ai-pc.ps1 first." -ForegroundColor Red
    Write-Host "(JetKVM fallback: http://192.168.68.122)"
    exit 1
}
Write-Host "SSH OK" -ForegroundColor Green

# ---- 4. Upload via SCP -----------------------------------------------------
Write-Host ""
Write-Host "Uploading project $zipMB MB to PC 2..." -ForegroundColor Yellow
$remoteZip = "C:\Users\$User\aria_sync.zip"
& scp -o BatchMode=yes "$ZipPath" "${User}@${AIPc}:$remoteZip"
if ($LASTEXITCODE -ne 0) { Write-Host "SCP upload failed." -ForegroundColor Red; exit 1 }
Write-Host "Upload OK" -ForegroundColor Green

$remoteCoquiZip = ""
if (Test-Path $CoquiZip) {
    Write-Host "Uploading Coqui TTS $coquiZipMB MB to PC 2..." -ForegroundColor Yellow
    $remoteCoquiZip = "C:\Users\$User\aria_coqui_sync.zip"
    & scp -o BatchMode=yes "$CoquiZip" "${User}@${AIPc}:$remoteCoquiZip"
    if ($LASTEXITCODE -ne 0) { Write-Host "Coqui SCP upload failed." -ForegroundColor Red; exit 1 }
    Write-Host "Coqui upload OK" -ForegroundColor Green
}

# ---- 5. Extract on PC 2 ----------------------------------------------------
Write-Host ""
Write-Host "Extracting on PC 2..." -ForegroundColor Yellow

# Build the PowerShell block to run on PC2, then Base64-encode it so SSH/cmd.exe
# quoting doesn't corrupt it.  -EncodedCommand bypasses all shell escaping.
$psLines  = @()
$psLines += "if (-not (Test-Path '$PC2Dst')) { New-Item -Path '$PC2Dst' -ItemType Directory -Force | Out-Null }"
$psLines += "Expand-Archive -Path '$remoteZip' -DestinationPath '$PC2Dst' -Force"
$psLines += "if (-not (Test-Path '$PC2Dst\aria')) { New-Item -Path '$PC2Dst\aria' -ItemType Directory -Force | Out-Null }"
$psLines += "Remove-Item '$remoteZip' -Force"
if ($remoteCoquiZip -ne "") {
    $psLines += "if (-not (Test-Path '$PC2Coqui')) { New-Item -Path '$PC2Coqui' -ItemType Directory -Force | Out-Null }"
    $psLines += "Expand-Archive -Path '$remoteCoquiZip' -DestinationPath '$PC2Coqui' -Force"
    $psLines += "Remove-Item '$remoteCoquiZip' -Force"
}
$psLines += "Write-Host 'Extraction complete'"
$psScript = $psLines -join "`n"
$encoded  = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($psScript))

& ssh -o BatchMode=yes "$User@$AIPc" "powershell -NoProfile -NonInteractive -EncodedCommand $encoded"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Extraction may have had issues - verify on PC 2." -ForegroundColor Yellow
} else {
    Write-Host "Extraction OK" -ForegroundColor Green
}

# ---- Done ------------------------------------------------------------------
Write-Host ""
Write-Host "=== Sync complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next: run  .\scripts\setup-pc2-services.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "Model files NOT synced (~7 GB - copy once if not already on PC 2):" -ForegroundColor Yellow
Write-Host "  scp -r `"$CoquiSrc\run\training`" `"${User}@${AIPc}:$PC2Coqui\run\`""
