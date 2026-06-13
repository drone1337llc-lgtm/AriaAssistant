using Godot;
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public partial class WindowDetector : Node
{
	[DllImport("user32.dll")]
	private static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);

	[DllImport("user32.dll")]
	private static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

	[DllImport("user32.dll")]
	private static extern bool IsWindowVisible(IntPtr hWnd);

	[DllImport("user32.dll")]
	private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

	[DllImport("user32.dll")]
	private static extern IntPtr GetForegroundWindow();

	[DllImport("user32.dll")]
	private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

	[DllImport("user32.dll")]
	private static extern int GetWindowLong(IntPtr hWnd, int nIndex);

	[DllImport("user32.dll")]
	private static extern int GetWindowTextLength(IntPtr hWnd);

	[DllImport("dwmapi.dll")]
	private static extern int DwmGetWindowAttribute(IntPtr hwnd, int attr, out int value, int size);

	private const int GWL_EXSTYLE = -20;
	private const int WS_EX_TOOLWINDOW = 0x00000080;
	private const int DWMWA_CLOAKED = 14;

	[StructLayout(LayoutKind.Sequential)]
	public struct RECT { public int Left, Top, Right, Bottom; }

	private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

	// Screen-space rects of visible windows (excluding ourselves and shell)
	public List<Rect2> WindowLedges { get; private set; } = new();

	// Title of the window the user is currently focused on (excluding Aria's own
	// window). Lets the brain notice what the user is doing for ambient remarks.
	public string ForegroundTitle { get; private set; } = "";

	private float _pollTimer = 0f;
	private const float PollInterval = 2f;

	// Our own process id so we skip our window
	private uint _ownPid;

	public override void _Ready()
	{
		_ownPid = (uint)System.Diagnostics.Process.GetCurrentProcess().Id;
		Refresh();
	}

	public override void _Process(double delta)
	{
		_pollTimer += (float)delta;
		if (_pollTimer >= PollInterval)
		{
			_pollTimer = 0f;
			Refresh();
		}
	}

	public void Refresh()
	{
		var rects = new List<Rect2>();
		int screenH = DisplayServer.ScreenGetSize().Y;

		EnumWindows((hwnd, _) =>
		{
			if (!IsWindowVisible(hwnd)) return true;

			// Skip our own window
			GetWindowThreadProcessId(hwnd, out uint pid);
			if (pid == _ownPid) return true;

			// Skip tool windows (palettes, overlays) and untitled windows
			if ((GetWindowLong(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW) != 0) return true;
			if (GetWindowTextLength(hwnd) == 0) return true;

			// Skip cloaked windows (suspended UWP apps report visible but aren't drawn)
			if (DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, out int cloaked, sizeof(int)) == 0 && cloaked != 0)
				return true;

			if (!GetWindowRect(hwnd, out RECT r)) return true;

			int w = r.Right - r.Left;
			int h = r.Bottom - r.Top;

			// Skip tiny, off-screen, or full-screen windows
			if (w < 80 || h < 40) return true;
			if (r.Right < 0 || r.Left > DisplayServer.ScreenGetSize().X) return true;
			if (r.Bottom < 0 || r.Top > screenH) return true;
			if (w > DisplayServer.ScreenGetSize().X - 20 && h > screenH - 20) return true;

			rects.Add(new Rect2(r.Left, r.Top, w, h));
			return true;
		}, IntPtr.Zero);

		WindowLedges = rects;
		RefreshForegroundTitle();
	}

	// Read the focused window's title, skipping our own window so Aria never
	// "reacts to herself". Failures are swallowed — this is best-effort context.
	private void RefreshForegroundTitle()
	{
		try
		{
			IntPtr fg = GetForegroundWindow();
			if (fg == IntPtr.Zero) return;
			GetWindowThreadProcessId(fg, out uint pid);
			if (pid == _ownPid) return;   // it's us — leave the previous title
			int len = GetWindowTextLength(fg);
			if (len <= 0) return;
			var sb = new StringBuilder(len + 1);
			GetWindowText(fg, sb, sb.Capacity);
			ForegroundTitle = sb.ToString();
		}
		catch { /* best-effort; keep last known title */ }
	}

	// Returns the top-center point of the nearest window within reach, or null
	public Vector2? NearestLedge(Vector2 ariaPos, float reachX = 200f)
	{
		Vector2? best = null;
		float bestDist = float.MaxValue;

		foreach (var rect in WindowLedges)
		{
			// Top edge of the window
			float topY = rect.Position.Y;
			float centerX = rect.Position.X + rect.Size.X / 2f;
			float dist = Math.Abs(ariaPos.X - centerX);

			if (dist < reachX && dist < bestDist)
			{
				bestDist = dist;
				best = new Vector2(centerX, topY);
			}
		}
		return best;
	}
}
