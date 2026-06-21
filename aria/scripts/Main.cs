using Godot;
using System;
using System.Runtime.InteropServices;
using Aria;

public partial class Main : Node
{
    [DllImport("user32.dll")] private static extern bool SetWindowPos(
        IntPtr hWnd, IntPtr hWndInsertAfter, int x, int y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll")] private static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] private static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
    [DllImport("user32.dll")] private static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    // Required for GWLP_WNDPROC subclassing — SetWindowLong truncates pointers on 64-bit.
    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);
    [DllImport("user32.dll")]
    private static extern IntPtr CallWindowProc(IntPtr lpPrevWndFunc, IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate IntPtr WndProcDelegate(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    private WndProcDelegate _customWndProc;    // keep reference to prevent GC collection
    private IntPtr _originalWndProc;

    private static readonly IntPtr HWND_TOPMOST = new(-1);
    private const uint SWP_NOMOVE = 0x0002, SWP_NOSIZE = 0x0001, SWP_NOACTIVATE = 0x0010,
                       SWP_NOZORDER = 0x0004, SWP_FRAMECHANGED = 0x0020;
    private const int  GWL_EXSTYLE = -20, GWLP_WNDPROC = -4, WS_EX_TRANSPARENT = 0x00000020;
    private const uint WM_NCHITTEST = 0x0084;
    private const int  HTTRANSPARENT = -1;

    [Export] public NodePath VrmNodePath;
    [Export] public NodePath SpeechLabelPath;

    // Voice config (TTSBridge is created in code; these surface its knobs in the Main Inspector).
    [Export] public bool VoiceEnabled = true;
    // Custom Jessica XTTS server (scripts/tts_server_jessica.py, port 5003).
    // Set UseJsonPost=true so TTSBridge sends {"text":...} instead of a GET query.
    [Export] public string TtsUrl = "http://127.0.0.1:5003/tts";
    [Export] public bool TtsUseJsonPost = true;
    [Export] public string TtsSpeaker = "";   // server ignores this; conditioning is baked in
    [Export] public string TtsLanguage = "en";

    // Motion-diffusion (FloodDiffusion) — runs on the AI PC. Created in code
    // when MotionServerUrl is set; disabled by default. When enabled, the brain
    // can request_motion directives and the server will generate new clips on demand.
    [Export] public string MotionServerUrl = "http://127.0.0.1:8766/motion";   // via bridge tunnel -> PC2:8766
    [Export] public int MotionQueueCapacity = 100;
    [Export] public float MotionPollIntervalSec = 2f;
    [Export] public string MotionAuthToken = "";
    [Export] public int ChatServerPort = 8767;   // HTTP listener for the Streamlit dashboard

    // ── Motion library mirror ────────────────────────────────────────────
    // The AI server emits a per-anim spec (duration, isInPlace, travel speed,
    // cut-short, boneSet, …) to astro_assistant/motion_library.json. We mirror
    // it into a C# dict at startup and re-poll every 5 min. Path defaults to
    // the server's drop location, one level up from the Godot project.
    [Export] public string MotionLibraryPath = "res://../motion_lib/motion_library.json";
    [Export] public float MotionLibraryPollSec = 300f;   // 5 minutes

    // Ambient awareness: every so often, when she's idle and quiet, Aria speaks
    // on her own initiative — noticing what app the user is in and offering a
    // remark or help. This is the "monitor anything I need help with / act on her
    // own initiative" behaviour. Set AmbientChatter=false to make her only speak
    // when greeted or poked. Intervals are in seconds (default 5–12 min).
    [Export] public bool AmbientChatter = true;
    [Export] public float AmbientMinInterval = 300f;
    [Export] public float AmbientMaxInterval = 720f;
    private float _ambientTimer = 0f;
    private float _ambientNext = 0f;
    private string _lastForegroundSpokenAbout = "";

    // ── Autonomy loop ──────────────────────────────────────────────────────────
    // Keeps Aria visibly alive: on its own timer she strolls to a new random spot
    // on the desktop. Completely independent of the LLM ambient-chatter loop.
    // Tune the interval in the Inspector (seconds). Set AutonomyEnabled=false to
    // make her only walk when the LLM or user tells her to.
    [Export] public bool AutonomyEnabled = true;
    [Export] public float AutonomyMinInterval = 60f;
    [Export] public float AutonomyMaxInterval = 150f;
    private float _autoTimer = 0f;
    private float _autoNext  = 0f;

    private CharacterController _character;
    private WindowDetector _windowDetector;
    private LLMBridge _llm;
    private ExpressionController _expr;
    private TTSBridge _tts;
    private HealthMonitor _health;
    private Aria.AriaMotionClient _motionClient;   // null if no server URL configured
    private Label _speechLabel;
    private float _speechTimer = 0f;
    private float _speechDuration = 0f;
    private bool _speaking = false;

    // Chat overlay (F2 toggles). Built in BuildChatOverlay().
    private CanvasLayer _chatLayer;
    private LineEdit _chatInput;
    private bool _chatOpen = false;

    // HTTP chat listener (POST /chat on ChatServerPort).
    private Aria.AriaChatServer _chatServer;
    private Vector2? _userCursor;     // last known viewport-relative cursor position

    public override void _Ready()
    {
        // Build marker — if you DON'T see this line in the Output panel, Godot is running
        // a stale C# build and the blink/bubble/head fixes below are NOT compiled in.
        GD.Print("[Main] Build OK: wndproc+ws-ex-transparent+hittest + worldenv-bg + multi-json-parse + autonomy active");

        // Maximize the window so Aria can roam the full desktop.
        // Required for the "character walks on the physical screen" illusion.
        DisplayServer.WindowSetMode(DisplayServer.WindowMode.Maximized);

        // Force the window to (0, 0) on the current screen. Without this, on
        // some setups DisplayServer reports a window position that's offset
        // (e.g. y=1080 on a 1440p display) so the actual rendered window
        // ends up off the bottom of the visible monitor. Pinning to (0, 0)
        // makes the viewport and the visible screen agree.
        int scr = DisplayServer.WindowGetCurrentScreen();
        var screenPos = DisplayServer.ScreenGetPosition(scr);
        var screenSize = DisplayServer.ScreenGetSize(scr);
        DisplayServer.WindowSetPosition(screenPos);
        DisplayServer.WindowSetSize(screenSize);
        // Cache the window's screen origin once, right after we position it.
        // WindowGetPosition() can drift on some setups (e.g. multi-monitor DPI scaling)
        // so we use this stable snapshot in UpdateClickRegion instead of calling it every frame.
        _windowOrigin = screenPos;

        // Enable per-pixel transparency for the Godot window.
        // NOTE: do NOT add WS_EX_LAYERED via SetWindowLong — that switches DWM from
        // the native Vulkan alpha-compositing path to GDI-layered mode, which doesn't
        // capture Vulkan output and renders the whole window white.  Godot's Forward+
        // renderer achieves per-pixel transparency through the Vulkan swapchain directly.
        GetWindow().TransparentBg = true;

        // The Vulkan clear colour is already transparent (project.godot sets it).
        // We also need a WorldEnvironment with BGMode.Color + alpha=0 so that Forward+
        // doesn't render a sky or procedural background over the clear colour.
        // Without this node, the 3D scene paints a white/sky rectangle over the desktop
        // even though TransparentBg is true.
        RenderingServer.SetDefaultClearColor(Colors.Transparent);
        var worldEnv = GetNodeOrNull<WorldEnvironment>("WorldEnvironment");
        if (worldEnv == null)
        {
            worldEnv = new WorldEnvironment { Name = "WorldEnvironment" };
            AddChild(worldEnv);
        }
        if (worldEnv.Environment == null)
            worldEnv.Environment = new Godot.Environment();
        worldEnv.Environment.BackgroundMode = Godot.Environment.BGMode.Color;
        worldEnv.Environment.BackgroundColor = new Color(0, 0, 0, 0);   // fully transparent

        // Make window always-on-top, hook WM_NCHITTEST, and set initial click-through.
        MakeWindowBehave();

        _windowDetector = GetNode<WindowDetector>("WindowDetector");
        _character = GetNode<CharacterController>("CharacterController");
        _llm = GetNode<LLMBridge>("LLMBridge");
        _speechLabel = GetNode<Label>(SpeechLabelPath);

        // Per-anim self-tuning speed tracker. First 10 plays of any anim
        // are shadow (log only, no override); after that the tuner multiplies
        // the user-supplied speedScale by a learned [0.5, 2.0] correction.
        // Stats persist to <project>/logs/anim_speed_tuner.json so tuning
        // survives restarts. Inject into the controller so PlayAnim can
        // call RecordPlay on every play.
        var tuner = new Aria.AnimSpeedTuner();
        _character.SetTuner(tuner);

        // The label is repositioned above Aria's head every frame; switch it
        // from the scene's full-width top anchor to a free-floating box.
        _speechLabel.SetAnchorsPreset(Control.LayoutPreset.TopLeft);
        // Size is recomputed to fit each line of dialogue (SizeBubbleToText), so don't
        // force a fixed width — let the bubble shrink for short lines and grow for long.
        _speechLabel.CustomMinimumSize = Vector2.Zero;

        // The window is borderless + transparent (you can see the desktop through it).
        // Per the AstroBud design system, the speech bubble is a cool near-white glass
        // panel with navy ink, a periwinkle rim, 14px corners and a soft cool shadow —
        // matching the PyQt overlay bubble so both surfaces read identically. The opaque
        // light panel keeps text readable over any desktop region, so no text outline.
        var bg = new StyleBoxFlat
        {
            BgColor = new Color(0.961f, 0.980f, 1.0f, 0.92f),       // --surface-bubble  rgba(245,250,255,.92)
            BorderColor = new Color(0.706f, 0.784f, 0.941f, 0.63f), // --border-bubble   rgba(180,200,240,.63)
            BorderWidthLeft = 2, BorderWidthRight = 2, BorderWidthTop = 2, BorderWidthBottom = 2,
            CornerRadiusTopLeft = 14,
            CornerRadiusTopRight = 14,
            CornerRadiusBottomLeft = 14,
            CornerRadiusBottomRight = 14,
            ContentMarginLeft = 17,
            ContentMarginRight = 17,
            ContentMarginTop = 13,
            ContentMarginBottom = 13,
            // Soft, cool, downward shadow — --shadow-bubble  0 8px 24px rgba(20,24,60,.25)
            ShadowColor = new Color(0.078f, 0.094f, 0.235f, 0.25f),
            ShadowSize = 12,
            ShadowOffset = new Vector2(0, 8),
        };
        _speechLabel.AddThemeStyleboxOverride("normal", bg);
        // Navy ink on the light bubble (--text-on-bubble #1A1A2E). No outline needed now
        // that text always sits on an opaque light panel.
        _speechLabel.AddThemeColorOverride("font_color", new Color(0.102f, 0.102f, 0.180f, 1));
        _speechLabel.AddThemeConstantOverride("outline_size", 0);

        // Make sure the UI CanvasLayer is in front of the 3D scene.
        var uiLayer = _speechLabel.GetParent() as CanvasLayer;
        if (uiLayer != null) uiLayer.Layer = 10;

        // Chat input overlay (F2 to toggle). Lets you type a message to Aria
        // without having to right-click on her tiny hit-box.
        BuildChatOverlay(uiLayer);

        // Step 1: Build the animation library from the imported Mixamo FBX files.
        var animBuilder = GetNodeOrNull<AnimationBuilder>("AnimationBuilder");
        if (animBuilder != null) animBuilder.Build();
        else GD.PrintErr("[Main] AnimationBuilder node not found");

        // Step 2: Find Aria's root and her AnimationPlayer (now populated).
        Node3D aria = GetNodeOrNull<Node3D>("CharacterController/Aria");
        if (aria != null)
        {
            // Diagnostic: list every mesh under Aria so a stray backdrop/plane baked
            // into the model (which would render as a faint "box") can be spotted by name.
            foreach (var mi in aria.FindChildren("*", "MeshInstance3D", true, false))
                GD.Print($"[Diag] Mesh under Aria: '{mi.Name}'");
        }
        AnimationPlayer anim = GetNodeOrNull<AnimationPlayer>("CharacterController/Aria/Armature/AnimationPlayer");
        if (anim == null && aria != null)
        {
            foreach (var child in aria.FindChildren("*", "AnimationPlayer", true, false))
            {
                anim = child as AnimationPlayer;
                if (anim != null) break;
            }
        }
        if (anim == null)
            GD.PrintErr("[Aria] Could not find any AnimationPlayer in the imported Aria.glb — animations won't play");

        _character.Init(anim, _windowDetector);

        // Mirror the server-side motion_library.json into AnimSources.
        // The poll loop fires LibraryUpdated on mtime/sha256 change; the
        // character controller reads AnimSources to look up per-anim
        // travel speed.  Path defaults to the server's drop location
        // (res://../astro_assistant/motion_library.json) but can be
        // overridden in the Inspector for local testing.
        var mirror = new Aria.MotionLibraryMirror
        {
            Name = "MotionLibraryMirror",
            MotionLibraryPath = MotionLibraryPath,
            PollIntervalSec = MotionLibraryPollSec,
        };
        AddChild(mirror);
        mirror.Attach(anim, this);
        mirror.LibraryUpdated += (count, hash) =>
            GD.Print($"Library updated: {count} animations, hash={hash}");

        // Step 3: Stand up the voice, face, and self-watch systems. These are
        // created in code so the .tscn needs no extra nodes or NodePath wiring.
        _expr = new ExpressionController { Name = "ExpressionController" };
        AddChild(_expr);
        if (aria != null) _expr.Setup(aria);

        _tts = new TTSBridge
        {
            Name = "TTSBridge",
            Enabled = VoiceEnabled,
            TtsUrl = TtsUrl,
            UseJsonPost = TtsUseJsonPost,
            Speaker = TtsSpeaker,
            Language = TtsLanguage,
        };
        AddChild(_tts);

        // Motion-diffusion client — only created if a server URL is configured.
        // On the IK-only build (MotionServerUrl empty) this block is skipped
        // and the controller's RequestMotion directives will silently no-op.
        if (!string.IsNullOrWhiteSpace(MotionServerUrl))
        {
            _motionClient = new AriaMotionClient
            {
                Name = "AriaMotionClient",
                ServerUrl = MotionServerUrl,
                MaxQueueDepth = MotionQueueCapacity,
                PollIntervalSec = MotionPollIntervalSec,
                AuthToken = MotionAuthToken,
            };
            AddChild(_motionClient);
            _character?.SetMotionClient(_motionClient);
            GD.Print($"[Motion] client enabled: {MotionServerUrl} (cap={MotionQueueCapacity})");
        }

        // Tiny HTTP listener (port 8767) so the Streamlit dashboard on PC 2
        // (or any LAN device) can POST /chat {"text":"..."} and Aria will
        // process it through the same LLM path as right-clicks / F2 input.
        _chatServer = new Aria.AriaChatServer
        {
            Name = "AriaChatServer",
            Port = ChatServerPort,
        };
        _chatServer.OnChatMessage = (text) => _llm.SendMessage(text,
            _character?.BuildWorldState(_userCursor,
                                          _windowDetector?.ForegroundTitle,
                                          _motionClient?.LocalQueueDepth,
                                          MotionQueueCapacity));
        AddChild(_chatServer);

        _health = new HealthMonitor { Name = "HealthMonitor" };
        AddChild(_health);
        _health.Setup(_character, anim, _llm, aria);

        // Step 4: Brain → avatar. ResponseReady carries say + emotion + action;
        //         DirectivesReady carries the sequenced body plan.
        _llm.ResponseReady += OnResponse;
        _llm.DirectivesReady += OnDirectives;

        // Greet on startup (works even offline — proves the bubble + voice path).
        GetTree().CreateTimer(2.0).Timeout += () =>
            _llm.SendMessage("You just appeared on the user's desktop. Greet them warmly in one short sentence.",
                             _character?.BuildWorldState(_userCursor,
                                                          _windowDetector?.ForegroundTitle,
                                                          _motionClient?.LocalQueueDepth,
                                                          MotionQueueCapacity));

        // Schedule her first unprompted remark.
        _ambientNext = (float)GD.RandRange(AmbientMinInterval, AmbientMaxInterval);

        // Autonomy loop: first walk happens shortly after startup so the loop is
        // visibly active right away, then settles into the configured interval.
        _autoNext = (float)GD.RandRange(30.0, 60.0);

        // Diagnostics: rest pose now, animated pose at t=1s.
        GD.Print("[Diag] ===== REST POSE (end of _Ready, no anim frame yet) =====");
        DumpDiagnostics();
        GetTree().CreateTimer(1.0).Timeout += () =>
        {
            GD.Print("[Diag] ===== ANIMATED (t=1s, idle playing) =====");
            DumpDiagnostics();
        };
    }

    public override void _Process(double delta)
    {
        if (_speaking && _speechDuration > 0f)
        {
            _speechTimer += (float)delta;
            if (_speechTimer >= _speechDuration)
            {
                _speechLabel.Visible = false;
                _speechDuration = 0f;
                _speaking = false;
                _expr?.StopTalking();
            }
        }

        UpdateClickRegion();
        MaybeAmbientChatter(delta);
        TickAutonomy(delta);
    }

    /// <summary>
    /// Autonomy tick: fires on its own timer and sends Aria walking to a fresh
    /// random position on the desktop. This is the core "she feels alive" loop —
    /// runs independently of the LLM, so she keeps moving even when the AI is
    /// idle or slow. Only acts when she's fully settled (Idle state).
    /// </summary>
    private void TickAutonomy(double delta)
    {
        if (!AutonomyEnabled || _character == null) return;
        _autoTimer += (float)delta;
        if (_autoTimer < _autoNext) return;

        _autoTimer = 0f;
        _autoNext = (float)GD.RandRange(AutonomyMinInterval, AutonomyMaxInterval);

        // Don't interrupt a walk, climb, fall, or reaction — wait until she's resting.
        if (_character.CurrentState != CharacterController.State.Idle) return;
        // And don't fire while the LLM has an active plan (turn_to, pause, gesture…).
        // Autonomy and brain-driven directives shouldn't fight each other.
        if (_character.HasPendingDirectives) return;

        // Pick a random floor X on the usable screen area and stroll there.
        int scr = DisplayServer.WindowGetCurrentScreen();
        var usable = DisplayServer.ScreenGetUsableRect(scr);
        // Convert global screen X to viewport-relative by subtracting the window's X.
        float winX = DisplayServer.WindowGetPosition().X;
        float minX = usable.Position.X - winX + 80f;
        float maxX = usable.Position.X + usable.Size.X - winX - 80f;
        if (maxX <= minX) return;   // safety: degenerate rect

        float targetX = (float)GD.RandRange(minX, maxX);
        _character.WalkTo(targetX);

        GD.Print($"[Autonomy] tick → WalkTo({targetX:F0})  next in {_autoNext:F0}s");
    }

    /// <summary>
    /// Aria's self-initiated awareness. On a long random timer, when she's idle
    /// and not already speaking, she sends the brain a context-aware nudge —
    /// usually about whatever app the user is focused on — so she behaves like a
    /// companion who notices things, not a bot that only answers when poked.
    /// Fully reuses the brain→bubble→voice→face→gesture path via OnResponse.
    /// </summary>
    private void MaybeAmbientChatter(double delta)
    {
        if (!AmbientChatter || _llm == null || _character == null) return;
        if (_speaking) return;                                   // don't talk over herself
        if (_character.CurrentState != CharacterController.State.Idle) return; // only when settled
        if (_character.HasPendingDirectives) return;             // LLM has a plan, let it play out

        _ambientTimer += (float)delta;
        if (_ambientTimer < _ambientNext) return;

        _ambientTimer = 0f;
        _ambientNext = (float)GD.RandRange(AmbientMinInterval, AmbientMaxInterval);

        string title = _windowDetector?.ForegroundTitle ?? "";
        string prompt;
        if (!string.IsNullOrWhiteSpace(title) && title != _lastForegroundSpokenAbout)
        {
            _lastForegroundSpokenAbout = title;
            prompt = $"Unprompted, you glance over and notice the user is working in \"{title}\". " +
                     "Make ONE short, warm, in-character remark about it or a light offer to help. " +
                     "Vary your openings; don't repeat yourself.";
        }
        else
        {
            prompt = "A quiet moment has passed with no input from the user. Say ONE short, in-character " +
                     "thing on your own initiative — a small observation, a bit of company, or a gentle " +
                     "check-in. Keep it natural and don't repeat your earlier lines.";
        }
        GD.Print($"[Ambient] initiating (fg=\"{title}\")");
        _llm.SendMessage(prompt, _character?.BuildWorldState(_userCursor, title,
                                                             _motionClient?.LocalQueueDepth,
                                                             MotionQueueCapacity));
    }

    /// <summary>
    /// Two-layer click-through approach (belt + suspenders):
    ///   1. WM_NCHITTEST hook (CustomWndProc) returns HTTRANSPARENT outside Aria's hitbox.
    ///   2. WS_EX_TRANSPARENT per-frame toggle via SetClickThrough.
    /// WS_EX_TRANSPARENT without WS_EX_LAYERED is the GDI painting-order flag per MSDN,
    /// but on Windows 10/11 with DWM-Vulkan compositing the system still passes mouse
    /// events through for non-layered transparent windows — providing a second path when
    /// the WndProc hook alone is insufficient for cross-process click passthrough.
    /// </summary>
    private void UpdateClickRegion()
    {
        if (_character == null) return;
        if (_speechLabel != null && _speechLabel.Visible) PositionSpeechLabel();

        // The ONLY mechanism that gives a Godot per-pixel-transparent window real
        // cross-process click-through on Windows is the mouse-passthrough region: the
        // window only "exists" where this polygon is, so clicks anywhere else fall to the
        // desktop. It also clips rendering to the polygon — fine, since everything outside
        // is empty/transparent anyway. We cover her body and stretch up to include the
        // speech bubble while it's visible, so the bubble isn't clipped.
        Vector2 feet = _character.FeetScreen;             // viewport-relative px
        float left = feet.X - 150f, right = feet.X + 150f, top = feet.Y - 360f, bottom = feet.Y + 12f;
        if (_speechLabel != null && _speechLabel.Visible)
        {
            Vector2 p = _speechLabel.Position, s = _speechLabel.Size;
            left = Math.Min(left, p.X - 8f);
            right = Math.Max(right, p.X + s.X + 8f);
            top = Math.Min(top, p.Y - 8f);
        }
        var region = new Vector2[]
        {
            new(left, top), new(right, top), new(right, bottom), new(left, bottom),
        };
        DisplayServer.WindowSetMousePassthrough(region);
    }

    private bool _clickThrough;
    private Vector2I _windowOrigin;   // cached at _Ready(); used by CustomWndProc + UpdateClickRegion

    /// <summary>Toggle WS_EX_TRANSPARENT (no WS_EX_LAYERED — that breaks Vulkan rendering).</summary>
    private void SetClickThrough(bool on)
    {
        var hwnd = (IntPtr)DisplayServer.WindowGetNativeHandle(DisplayServer.HandleType.WindowHandle);
        if (hwnd == IntPtr.Zero) return;
        int ex = GetWindowLong(hwnd, GWL_EXSTYLE);
        int desired = on ? (ex | WS_EX_TRANSPARENT) : (ex & ~WS_EX_TRANSPARENT);
        if (desired == ex) { _clickThrough = on; return; }
        SetWindowLong(hwnd, GWL_EXSTYLE, desired);
        SetWindowPos(hwnd, IntPtr.Zero, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
        _clickThrough = on;
    }

    /// <summary>
    /// True if a mouse event at viewport-coord (mx, my) is over Aria's
    /// character (feet ±160 wide, feet -340..+10 tall). Used by _Input
    /// to decide whether a right-click should poke Aria or be ignored
    /// (so it passes through to whatever app is behind the window).
    /// </summary>
    private bool IsClickOnAria(float mx, float my)
    {
        if (_character == null) return false;
        Vector2 feet = _character.FeetScreen;
        return mx >= feet.X - 150f && mx <= feet.X + 150f
            && my >= feet.Y - 360f && my <= feet.Y + 12f;
    }

    private void PositionSpeechLabel()
    {
        if (_character == null || _speechLabel == null) return;
        // HeadScreen is in viewport-relative (window-local) coords.
        Vector2 head = _character.HeadScreen;
        float hx = head.X;
        float hy = head.Y;
        var vp = GetViewport().GetVisibleRect().Size;
        float lw = _speechLabel.Size.X;
        float labelH = Math.Max(_speechLabel.Size.Y, 44f);
        float lx = Mathf.Clamp(hx - lw / 2f, 8f, vp.X - lw - 8f);
        float ly = Mathf.Clamp(hy - labelH - 28f, 8f, vp.Y - labelH - 8f);
        _speechLabel.Position = new Vector2(lx, ly);
    }

    // Grow/shrink the speech bubble to fit the wrapped text exactly, so long lines
    // aren't clipped and short ones don't leave a big empty panel.
    private void SizeBubbleToText(string say)
    {
        const float maxTextWidth = 340f;   // wrap width for the text itself
        const float padX = 34f;            // stylebox L+R content margins (17 + 17)
        const float padY = 26f;            // stylebox T+B content margins (13 + 13)

        var font = _speechLabel.GetThemeFont("font");
        int fontSize = _speechLabel.GetThemeFontSize("font_size");
        if (font == null || fontSize <= 0)
        {
            // Theme font not resolved yet — fall back to a rough char-count estimate.
            int est = Math.Max(1, (int)Math.Ceiling(say.Length / 42.0));
            _speechLabel.Size = new Vector2(maxTextWidth + padX, est * 21f + padY);
            return;
        }

        // Measure wrapped at the cap width. If it fits on one line, shrink the bubble
        // to that line; otherwise keep the cap width so the Label re-wraps identically
        // (a narrower width would re-break words and clip the bottom line — the cause
        // of the earlier text cut-off).
        Vector2 measured = font.GetMultilineStringSize(
            say, HorizontalAlignment.Center, maxTextWidth, fontSize);
        float lineH = font.GetHeight(fontSize);
        float textW = measured.Y <= lineH * 1.4f
            ? Mathf.Min(Mathf.Ceil(measured.X), maxTextWidth)
            : maxTextWidth;
        Vector2 fitted = font.GetMultilineStringSize(
            say, HorizontalAlignment.Center, textW, fontSize);
        // Generous slack: a whole extra line of height plus 8px width so a tall glyph,
        // descender, or wrap-rounding can never clip the text inside the bubble.
        _speechLabel.Size = new Vector2(textW + padX + 8f, Mathf.Ceil(fitted.Y) + padY + Mathf.Ceil(lineH));
    }

    private void OnResponse(string say, string emotion, string action, string move)
    {
        _tts?.Stop();                       // cut any overlapping audio

        // Empty/whitespace line → make sure no blank white bubble lingers on screen.
        if (string.IsNullOrWhiteSpace(say))
        {
            _speechLabel.Visible = false;
            _speaking = false;
            return;
        }

        _speechLabel.Text = say;
        SizeBubbleToText(say);
        _speechLabel.Visible = true;
        PositionSpeechLabel(); // position now, not waiting for the next _Process frame
        GD.Print($"[Bubble] pos={_speechLabel.Position} size={_speechLabel.Size} " +
                 $"headScreen={_character.HeadScreen} winPos={DisplayServer.WindowGetPosition()} " +
                 $"vp={GetViewport().GetVisibleRect().Size}");
        _speechTimer = 0f;
        _speechDuration = Mathf.Clamp(say.Length * 0.06f, 3f, 9f);
        _speaking = true;

        _expr?.SetEmotion(emotion);
        _character?.SetEmotionTag(emotion);   // remember so the next WorldState reports it
        _expr?.StartTalking();
        HandleBody(action, move);             // legacy {action,move} path; OnDirectives overrides if a queue is coming
        _tts?.Speak(say);

        GD.Print($"[Speech] say='{say}' emotion={emotion} action={action} " +
                 $"visible={_speechLabel.Visible} dur={_speechDuration:F1}s " +
                 $"canvasLayer={(_speechLabel.GetParent() as CanvasLayer)?.Layer ?? -1}");
    }

    /// <summary>
    /// Rich-signal handler: the LLM's reply included a 'directives' array.
    /// Hand them to the controller's queue, which executes them in order and
    /// preempts the random/idle state machine. If the reply also had a legacy
    /// {move} that started a walk in OnResponse, that walk is cancelled here
    /// so we never have two body commands fighting each other.
    /// </summary>
    private void OnDirectives(Godot.Collections.Array<Aria.AriaDirective> directives,
                              string say, string emotion)
    {
        if (_character == null) return;
        if (directives == null || directives.Count == 0)
        {
            // No directives — let the legacy {action, move} path keep running.
            return;
        }
        // The LLM chose to use the new vocabulary. Cancel any legacy walk that
        // just started in OnResponse, then submit the plan.
        _character.ClearDirectives();
        var arr = new Aria.AriaDirective[directives.Count];
        for (int i = 0; i < directives.Count; i++) arr[i] = directives[i];
        _character.SubmitDirectives(arr, append: false);
        GD.Print($"[Directives] submitted {arr.Length} to controller, queue depth={_character.PendingDirectiveCount}");
    }

    // ── Debug IK hotkeys ───────────────────────────────────────────────
    // Fire IK directives directly from the keyboard, bypassing the LLM.
    // Useful for verifying the IK layer is doing what it should without
    // depending on whether the LLM emits the new vocabulary.
    private void DebugIKHotkey(Key k)
    {
        if (_character == null) return;
        if (k == Key.K)
        {
            _character.SubmitDirective(new Aria.AriaDirective { Kind = Aria.DirectiveKind.IkReleaseAll });
            GD.Print("[DebugIK] released all chains");
            return;
        }
        if (k == Key.R)
        {
            // Random reach — pick a target in front of Aria
            var rng = new RandomNumberGenerator(); rng.Randomize();
            float x = (float)rng.RandfRange(-1.2f, 1.2f);
            float y = (float)rng.RandfRange(0.0f, 1.5f);
            float z = (float)rng.RandfRange(0.5f, 2.0f);   // in front of camera
            _character.SubmitDirective(new Aria.AriaDirective
            {
                Kind = Aria.DirectiveKind.IkReach,
                Name = DebugIKHotkeyChain,
                X = x, Y = y, Z = z,
            });
            GD.Print($"[DebugIK] ik_reach {DebugIKHotkeyChain} -> ({x:F2},{y:F2},{z:F2})");
            return;
        }
        if (k == Key.L)
        {
            // Look at a random in-front point
            var rng = new RandomNumberGenerator(); rng.Randomize();
            float x = (float)rng.RandfRange(-1.5f, 1.5f);
            float y = (float)rng.RandfRange(0.3f, 1.5f);
            float z = (float)rng.RandfRange(0.5f, 2.0f);
            _character.SubmitDirective(new Aria.AriaDirective
            {
                Kind = Aria.DirectiveKind.IkLook,
                X = x, Y = y, Z = z,
            });
            GD.Print($"[DebugIK] ik_look -> ({x:F2},{y:F2},{z:F2})");
            return;
        }
        if (k == Key.T)
        {
            _character.SubmitDirective(new Aria.AriaDirective
            {
                Kind = Aria.DirectiveKind.IkLean, Direction = "forward", Amount = 0.6f,
            });
            GD.Print("[DebugIK] ik_lean forward amt=0.6");
            return;
        }
        if (k == Key.Y)
        {
            _character.SubmitDirective(new Aria.AriaDirective
            {
                Kind = Aria.DirectiveKind.IkTwist, YawDeg = 30, PitchDeg = -5,
            });
            GD.Print("[DebugIK] ik_twist yaw=30 pitch=-5");
            return;
        }
        if (k == Key.G)
        {
            _character.SubmitDirective(new Aria.AriaDirective
            {
                Kind = Aria.DirectiveKind.IkGrip, Hand = "right", Name = "closed", Amount = 1f,
            });
            GD.Print("[DebugIK] ik_grip right closed");
            return;
        }
        if (k == Key.H)
        {
            _character.SubmitDirective(new Aria.AriaDirective
            {
                Kind = Aria.DirectiveKind.IkGrip, Hand = "right", Name = "open", Amount = 1f,
            });
            GD.Print("[DebugIK] ik_grip right open");
            return;
        }
    }

    // Routes the brain's body intent: a real {move} drives locomotion; otherwise she
    // settles in place and plays the one-off {action} gesture. Emotion is handled separately.
    private void HandleBody(string action, string move)
    {
        move = (move ?? "stay").Trim().ToLowerInvariant();
        bool locomotion = move is "left" or "right" or "come" or "here" or "approach" or "toward_me" or "roam" or "wander";
        if (locomotion)
            _character.CommandMove(move);     // go somewhere; skip the one-off gesture this turn
        else
        {
            _character.CommandMove("stay");   // settle here…
            DoAction(action);                 // …and play the gesture
        }
    }

    private void DoAction(string action)
    {
        switch ((action ?? "none").Trim().ToLowerInvariant())
        {
            case "none" or "": break;   // truly no-op; don't interrupt idle
            case "wave":     _character.PlayGesture("react", 3f); break;   // greeting wave → Standing Greeting clip
            case "dance":    _character.PlayGesture("wave", 4f); break;
            case "thankful": _character.PlayGesture("thankful", 3f); break;
            case "look":     _character.PlayGesture("look", 3f); break;
            case "react":    _character.PlayGesture("react", 3f); break;
            case "sit":      _character.PlayGesture(_character.IsPerched ? "sit_clap" : "react", 4f); break;
            case "yawn":     _character.PlayGesture("yawn", 3f); break;
            case "nod":      _character.PlayGesture("react", 2f); break;
            case "celebrate":_character.PlayGesture("dance_tut", 3f); break;
            default:         _character.EnterReact(1.5f); break;
        }
    }

    /// <summary>
    /// One-shot debug dump: window/viewport geometry, camera setup, and the
    /// world-space bounding box of Aria's meshes.
    /// </summary>
    private void DumpDiagnostics()
    {
        int screen = DisplayServer.WindowGetCurrentScreen();
        GD.Print($"[Diag] window pos={DisplayServer.WindowGetPosition()} size={DisplayServer.WindowGetSize()} mode={DisplayServer.WindowGetMode()}");
        GD.Print($"[Diag] screen={screen} usable={DisplayServer.ScreenGetUsableRect(screen)} full={DisplayServer.ScreenGetSize(screen)}");
        GD.Print($"[Diag] viewport visible rect={GetViewport().GetVisibleRect()}");

        var cam = GetNodeOrNull<Camera3D>("Camera3D");
        if (cam != null)
            GD.Print($"[Diag] camera projection={cam.Projection} size={cam.Size} pos={cam.GlobalPosition} current={cam.Current}");
        else
            GD.PrintErr("[Diag] Camera3D node not found!");

        GD.Print($"[Diag] character feet={_character.FeetScreen} node pos={_character.Position}");

        var aria = GetNodeOrNull<Node3D>("CharacterController/Aria");
        if (aria == null) { GD.PrintErr("[Diag] Aria node not found!"); return; }

        bool first = true;
        Aabb total = new();
        int meshCount = 0;
        foreach (var n in aria.FindChildren("*", "MeshInstance3D", true, false))
        {
            if (n is MeshInstance3D mi)
            {
                var ab = mi.GlobalTransform * mi.GetAabb();
                total = first ? ab : total.Merge(ab);
                first = false;
                meshCount++;
            }
        }
        if (first)
            GD.PrintErr("[Diag] NO MeshInstance3D found under Aria — model didn't import/instance!");
        else
            GD.Print($"[Diag] Aria world AABB: pos={total.Position} size={total.Size} ({meshCount} meshes), aria scale={aria.Scale}");

        var skel = aria.FindChildren("*", "Skeleton3D", true, false).Count > 0
            ? aria.FindChildren("*", "Skeleton3D", true, false)[0] as Skeleton3D : null;
        var player = aria.FindChildren("*", "AnimationPlayer", true, false).Count > 0
            ? aria.FindChildren("*", "AnimationPlayer", true, false)[0] as AnimationPlayer : null;
        if (skel != null)
        {
            int hips = skel.FindBone("J_Bip_C_Hips");
            int upperArm = skel.FindBone("J_Bip_L_UpperArm");
            if (hips >= 0)
                GD.Print($"[Diag] live hips pose rot={skel.GetBonePoseRotation(hips)} rest rot={skel.GetBoneRest(hips).Basis.GetRotationQuaternion()}");
            if (upperArm >= 0)
                GD.Print($"[Diag] live L_UpperArm pose rot={skel.GetBonePoseRotation(upperArm)}");
        }
        if (player != null && player.CurrentAnimation != "")
        {
            var a = player.GetAnimation(player.CurrentAnimation);
            if (a != null && a.GetTrackCount() > 0)
            {
                GD.Print($"[Diag] playing '{player.CurrentAnimation}' pos={player.CurrentAnimationPosition:F2}s tracks={a.GetTrackCount()}");
                for (int i = 0; i < Math.Min(2, a.GetTrackCount()); i++)
                {
                    GD.Print($"[Diag]   track{i}: path={a.TrackGetPath(i)} type={a.TrackGetType(i)} keys={a.TrackGetKeyCount(i)} " +
                             $"k@0={(a.TrackGetKeyCount(i) > 0 ? a.TrackGetKeyValue(i, 0).ToString() : "-")} " +
                             $"k@1s={(a.TrackGetType(i) == Animation.TrackType.Rotation3D ? a.RotationTrackInterpolate(i, 1.0).ToString() : "-")}");
                }
            }
        }
    }

    // Keyboard debug: when DebugIKMode is true, hit keys to fire IK directives
    // directly without going through the LLM. Useful for verifying the IK
    // layer is working in the production scene (the user reported "no visible
    // difference" — these hotkeys let you SEE the IK move without depending
    // on whether the LLM emits the new vocabulary).
    [Export] public bool DebugIKMode = true;
    [Export] public string DebugIKHotkeyChain = "right_arm";  // change in Inspector

    public override void _Input(InputEvent e)
    {
        // Track the user's cursor so the brain can issue directives like
        // "come over here" or "face the user" without knowing pixel coords.
        if (e is InputEventMouseMotion mm)
        {
            _userCursor = mm.Position;
            _character?.SetUserCursor(_userCursor);
        }

        // Debug hotkeys: R = random reach, L = look at cursor, K = release all,
        // T = lean forward, Y = twist, G = grip close, H = grip open.
        // Fires regardless of whether Aria is clicked, so you can test IK
        // from anywhere on the desktop.
        if (e is InputEventKey k && k.Pressed && !k.Echo)
        {
            // F2 toggles the chat overlay. We let this through even when the
            // chat LineEdit has focus, but the LineEdit handles Enter itself.
            if (k.Keycode == Key.F2)
            {
                ToggleChat();
            }
            // Esc closes the chat overlay if it's open.
            else if (k.Keycode == Key.Escape && _chatOpen)
            {
                ToggleChat();
            }
            else if (DebugIKMode)
            {
                DebugIKHotkey(k.Keycode);
            }
        }

        // Right-click ON ARIA sends a playful poke to the brain. The window
        // is fully click-through (no mouse passthrough polygon), so clicks
        // anywhere else pass through to apps behind. We only act on clicks
        // that land on Aria's hit-box.
        if (e is InputEventMouseButton mb && mb.ButtonIndex == MouseButton.Right && mb.Pressed)
        {
            var pos = mb.Position;
            if (IsClickOnAria(pos.X, pos.Y))
            {
                _llm.SendMessage("The user just clicked on you. React playfully in one short sentence.",
                                 _character?.BuildWorldState(_userCursor,
                                                               _windowDetector?.ForegroundTitle,
                                                               _motionClient?.LocalQueueDepth,
                                                               MotionQueueCapacity));
            }
        }
    }

    private void BuildChatOverlay(CanvasLayer parent)
    {
        // A second CanvasLayer above the speech bubble so input fields are clickable.
        // Layer 11 (speech is 10) keeps the chat on top.
        _chatLayer = new CanvasLayer { Layer = 11, Name = "ChatOverlay" };
        parent?.GetParent()?.AddChild(_chatLayer);

        // Top-center strip — wide enough to read, narrow enough to stay out of the way.
        var panel = new PanelContainer { Name = "ChatPanel" };
        panel.SetAnchorsPreset(Control.LayoutPreset.TopWide);
        panel.OffsetTop = 16f;
        panel.OffsetBottom = 80f;
        panel.OffsetLeft = 600f;
        panel.OffsetRight = -600f;
        panel.Visible = false;
        _chatLayer.AddChild(panel);

        var bg = new StyleBoxFlat
        {
            BgColor = new Color(0.06f, 0.07f, 0.12f, 0.92f),
            BorderColor = new Color(0.40f, 0.55f, 0.95f, 1f),
            BorderWidthLeft = 1, BorderWidthRight = 1, BorderWidthTop = 1, BorderWidthBottom = 1,
            CornerRadiusTopLeft = 8, CornerRadiusTopRight = 8,
            CornerRadiusBottomLeft = 8, CornerRadiusBottomRight = 8,
            ContentMarginLeft = 12, ContentMarginRight = 12,
            ContentMarginTop = 8,  ContentMarginBottom = 8,
        };
        panel.AddThemeStyleboxOverride("panel", bg);

        var row = new HBoxContainer();
        row.AddThemeConstantOverride("separation", 8);
        panel.AddChild(row);

        var hint = new Label { Text = "F2 to close · Enter to send:", CustomMinimumSize = new Vector2(0, 28) };
        hint.AddThemeColorOverride("font_color", new Color(0.75f, 0.85f, 1f, 1f));
        hint.VerticalAlignment = VerticalAlignment.Center;
        row.AddChild(hint);

        _chatInput = new LineEdit
        {
            PlaceholderText = "Say something to Aria…",
            CustomMinimumSize = new Vector2(0, 28),
            SizeFlagsHorizontal = Control.SizeFlags.ExpandFill,
        };
        _chatInput.TextSubmitted += OnChatSubmit;
        row.AddChild(_chatInput);

        var sendBtn = new Button { Text = "Send", CustomMinimumSize = new Vector2(80, 28) };
        sendBtn.Pressed += () => SubmitChat(_chatInput.Text);
        row.AddChild(sendBtn);

        _chatPanel = panel;
    }

    private PanelContainer _chatPanel;

    private void ToggleChat()
    {
        _chatOpen = !_chatOpen;
        if (_chatPanel != null) _chatPanel.Visible = _chatOpen;
        if (_chatOpen && _chatInput != null)
        {
            _chatInput.GrabFocus();
            _chatInput.Text = "";
        }
        GD.Print($"[Chat] overlay {(_chatOpen ? "open" : "closed")} (F2 to toggle)");
    }

    private void OnChatSubmit(string text) => SubmitChat(text);

    private void SubmitChat(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        GD.Print($"[Chat] sending to Aria: \"{text}\"");
        _llm?.SendMessage(text, _character?.BuildWorldState(_userCursor,
                                                              _windowDetector?.ForegroundTitle,
                                                              _motionClient?.LocalQueueDepth,
                                                              MotionQueueCapacity));
        if (_chatInput != null) _chatInput.Text = "";
    }

    private void MakeWindowBehave()
    {
        var hwnd = (IntPtr)DisplayServer.WindowGetNativeHandle(DisplayServer.HandleType.WindowHandle);
        if (hwnd == IntPtr.Zero) return;

        // Keep Aria always on top. We intentionally don't touch Extended Styles here:
        // adding WS_EX_LAYERED to a Vulkan/Forward+ window makes Windows switch from
        // the Vulkan-alpha compositing path to GDI-layered compositing, which doesn't
        // understand Vulkan swapchain alpha and renders the entire window white.
        SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);

        // Layer 1 — WM_NCHITTEST subclassing: for every hit-test outside Aria's body hitbox
        // we return HTTRANSPARENT, routing the click to the window underneath (same-thread path).
        _customWndProc = new WndProcDelegate(CustomWndProc);
        _originalWndProc = SetWindowLongPtr(hwnd, GWLP_WNDPROC,
            Marshal.GetFunctionPointerForDelegate(_customWndProc));
        GD.Print($"[Main] HWND=0x{hwnd:X}  WndProc hooked (orig=0x{_originalWndProc:X})");

        // Cross-process click-through is handled by the mouse-passthrough REGION set each
        // frame in UpdateClickRegion (WS_EX_TRANSPARENT alone can't cross processes, and
        // WS_EX_LAYERED whites out the window). Keep WS_EX_TRANSPARENT OFF so the region's
        // solid part — over Aria — can still catch clicks for the right-click poke.
        SetClickThrough(false);
    }

    /// <summary>Custom window procedure. Returns HTTRANSPARENT for mouse events outside
    /// Aria's body hitbox so they fall through to the window behind the overlay.
    /// All other messages are forwarded to Godot's original window procedure.</summary>
    private IntPtr CustomWndProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam)
    {
        if (msg == WM_NCHITTEST && _character != null)
        {
            // lParam packs the cursor's screen coords: low word = X, high word = Y.
            // Cast through signed short so negative virtual-desktop coords wrap correctly.
            short sx = (short)(lParam.ToInt64() & 0xFFFF);
            short sy = (short)((lParam.ToInt64() >> 16) & 0xFFFF);
            float vx = sx - _windowOrigin.X;
            float vy = sy - _windowOrigin.Y;
            if (!IsClickOnAria(vx, vy))
                return (IntPtr)HTTRANSPARENT;   // pass event to the window beneath
        }
        return CallWindowProc(_originalWndProc, hWnd, msg, wParam, lParam);
    }

    public override void _ExitTree()
    {
        // Restore Godot's original window procedure so the engine can clean up cleanly.
        if (_originalWndProc != IntPtr.Zero)
        {
            var hwnd = (IntPtr)DisplayServer.WindowGetNativeHandle(DisplayServer.HandleType.WindowHandle);
            if (hwnd != IntPtr.Zero)
                SetWindowLongPtr(hwnd, GWLP_WNDPROC, _originalWndProc);
        }
    }
}
