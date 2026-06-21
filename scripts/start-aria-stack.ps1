# start-aria-stack.ps1  -  orchestrator for the Aria stack.
#
# Manages N processes locally + M processes on the AI PC (192.168.68.88).
# Usage:
#   .\start-aria-stack.ps1 start        # launch everything in dependency order
#   .\start-aria-stack.ps1 stop         # kill everything (graceful where possible)
#   .\start-aria-stack.ps1 restart      # stop then start
#   .\start-aria-stack.ps1 status       # which are running, which are dead
#   .\start-aria-stack.ps1 tail         # tail the log
#   .\start-aria-stack.ps1 watch        # foreground: restart any crashed process
#
# PC split:
#   PC 1 (this machine) - display-only: Godot, tray, chat window.
#   PC 2 (192.168.68.88) - AI box: everything compute-heavy.
#
# Edit the $Processes array below to match your stack.

$ErrorActionPreference = "Continue"

# ---- Config ---------------------------------------------------------------

$ProjectRoot = "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion"
$LogFile = Join-Path $ProjectRoot "logs\aria-stack.log"
$WatchIntervalSec = 10
$AIPc = "192.168.68.88"
$AIPcUser = $env:USERNAME
# JetKVM (KVM-over-IP fallback for PC 2):
#   Web UI  : http://192.168.68.122
#   SSH     : ssh root@192.168.68.122  (no password, PC 1 only)
# Use it if SSH to PC 2 stops working — gives full console/display access to PC 2.

# Shorthand for the same root path on PC 2 (same username, same path).
$PC2Root = "C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion"

