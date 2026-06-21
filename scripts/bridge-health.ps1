<#
.SYNOPSIS
  Health check for the Aria bridge mesh + PC2 service tunnels (run from PC1).

.DESCRIPTION
  Shows which mesh nodes are connected and probes each PC2 service THROUGH its
  bridge tunnel, so you see in one place whether the comms path is healthy.

  Tunnel verdicts:
    UP    - the service answered through the tunnel (real HTTP status)
    DOWN  - tunnel forwarded but PC2 service didn't answer (service not running)
    NOLISTEN - the local bridge tunnel isn't listening (bridge/config problem)

.USAGE
  .\bridge-health.ps1            # one-shot
  .\bridge-health.ps1 -Watch     # poll every 5s, flag flaps/changes (Ctrl-C to stop)
  .\bridge-health.ps1 -Watch -IntervalSec 10
#>
param(
    [switch]$Watch,
    [int]$IntervalSec = 5,
    [string]$GuiUrl = "http://localhost:8080"
)

$Tunnels = @(
    @{ name = "LM Studio"; port = 1010; url = "http://127.0.0.1:1010/v1/models" }
    @{ name = "Brain";     port = 8770; url = "http://127.0.0.1:8770/health" }
    @{ name = "TTS";       port = 5003; url = "http://127.0.0.1:5003/tts" }
    @{ name = "Motion";    port = 8766; url = "http://127.0.0.1:8766/" }
    @{ name = "Astro";     port = 8765; url = "http://127.0.0.1:8765/" }
)

function Get-Mesh {
    try {
        $j = (Invoke-WebRequest -UseBasicParsing "$GuiUrl/api/peers" -TimeoutSec 4).Content | ConvertFrom-Json
        return $j
    } catch { return $null }
}

function Test-Tunnel {
    param($t)
    # Is the local listener even up?
    $listen = Test-NetConnection -ComputerName 127.0.0.1 -Port $t.port -WarningAction SilentlyContinue
    if (-not $listen.TcpTestSucceeded) { return "NOLISTEN" }
    $code = & curl.exe -s -o NUL -w "%{http_code}" --max-time 4 $t.url 2>$null
    if ($code -and $code -ne "000") { return "UP" } else { return "DOWN" }
}

function Show-Once {
    $mesh = Get-Mesh
    Write-Host ("=== Bridge health @ {0} ===" -f (Get-Date -Format "HH:mm:ss"))
    if ($null -eq $mesh) {
        Write-Host "  MESH: cannot reach local bridge GUI at $GuiUrl" -ForegroundColor Red
    } else {
        foreach ($p in $mesh) {
            $label = if ($p.self) { "$($p.key) (this node)" } else { $p.key }
            if ($p.self) {
                Write-Host ("  NODE  {0,-28} self" -f $label) -ForegroundColor Gray
            } elseif ($p.connected) {
                Write-Host ("  NODE  {0,-28} connected" -f $label) -ForegroundColor Green
            } else {
                Write-Host ("  NODE  {0,-28} OFFLINE" -f $label) -ForegroundColor Red
            }
        }
    }
    foreach ($t in $Tunnels) {
        $v = Test-Tunnel $t
        $color = switch ($v) { "UP" { "Green" } "DOWN" { "Yellow" } default { "Red" } }
        Write-Host ("  TUNL  {0,-12} :{1,-5} {2}" -f $t.name, $t.port, $v) -ForegroundColor $color
    }
}

if (-not $Watch) { Show-Once; return }

# Watch mode: compact one-line state, flag any change.
Write-Host "Watching bridge mesh + tunnels every ${IntervalSec}s. Ctrl-C to stop." -ForegroundColor Cyan
$last = ""
while ($true) {
    $mesh = Get-Mesh
    $meshStr = if ($null -eq $mesh) { "MESH:DOWN" } else {
        ($mesh | Where-Object { -not $_.self } | ForEach-Object {
            "{0}={1}" -f $_.key.Split('.')[-1], ($(if ($_.connected) { "up" } else { "DOWN" }))
        }) -join " "
    }
    $tunStr = ($Tunnels | ForEach-Object { "{0}:{1}" -f $_.name.Substring(0,[Math]::Min(3,$_.name.Length)), (Test-Tunnel $_) }) -join " "
    $state = "$meshStr | $tunStr"
    $ts = Get-Date -Format "HH:mm:ss"
    if ($state -ne $last) {
        Write-Host "[$ts] CHANGE  $state" -ForegroundColor Yellow
        $last = $state
    } else {
        Write-Host "[$ts] steady  $state" -ForegroundColor DarkGray
    }
    Start-Sleep -Seconds $IntervalSec
}
