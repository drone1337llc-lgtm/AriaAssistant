# Aria startup script — launches the Jessica TTS voice server, then runs the Godot export.
# Run from PowerShell:  .\start_aria.ps1
# Or to run the editor: .\start_aria.ps1 -Editor

param([switch]$Editor)

$TtsScript  = "C:\Users\Tench\Documents\Coqui-TTS-XTTS-v2-\scripts\tts_server_jessica.py"
$Python     = "C:\Program Files\Python312\python.exe"
$GodotExe   = "C:\Users\Tench\AppData\Local\Programs\Godot\Godot_v4.6.3_mono_win64.exe"
$ProjectDir = "C:\Users\Tench\Documents\AriaAssistant"

# Start TTS server in a separate window so its GPU log doesn't clutter Aria's output
Write-Host "[Aria] Starting Jessica TTS voice server (first load ~15s)..."
$ttsProc = Start-Process -FilePath $Python -ArgumentList $TtsScript `
    -WorkingDirectory (Split-Path $TtsScript) `
    -WindowStyle Normal -PassThru

Write-Host "[Aria] TTS server PID: $($ttsProc.Id)"
Write-Host "[Aria] Waiting for model to load..."
Start-Sleep -Seconds 18  # model takes ~15s; a little extra margin

if ($Editor) {
    Write-Host "[Aria] Opening Godot editor..."
    Start-Process -FilePath $GodotExe -ArgumentList "--editor", "--path", $ProjectDir
} else {
    Write-Host "[Aria] Launching Aria (exported game)..."
    # If you've exported: set this to the .exe path.  Otherwise open the editor.
    $ExportExe = "$ProjectDir\export\Aria.exe"
    if (Test-Path $ExportExe) {
        Start-Process -FilePath $ExportExe
    } else {
        Write-Host "[Aria] No export found at $ExportExe; opening editor instead."
        Start-Process -FilePath $GodotExe -ArgumentList "--editor", "--path", $ProjectDir
    }
}

Write-Host "[Aria] Started. Press Ctrl+C to stop the TTS server."
try { Wait-Process -Id $ttsProc.Id }
catch { Write-Host "[Aria] TTS server exited." }