# Each process: @{ name, kind ("local"|"remote"), path, args, cwd, env, ssh_cmd, match, dependsOn }
# - env: hashtable of env vars to set before spawning a local process (child inherits them).
# - match: override string used by Test-Local (default = proc.name).
$Processes = @(

    # ---- PC 2  -  AI box (192.168.68.88) ----
    # Run setup-ssh-to-ai-pc.ps1 once to enable passwordless SSH.
    # Run scripts/setup-pc2-services.ps1 once to create all venvs + firewall rules on PC 2.

    @{
        name      = "chromadb"
        kind      = "remote"
        # ChromaDB is installed at C:\chroma on PC 2 (not in the project dir).
        ssh_cmd   = "cd C:\chroma && start /b C:\chroma\.venv\Scripts\python.exe -m chromadb.cli run --host 0.0.0.0 --port 8000 --path C:\chroma_data"
        dependsOn = @()
        notes     = "ChromaDB on PC2:8000 - run brain/setup_chromadb_pc2.ps1 first"
    }
    @{
        name      = "tts_server"
        kind      = "remote"
        # Runs from the D: drive Coqui TTS install — ROOT in the script resolves to
        # D:\Users\Tench\Documents\Coqui-TTS-XTTS-v2- so model paths and reference
        # clips (data/jessica_voice/wavs/) are found correctly.
        # setup-pc2-services.ps1 creates the .venv there and installs TTS into it.
        # NOTE: model files (~7 GB) must be copied to PC2 first — see setup-pc2-services.ps1
        ssh_cmd   = "cd /d $PC2Root\Coqui-TTS-XTTS-v2- && start /b $PC2Root\Coqui-TTS-XTTS-v2-\.venv\Scripts\python.exe scripts\tts_server_jessica.py"
        dependsOn = @()
        notes     = "XTTS-v2 Jessica fine-tune on PC2:5003 (HEAVY GPU) - run setup-pc2-services.ps1 first"
    }
    @{
        name      = "brain"
        kind      = "remote"
        # Override ARIA_BRAIN_HOST so it binds 0.0.0.0 (reachable from PC 1).
        # LM Studio and ChromaDB are localhost from PC 2's perspective.
        ssh_cmd   = "set ARIA_BRAIN_HOST=0.0.0.0 && set LM_STUDIO_BASE_URL=http://127.0.0.1:1010/v1 && set CHROMADB_URL=http://127.0.0.1:8000 && set TTS_URL=http://127.0.0.1:5003/tts && cd $PC2Root\brain && start /b $PC2Root\brain\.venv\Scripts\python.exe -m aria_brain.main"
        dependsOn = @("chromadb", "tts_server")
        notes     = "FastAPI on PC2:8770 (personality, memory, mood, reflection, TTS, voice, telegram)"
    }
    @{
        name      = "telegram_bot"
        kind      = "remote"
        ssh_cmd   = "cd $PC2Root\brain && start /b $PC2Root\brain\.venv\Scripts\python.exe -m aria_brain.telegram_bot"
        dependsOn = @("brain")
        notes     = "Telegram bot on PC2 - needs TELEGRAM_BOT_TOKEN in brain/.env"
    }
    @{
        name      = "watchdog"
        kind      = "remote"
        ssh_cmd   = "cd $PC2Root\watchdog && start /b $PC2Root\watchdog\.venv\Scripts\python.exe -m aisistant.main loop"
        dependsOn = @("brain")
        notes     = "CrewAI watchdog on PC2 (5 agents, 9 tools)"
    }
    @{
        name      = "motion_server"
        kind      = "remote"
        ssh_cmd   = "cd $PC2Root\motion_lib && start /b $PC2Root\motion_lib\.venv\Scripts\python.exe motion_server.py --port 8766"
        dependsOn = @()
        notes     = "Motion server on PC2:8766 (FloodDiffusion) - optional"
    }

    # ---- PC 1  -  display-only (Godot, tray, chat window) ----
    # Brain and TTS are on PC 2 - env vars below route these clients there.
    @{
        name      = "tray"
        kind      = "local"
        path      = "$ProjectRoot\brain\.venv\Scripts\python.exe"
        args      = @("-m","aria_brain.tray")
        cwd       = "$ProjectRoot\brain"
        env       = @{ ARIA_BRAIN_HOST = "127.0.0.1"; TTS_URL = "http://127.0.0.1:5003/tts" }  # via bridge tunnels -> PC2
        dependsOn = @("brain")
        notes     = "System tray icon on PC1 - talks to brain on PC2"
    }
    @{
        name      = "chat_window"
        kind      = "local"
        path      = "$ProjectRoot\brain\.venv\Scripts\python.exe"
        args      = @("-m","aria_brain.chat_window")
        cwd       = "$ProjectRoot\brain"
        env       = @{ ARIA_BRAIN_HOST = "127.0.0.1"; TTS_URL = "http://127.0.0.1:5003/tts" }  # via bridge tunnels -> PC2
        dependsOn = @("brain")
        notes     = "PyQt6 chat window on PC1 - talks to brain on PC2"
    }
    @{
        name      = "godot_aria"
        kind      = "local"
        path      = "C:\Users\Tench\Documents\Godot_v4.6.3-stable_mono_win64\Godot_v4.6.3-stable_mono_win64\Godot_v4.6.3-stable_mono_win64.exe"
        args      = @("--path", "$ProjectRoot\aria")
        cwd       = "$ProjectRoot\aria"
        match     = "AriaAssistantAppIKdiffusion"   # unique string in the --path arg
        dependsOn = @("brain")
        notes     = "Godot desktop pet on PC1 - connects to LM Studio on PC2 directly"
    }
)

# ---- Helpers --------------------------------------------------------------

function Write-Log {
    param([string]$msg)
    $ts = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    $line = "$ts`t$msg"
    $logDir = Split-Path $LogFile
    if (-not (Test-Path $logDir)) { New-Item -Path $logDir -ItemType Directory -Force | Out-Null }
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

function Test-Local {
    param($proc)
    # Use proc.match if present (for processes whose name won't appear in their command line),
    # otherwise fall back to proc.name.
    $matchStr = if ($proc.match) { $proc.match } else { $proc.name }
    foreach ($exe in @("python","Godot","Godot_v4.6.3-stable_mono_win64")) {
        $procs = Get-Process -Name $exe -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" -ErrorAction SilentlyContinue).CommandLine
            if ($cmd -and $cmd -match [regex]::Escape($matchStr)) { return $true }
        }
    }
    return $false
}

