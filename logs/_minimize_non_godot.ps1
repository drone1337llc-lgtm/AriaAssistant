# Minimize all top-level windows except the Godot process. Then capture.
$signature = @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class W {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")] public static extern int GetWindow(IntPtr hWnd, uint uCmd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    public const int SW_MINIMIZE = 6;
    public const int SW_RESTORE = 9;
    public const int GW_OWNER = 4;
}
"@
Add-Type -TypeDefinition $signature -ErrorAction SilentlyContinue
$godPid = (Get-Process -Name 'Godot_v4.6.3-stable_mono_win64' -ErrorAction SilentlyContinue).Id
Write-Host "Godot pid=$godPid"
$minimized = 0
$kept = 0
$callback = [W+EnumWindowsProc]{
    param($hWnd, $lParam)
    if (-not [W]::IsWindowVisible($hWnd)) { return $true }
    $null = $null
    $procId = 0
    [void][W]::GetWindowThreadProcessId($hWnd, [ref]$procId)
    $title = New-Object System.Text.StringBuilder 256
    [void][W]::GetWindowText($hWnd, $title, 256)
    $t = $title.ToString()
    if ($t -eq '') { return $true }
    # Skip owned windows (popups owned by a parent)
    $owner = [W]::GetWindow($hWnd, [W]::GW_OWNER)
    if ($owner -ne 0) { return $true }
    if ($procId -eq $godPid) { $kept++; return $true }
    # Skip the Godot editor window — keep it so the game keeps running
    if ($t -like '*Godot Engine*' -or $t -like '*Aria*') { $kept++; return $true }
    # Skip taskbar / shell
    if ($t -like '*Taskbar*' -or $t -like '*Program Manager*') { return $true }
    [void][W]::ShowWindow($hWnd, [W]::SW_MINIMIZE)
    $script:minimized++
    return $true
}
[void][W]::EnumWindows($callback, [IntPtr]::Zero)
Write-Host "minimized $minimized windows, kept $kept (Godot + shell)"
