using Godot;
using System;
using System.Runtime.InteropServices;

public partial class Main : Node
{
    [DllImport("user32.dll")] private static extern bool SetWindowPos(
        IntPtr hWnd, IntPtr hWndInsertAfter, int x, int y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll")] private static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] private static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
    [DllImport("user32.dll")] private static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    private static readonly IntPtr HWND_TOPMOST = new(-1);
    private const uint SWP_NOMOVE = 0x0002, SWP_NOSIZE = 0x0001, SWP_NOACTIVATE = 0x0010;
    private const int GWL_EXSTYLE = -20, WS_EX_NOACTIVATE = 0x08000000, WS_EX_TOOLWINDOW = 0x00000080;

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

    private CharacterController _character;
    private WindowDetector _windowDetector;
    private LLMBridge _llm;
    private ExpressionController _expr;
    private TTSBridge _tts;
    private HealthMonitor _health;
    private Label _speechLabel;
    private float _speechTimer = 0f;
    private float _speechDuration = 0f;
    private bool _speaking = false;

    public override void _Ready()
    {
        // Maximize the window so Aria can roam the full desktop.
        // Required for the "character walks on the physical screen" illusion.
        DisplayServer.WindowSetMode(DisplayServer.WindowMode.Maximized);

        // Make window click-through and non-activating
        MakeWindowBehave();

        _windowDetector = GetNode<WindowDetector>("WindowDetector");
        _character = GetNode<CharacterController>("CharacterController");
        _llm = GetNode<LLMBridge>("LLMBridge");
        _speechLabel = GetNode<Label>(SpeechLabelPath);

        // The label is repositioned above Aria's head every frame; switch it
        // from the scene's full-width top anchor to a free-floating box.
        _speechLabel.SetAnchorsPreset(Control.LayoutPreset.TopLeft);
        _speechLabel.CustomMinimumSize = new Vector2(340, 0);
        _speechLabel.Size = new Vector2(340, 0);

        // The window is borderless + transparent (you can see the desktop through it),
        // so a bare white label is invisible against light desktop regions. Give it
        // a semi-opaque dark "speech bubble" panel so the text is always readable.
        var bg = new StyleBoxFlat
        {
            BgColor = new Color(0.06f, 0.06f, 0.10f, 0.82f),
            BorderColor = new Color(1, 1, 1, 0.25f),
            BorderWidthLeft = 1, BorderWidthRight = 1, BorderWidthTop = 1, BorderWidthBottom = 1,
            CornerRadiusTopLeft = 12,
            CornerRadiusTopRight = 12,
            CornerRadiusBottomLeft = 12,
            CornerRadiusBottomRight = 12,
            ContentMarginLeft = 14,
            ContentMarginRight = 14,
            ContentMarginTop = 10,
            ContentMarginBottom = 10,
        };
        _speechLabel.AddThemeStyleboxOverride("normal", bg);
        // Belt-and-braces: explicit font color + outline so text reads on any background.
        _speechLabel.AddThemeColorOverride("font_color", new Color(1, 1, 1, 1));
        _speechLabel.AddThemeColorOverride("font_outline_color", new Color(0, 0, 0, 1));
        _speechLabel.AddThemeConstantOverride("outline_size", 4);

        // Make sure the UI CanvasLayer is in front of the 3D scene.
        var uiLayer = _speechLabel.GetParent() as CanvasLayer;
        if (uiLayer != null) uiLayer.Layer = 10;

        // Step 1: Build the animation library from the imported Mixamo FBX files.
        var animBuilder = GetNodeOrNull<AnimationBuilder>("AnimationBuilder");
        if (animBuilder != null) animBuilder.Build();
        else GD.PrintErr("[Main] AnimationBuilder node not found");

        // Step 2: Find Aria's root and her AnimationPlayer (now populated).
        Node3D aria = GetNodeOrNull<Node3D>("CharacterController/Aria");
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

        _health = new HealthMonitor { Name = "HealthMonitor" };
        AddChild(_health);
        _health.Setup(_character, anim, _llm, aria);

        // Step 4: Brain → avatar. ResponseReady carries say + emotion + action.
        _llm.ResponseReady += OnResponse;

        // Greet on startup (works even offline — proves the bubble + voice path).
        GetTree().CreateTimer(2.0).Timeout += () =>
            _llm.SendMessage("You just appeared on the user's desktop. Greet them warmly in one short sentence.");

        // Schedule her first unprompted remark.
        _ambientNext = (float)GD.RandRange(AmbientMinInterval, AmbientMaxInterval);

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
        _llm.SendMessage(prompt);
    }

    /// <summary>
    /// The window covers the whole desktop, so by default it would swallow every
    /// mouse click. Restrict the clickable area to a small box around Aria;
    /// everything outside the polygon passes through to the apps underneath.
    /// </summary>
    private void UpdateClickRegion()
    {
        if (_character == null) return;

        var winPos = DisplayServer.WindowGetPosition();
        Vector2 feet = _character.FeetScreen;
        float x = feet.X - winPos.X;
        float y = feet.Y - winPos.Y;

        // Wide box: ±160px covers arm swing at full range; height -340 clears her head.
        var poly = new Vector2[]
        {
            new(x - 160, y - 340),
            new(x + 160, y - 340),
            new(x + 160, y + 10),
            new(x - 160, y + 10),
        };
        DisplayServer.WindowSetMousePassthrough(poly);

        if (_speechLabel != null && _speechLabel.Visible)
            PositionSpeechLabel();
    }

    private void PositionSpeechLabel()
    {
        if (_character == null || _speechLabel == null) return;
        var winPos = DisplayServer.WindowGetPosition();
        Vector2 head = _character.HeadScreen;
        float hx = head.X - winPos.X;
        float hy = head.Y - winPos.Y;
        var vp = GetViewport().GetVisibleRect().Size;
        const float lw = 340f;
        float labelH = Math.Max(_speechLabel.Size.Y, 44f);
        float lx = Mathf.Clamp(hx - lw / 2f, 8f, vp.X - lw - 8f);
        float ly = Mathf.Clamp(hy - labelH - 16f, 8f, vp.Y - labelH - 8f);
        _speechLabel.Position = new Vector2(lx, ly);
    }

    private void OnResponse(string say, string emotion, string action)
    {
        _tts?.Stop();                       // cut any overlapping audio

        _speechLabel.Text = say;
        const float BubbleWidth = 340f;
        const int CharsPerLine = 42;
        int lines = Math.Max(1, (int)Math.Ceiling(say.Length / (double)CharsPerLine));
        _speechLabel.Size = new Vector2(BubbleWidth, lines * 21f + 22f);
        _speechLabel.Visible = true;
        PositionSpeechLabel(); // position now, not waiting for the next _Process frame
        _speechTimer = 0f;
        _speechDuration = Mathf.Clamp(say.Length * 0.06f, 3f, 9f);
        _speaking = true;

        _expr?.SetEmotion(emotion);
        _expr?.StartTalking();
        DoAction(action);
        _tts?.Speak(say);

        GD.Print($"[Speech] say='{say}' emotion={emotion} action={action} " +
                 $"visible={_speechLabel.Visible} dur={_speechDuration:F1}s " +
                 $"canvasLayer={(_speechLabel.GetParent() as CanvasLayer)?.Layer ?? -1}");
    }

    private void DoAction(string action)
    {
        switch ((action ?? "none").Trim().ToLowerInvariant())
        {
            case "none" or "": break;   // truly no-op; don't interrupt idle
            case "wave":     _character.PlayGesture("wave", 3f); break;
            case "dance":    _character.PlayGesture(GD.Randf() < 0.5f ? "dance_silly" : "dance_tut", 4f); break;
            case "thankful": _character.PlayGesture("thankful", 3f); break;
            case "look":     _character.PlayGesture("look", 3f); break;
            case "react":    _character.PlayGesture("react", 3f); break;
            case "sit":      _character.PlayGesture(_character.IsPerched ? "sit_talk" : "react", 4f); break;
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

    public override void _Input(InputEvent e)
    {
        // Right-click near Aria sends a playful poke to the brain.
        if (e is InputEventMouseButton mb && mb.ButtonIndex == MouseButton.Right && mb.Pressed)
        {
            _llm.SendMessage("The user just clicked on you. React playfully in one short sentence.");
        }
    }

    private void MakeWindowBehave()
    {
        // Ensure always-on-top via win32 (so Aria stays visible above other windows).
        // Note: we intentionally don't set WS_EX_NOACTIVATE/WS_EX_TOOLWINDOW here —
        // they pushed Godot into "embedded" mode and broke window movement.
        var hwnd = (IntPtr)DisplayServer.WindowGetNativeHandle(DisplayServer.HandleType.WindowHandle);
        if (hwnd != IntPtr.Zero)
        {
            SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        }
    }
}