function Test-Remote {
    param([string]$name)
    $sshArgs = @("-o","BatchMode=yes","-o","ConnectTimeout=5","${AIPcUser}@${AIPc}","tasklist /FI ""IMAGENAME eq python.exe"" /NH")
    try {
        $out = & ssh @sshArgs 2>&1
        return $LASTEXITCODE -eq 0 -and $out -match "python\.exe"
    } catch {
        return $false
    }
}

function Start-Local {
    param($proc)
    if (Test-Local $proc) { Write-Log "[$($proc.name)] already running"; return }
    Write-Log "[$($proc.name)] starting (local)"
    try {
        # Per-process log files avoid file-lock contention from multiple Start-Process calls.
        $base   = $LogFile -replace "\.log$",""
        $outLog = "$base.$($proc.name).out.log"
        $errLog = "$base.$($proc.name).err.log"

        # Apply per-process env overrides so the child process inherits them.
        # dotenv (load_dotenv) does NOT override existing env vars, so these take
        # precedence over whatever is in brain/.env on disk.
        $saved = @{}
        if ($proc.env) {
            foreach ($k in $proc.env.Keys) {
                $saved[$k] = [System.Environment]::GetEnvironmentVariable($k, "Process")
                [System.Environment]::SetEnvironmentVariable($k, $proc.env[$k], "Process")
            }
        }

        $p = Start-Process -FilePath $proc.path -ArgumentList $proc.args `
                            -WorkingDirectory $proc.cwd -PassThru `
                            -RedirectStandardOutput $outLog -RedirectStandardError $errLog
        Write-Log "[$($proc.name)] started pid=$($p.Id)"

        # Restore env vars to avoid polluting subsequent processes.
        foreach ($k in $saved.Keys) {
            [System.Environment]::SetEnvironmentVariable($k, $saved[$k], "Process")
        }
    } catch { Write-Log "[$($proc.name)] FAILED: $($_.Exception.Message)" }
}

function Stop-Local {
    param($proc)
    Write-Log "[$($proc.name)] stopping (local)"
    $matchStr = if ($proc.match) { $proc.match } else { $proc.name }
    foreach ($exe in @("python","Godot","Godot_v4.6.3-stable_mono_win64")) {
        Get-Process -Name $exe -ErrorAction SilentlyContinue | Where-Object {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
            $cmd -and $cmd -match ([regex]::Escape($matchStr))
        } | ForEach-Object { try { $_ | Stop-Process -Force } catch {} }
    }
}

function Start-Remote {
    param($proc)
    if (Test-Remote $proc.name) { Write-Log "[$($proc.name)] already running (remote)"; return }
    Write-Log "[$($proc.name)] starting (remote)"
    try {
        $sshArgs = @("-o","BatchMode=yes","-o","ConnectTimeout=10","${AIPcUser}@${AIPc}", $proc.ssh_cmd)
        & ssh @sshArgs 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        if (Test-Remote $proc.name) { Write-Log "[$($proc.name)] started OK" }
        else { Write-Log "[$($proc.name)] may not have started - verify on PC 2" }
    } catch { Write-Log "[$($proc.name)] FAILED: $($_.Exception.Message)" }
}

function Stop-Remote {
    param($proc)
    Write-Log "[$($proc.name)] stopping (remote)"
    $sshArgs = @("-o","BatchMode=yes","-o","ConnectTimeout=5","${AIPcUser}@${AIPc}",
        "taskkill /F /FI ""WINDOWTITLE eq $($proc.name)*"" 2>nul & echo done")
    try { & ssh @sshArgs 2>&1 | Out-Null } catch {}
}

function Start-One {
    param($proc)
    # Non-recursive: just start this one process.
    # Cmd-Start and Cmd-Watch call this after ensuring deps are handled in order.
    # Log a warning (not a recursive start) if a dep somehow isn't up yet.
    foreach ($dep in $proc.dependsOn) {
        $depProc = $Processes | Where-Object { $_.name -eq $dep } | Select-Object -First 1
        if ($depProc) {
            $alive = if ($depProc.kind -eq "remote") { Test-Remote $depProc.name } else { Test-Local $depProc }
            if (-not $alive) {
                Write-Log "[$($proc.name)] WARNING: dependency '$dep' does not appear to be running yet"
            }
        }
    }
    if ($proc.kind -eq "remote") { Start-Remote $proc } else { Start-Local $proc }
}

function Stop-One {
    param($proc)
    if ($proc.kind -eq "remote") { Stop-Remote $proc } else { Stop-Local $proc }
}

# ---- Commands -------------------------------------------------------------

function Resolve-StartOrder {
    # Iterative topological sort — returns $Processes in dependency-safe order.
    # No recursion; handles any valid DAG up to $Processes.Count^2 iterations.
    $sorted   = [System.Collections.Generic.List[object]]::new()
    $pending  = [System.Collections.Generic.List[object]]::new()
    foreach ($p in $Processes) { $pending.Add($p) }
    $maxPass = $Processes.Count + 1
    for ($pass = 0; $pass -lt $maxPass -and $pending.Count -gt 0; $pass++) {
        $startedOne = $false
        foreach ($p in @($pending)) {
            $depsResolved = $true
            foreach ($dep in $p.dependsOn) {
                if (-not ($sorted | Where-Object { $_.name -eq $dep })) {
                    $depsResolved = $false; break
                }
            }
            if ($depsResolved) {
                $sorted.Add($p)
                $pending.Remove($p)
                $startedOne = $true
            }
        }
        if (-not $startedOne) { break }  # circular dep guard
    }
    # Append anything left (shouldn't happen with a valid dep graph)
    foreach ($p in $pending) { $sorted.Add($p) }
    return $sorted
}

function Cmd-Start {
    Write-Log "=== START ==="
    $order = Resolve-StartOrder
    foreach ($p in $order) { Start-One $p }
    Write-Log "=== START done ==="
}

function Cmd-Stop {
    Write-Log "=== STOP ==="
    $reversed = $Processes | Sort-Object @{Expression={ $_.dependsOn.Count }; Descending=$true}
    foreach ($p in $reversed) { Stop-One $p }
    Write-Log "=== STOP done ==="
}

function Cmd-Status {
    "=== STATUS @ $(Get-Date) ==="
    foreach ($p in $Processes) {
        $alive = if ($p.kind -eq "remote") { Test-Remote $p.name } else { Test-Local $p }
        $tag = if ($alive) { "[OK]  " } else { "[DEAD]" }
        "$tag $($p.name.PadRight(22)) $($p.kind.PadRight(7)) $($p.notes)"
    }
}

function Cmd-Tail {
    if (-not (Test-Path $LogFile)) { "no log yet"; return }
    Get-Content $LogFile -Tail 50 -Wait
}

function Cmd-Watch {
    Write-Log "=== WATCH mode (Ctrl-C to exit) ==="
    while ($true) {
        foreach ($p in $Processes) {
            $alive = if ($p.kind -eq "remote") { Test-Remote $p.name } else { Test-Local $p }
            if (-not $alive) {
                Write-Log "[$($p.name)] died - restarting"
                Start-One $p
            }
        }
        Start-Sleep -Seconds $WatchIntervalSec
    }
}

# ---- Entry ----------------------------------------------------------------

$cmd = $args[0]
if (-not $cmd) { $cmd = "status" }
$SinglePC = $args -contains "-SinglePC" -or $args -contains "--single-pc"
if ($SinglePC) {
    $before = $Processes.Count
    $Processes = $Processes | Where-Object { $_.kind -ne "remote" }
    $removed = $before - $Processes.Count
    Write-Host "[single-pc mode] filtered out $removed remote process(es)"
}
switch ($cmd) {
    "start"    { Cmd-Start }
    "stop"     { Cmd-Stop }
    "restart"  { Cmd-Stop; Start-Sleep -Seconds 2; Cmd-Start }
    "status"   { Cmd-Status }
    "tail"     { Cmd-Tail }
    "watch"    { Cmd-Watch }
    default    { "Usage: start | stop | restart | status | tail | watch  [-SinglePC]" }
}
