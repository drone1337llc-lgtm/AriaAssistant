using Godot;
using System;
using System.Collections.Generic;

public partial class CharacterController : Node3D
{
    public enum State { Idle, Walk, Turn, Climb, Fall, React }

    // WalkSpeed is in DisplayServer screen pixels per second.
    //   With the Hips translation tracks STRIPPED from every clip, 100% of
    //   Aria's horizontal travel comes from this value — the animation only
    //   moves her legs in place. To avoid foot-sliding ("moonwalking"), the
    //   body must travel at the same ground speed the planted foot sweeps at.
    //   On a 1080p monitor with the orthographic camera size=8, 1 world unit =
    //   1080/8 = 135 px, and Aria is ~1.6 units (~1.6 m) tall.
    //   She now walks with the CATWALK STRUT clip (WalkClip below), which the
    //   user calls "her strut". A runway catwalk's forward cadence is slower and
    //   more deliberate than a generic walk — about 0.9 m/s — so the matched
    //   ground speed is ~0.9 * 135 ≈ 125 px/s (vs ~160 for the plain "walk"
    //   clip). 125 is still far quicker than the old crawling 68 that prompted
    //   the "too slow to match her strut" report.
    //   TUNE LIVE in the Inspector: if her feet slide forward, LOWER this; if she
    //   moonwalks (slides backward), RAISE it. Or set WalkClip="walk" + ~160 for a
    //   plain quick walk instead of the strut.
    [Export] public float WalkSpeed = 160f;         // px/sec along a surface, matched to the walk clip
    [Export] public string WalkClip = "walk";
    [Export] public float ClimbSpeed = 240f;      // px/sec straight up a window edge
    [Export] public float FallAccel = 2400f;      // px/sec^2
    [Export] public float MaxFallSpeed = 1400f;
    [Export] public float IdleMinTime = 3f;
    [Export] public float IdleMaxTime = 8f;
    [Export] public float PerchMinTime = 8f;      // idle time when on top of a window
    [Export] public float PerchMaxTime = 20f;
    [Export] public float ClimbChance = 0.65f;    // odds an idle ends in a climb attempt
    [Export] public float AnimBlendTime = 0.15f;  // crossfade between animations (sec)
    [Export] public float CameraYawDeg = 0f;      // node yaw (deg) at which Aria faces the camera
    [Export] public float TurnSpeedDeg = 540f;    // how fast she pivots to a new facing, deg/sec
    [Export] public float TurnAnimDuration = 1.0f; // wall-clock seconds for a turn animation
    [Export] public float TurnAnimPlaybackSpeed = 3.5f; // play the 4.73s FBX at this multiplier so the visible turn takes ~TurnAnimDuration

    // Behaviour mix — the whole point of having 20+ clips is that she should
    // look like she's passing the time, not pacing the taskbar forever.
    [Export] public float DanceChance = 0.12f;        // odds a floor idle is a short dance
    [Export] public float OneShotIdleChance = 0.35f;  // odds a floor idle is look-around / yawn
    [Export] public float LingerChance = 0.45f;       // odds she stays put for another idle instead of wandering
    [Export] public float PerchStayChance = 0.65f;    // odds she keeps lounging when already on a window

    public State CurrentState { get; private set; } = State.Idle;

    // Feet position in global screen px — Main uses this for the click-through region
    public Vector2 FeetScreen => _feet;
    // Approximate top-of-head position in global screen px, for the speech bubble.
    public Vector2 HeadScreen => new(_feet.X, _feet.Y - HeadHeightPx);
    // True while she is sitting/lounging on a window ledge (used for context).
    public bool IsPerched => !OnFloor();

    [Export] public float HeadHeightPx = 300f;   // feet→head distance on screen at current camera

    private AnimationPlayer _anim;
    private WindowDetector _windows;
    private StringName _curAnim = "";            // last animation we requested

    private Rect2I _usable;          // primary screen work area, global coords (excludes taskbar)
    private float _floorY;           // feet Y when standing on the desktop floor
    private Vector2 _feet;           // feet position in global screen px
    private float _stateTimer, _stateDuration;
    private float _walkTargetX;
    private float _yaw;          // current body yaw, radians
    private float _targetYaw;    // yaw we're turning toward, radians
    private float _fallSpeed;
    private Rect2? _climbTarget;     // window we're walking toward / scaling
    private float _climbEdgeX;
    private float _turnTimer;
    private float _turnAnimDuration;    // computed from actual clip length / speed; replaces fixed export
    private bool _turnToRight;
    private float _walkTargetXAfterTurn;
    private State _afterTurn = State.Walk;
    private Skeleton3D _skeleton;
    private int _footBoneL = -1, _footBoneR = -1;
    private float _footPivotOffset = 0f;  // world-unit Y: subtract to place model feet at floor
    private bool _footCalibDone;
    private const float SupportTol = 26f;    // how close feet must be to a window top to stand on it
    private const float MinClimbHeight = 80f;   // ignore windows whose top is barely above the floor

    private static readonly string[] FloorIdleLoops = { "idle", "idle2" };
    private static readonly string[] FloorIdleOneShots = { "look", "yawn" };
    private static readonly string[] DanceAnims = { "dance_silly", "dance_tut" };

    public void Init(AnimationPlayer anim, WindowDetector windows)
    {
        _anim = anim;
        _windows = windows;
        int screen = DisplayServer.WindowGetCurrentScreen();
        _usable = DisplayServer.ScreenGetUsableRect(screen);
        _floorY = _usable.Position.Y + _usable.Size.Y;
        _feet = new Vector2(_usable.Position.X + _usable.Size.X / 2f, _floorY);

        _yaw = _targetYaw = Mathf.DegToRad(CameraYawDeg);
        Rotation = new Vector3(0f, _yaw, 0f);

        // Find Aria's skeleton for foot-height calibration (Aria is a direct child)
        var aria = GetNodeOrNull<Node3D>("Aria");
        if (aria != null)
        {
            _skeleton = FindSkeletonUnder(aria);
            if (_skeleton != null)
            {
                _footBoneL = _skeleton.FindBone("J_Bip_L_Foot");
                _footBoneR = _skeleton.FindBone("J_Bip_R_Foot");
                if (_footBoneL < 0 && _footBoneR < 0)
                    GD.PrintErr("[Aria] Foot bones not found (J_Bip_L_Foot / J_Bip_R_Foot); no floor calibration");
                else
                    GD.Print($"[Aria] Foot bones: L={_footBoneL}, R={_footBoneR}");
            }
        }

        // Debug: list all loaded animations so we can verify what the GLB import produced
        if (_anim != null)
        {
            var libs = _anim.GetAnimationLibraryList();
            GD.Print($"[Aria] AnimationPlayer has {libs.Count} libraries: [{string.Join(", ", libs)}]");
            foreach (var lib in libs)
            {
                var libObj = _anim.GetAnimationLibrary(lib);
                if (libObj != null)
                {
                    var names = libObj.GetAnimationList();
                    GD.Print($"[Aria]   Library '{lib}': {names.Count} animations: [{string.Join(", ", names)}]");
                }
            }
        }
        else
        {
            GD.PrintErr("[Aria] AnimationPlayer is null! Check that the AnimationPlayer exists at Aria/AnimationPlayer in the imported scene.");
        }

        EnterIdle();
    }

    public override void _Process(double delta)
    {
        if (_windows == null) return;
        _stateTimer += (float)delta;

        // One-time foot calibration: after the first anim frame, measure how far
        // the model's visual feet are below the character pivot in world space.
        // Subtracted in ApplyScreenPosition so feet always land at the floor line.
        if (!_footCalibDone && _skeleton != null && (_footBoneL >= 0 || _footBoneR >= 0)
            && _stateTimer > 0.1f)
        {
            CalibrateFootOffset();
            _footCalibDone = true;
        }

        switch (CurrentState)
        {
            case State.Idle:  ProcessIdle();         break;
            case State.Walk:  ProcessWalk(delta);    break;
            case State.Turn:  ProcessTurn(delta);    break;
            case State.Climb: ProcessClimb(delta);   break;
            case State.Fall:  ProcessFall(delta);    break;
            case State.React: ProcessReact();        break;
        }

        UpdateYaw(delta);
        ApplyScreenPosition();
    }

    // ── Facing ────────────────────────────────────────────────────

    private float CamYaw => Mathf.DegToRad(CameraYawDeg);

    private void FaceCamera() => _targetYaw = CamYaw;

    // Turn to a left/right side profile. +90° from camera-facing aims her at
    // +X (screen right); -90° aims at -X (screen left).
    private void FaceWalk(bool right) => _targetYaw = CamYaw + (right ? Mathf.Pi / 2f : -Mathf.Pi / 2f);

    private void UpdateYaw(double delta)
    {
        float maxStep = Mathf.DegToRad(TurnSpeedDeg) * (float)delta;
        float diff = Mathf.AngleDifference(_yaw, _targetYaw);
        _yaw = Math.Abs(diff) <= maxStep ? _targetYaw : _yaw + Math.Sign(diff) * maxStep;
        Rotation = new Vector3(0f, _yaw, 0f);
    }

    // ── Support / geometry helpers ────────────────────────────────

    private bool OnFloor() => Math.Abs(_feet.Y - _floorY) < 2f;

    // Top of a window that spans x near nearY, if any
    private float? SupportTopAt(float x, float nearY)
    {
        foreach (var r in _windows.WindowLedges)
        {
            if (x >= r.Position.X + 8 && x <= r.Position.X + r.Size.X - 8 &&
                Math.Abs(r.Position.Y - nearY) <= SupportTol)
                return r.Position.Y;
        }
        return null;
    }

    // The full rect of the window currently under our feet, if any.
    private Rect2? SupportRectAt(float x, float nearY)
    {
        foreach (var r in _windows.WindowLedges)
        {
            if (x >= r.Position.X + 8 && x <= r.Position.X + r.Size.X - 8 &&
                Math.Abs(r.Position.Y - nearY) <= SupportTol)
                return r;
        }
        return null;
    }

    // True while something is still under our feet (floor or a window top)
    private bool HasSupport()
    {
        if (OnFloor()) return true;
        var s = SupportTopAt(_feet.X, _feet.Y);
        if (s.HasValue) { _feet.Y = s.Value; return true; }  // ride the window if it moved slightly
        return false;
    }

    private List<Rect2> ClimbCandidates()
    {
        var result = new List<Rect2>();
        foreach (var r in _windows.WindowLedges)
        {
            float top = r.Position.Y;
            if (top > _floorY - MinClimbHeight) continue;          // barely off the floor
            if (top < _usable.Position.Y + 60) continue;           // too high / off-screen
            if (r.Size.X < 160) continue;                          // too narrow to perch on
            float left = r.Position.X, right = r.Position.X + r.Size.X;
            if (right < _usable.Position.X + 60 || left > _usable.Position.X + _usable.Size.X - 60)
                continue;                                          // not really on this screen
            result.Add(r);
        }
        return result;
    }

    // ── State transitions ─────────────────────────────────────────

    private void EnterIdle()
    {
        CurrentState = State.Idle;
        _stateTimer = 0f;
        FaceCamera();

        // Lounging on a window ledge → sit.
        if (!OnFloor())
        {
            float r = GD.Randf();
            string sit = r < 0.60f ? "sit" : (r < 0.85f ? "sit_talk" : "sit_clap");
            PlayAnim(sit);
            _stateDuration = (float)GD.RandRange(PerchMinTime, PerchMaxTime);
            return;
        }

        // On the floor: weight toward calm idles, with the occasional look-around,
        // yawn, or short dance so she reads as "entertaining herself".
        float roll = GD.Randf();
        if (roll < DanceChance)
        {
            string dance = PickRandom(DanceAnims);
            PlayAnim(dance);
            _stateDuration = Math.Max(AnimLength(dance), 3f);
        }
        else if (roll < DanceChance + OneShotIdleChance)
        {
            string a = PickRandom(FloorIdleOneShots);
            PlayAnim(a);
            _stateDuration = Math.Max(AnimLength(a), 2.5f);
        }
        else
        {
            string a = PickRandom(FloorIdleLoops);
            PlayAnim(a);
            _stateDuration = (float)GD.RandRange(IdleMinTime, IdleMaxTime);
        }
    }

    private void EnterWalk(float targetX)
    {
        bool toRight = targetX > _feet.X;
        float newTargetYaw = CamYaw + (toRight ? Mathf.Pi / 2f : -Mathf.Pi / 2f);

        // If the new walk direction matches where we are already pointing (or
        // are about to point at), skip the turn animation entirely. This is
        // the common case — re-walking to the same side, or coming from a
        // state that already faced that way.
        if (Mathf.Abs(Mathf.AngleDifference(_targetYaw, newTargetYaw)) < 0.05f)
        {
            CurrentState = State.Walk;
            _stateTimer = 0f;
            _walkTargetX = targetX;
            FaceWalk(toRight);
            PlayWalkClip();
            return;
        }

        // Otherwise, go through a Turn state first: play the right/left turn
        // animation, rotate to the new side profile, then resume Walk.
        _walkTargetXAfterTurn = targetX;
        EnterTurn(toRight, newTargetYaw, State.Walk);
    }

    private void EnterClimb()
    {
        CurrentState = State.Climb;
        _stateTimer = 0f;
        FaceCamera();
        PlayAnim("climb");
    }

    // A turn is now a general "pivot to targetYaw, then enter `after`" move.
    // The body rotation is driven by UpdateYaw (yaw is authoritative); the
    // turn clip is the visual flourish, so either clip ends facing correctly.
    private void EnterTurn(bool clipRight, float targetYaw, State after)
    {
        CurrentState = State.Turn;
        _stateTimer = 0f;
        _turnTimer = 0f;
        _turnToRight = clipRight;
        _afterTurn = after;
        _targetYaw = targetYaw;

        string clip = clipRight ? "turn_right" : "turn_left";
        PlayAnim(clip, TurnAnimPlaybackSpeed);

        // Compute how long the turn state lasts: exactly one clip playback.
        // (TurnAnimDuration export is ignored — it was longer than one clip,
        // causing the looping clip to play 2-3× before the state ended.)
        float raw = AnimLength(clip);
        _turnAnimDuration = raw > 0.01f ? raw / TurnAnimPlaybackSpeed : TurnAnimDuration;
    }

    // She just finished walking (a side profile). Pivot back to camera-facing
    // with a real turn clip instead of snapping, then idle. This is the
    // "transition from walking to facing the front" the user asked for.
    private void EnterTurnToFront()
    {
        float diff = Mathf.AngleDifference(_yaw, CamYaw);
        bool clipRight = diff >= 0f;
        EnterTurn(clipRight, CamYaw, State.Idle);
    }

    private void EnterFall()
    {
        CurrentState = State.Fall;
        _stateTimer = 0f;
        _fallSpeed = 0f;
        _climbTarget = null;
        PlayAnim("fall");
    }

    public void EnterReact(float duration = 3f) => PlayGesture("react", duration);

    // Public hook for the AI brain: trigger a one-shot gesture (wave, dance,
    // thankful, react, …) that plays for `duration` then returns to Idle.
    public void PlayGesture(string animName, float duration = 3f)
    {
        if (CurrentState == State.Climb || CurrentState == State.Fall || CurrentState == State.Turn) return;
        CurrentState = State.React;
        _stateTimer = 0f;
        _stateDuration = duration;
        FaceCamera();
        PlayAnim(animName);
    }

    // ── Self-healing hooks (called by HealthMonitor) ──────────────

    /// True if her feet have drifted to a NaN/Inf or far-off-screen position.
    public bool NeedsRecovery()
    {
        if (float.IsNaN(_feet.X) || float.IsNaN(_feet.Y) ||
            float.IsInfinity(_feet.X) || float.IsInfinity(_feet.Y)) return true;
        const float margin = 220f;
        if (_feet.X < _usable.Position.X - margin || _feet.X > _usable.Position.X + _usable.Size.X + margin) return true;
        if (_feet.Y < _usable.Position.Y - margin || _feet.Y > _floorY + margin) return true;
        return false;
    }

    /// Teleport back to the desktop floor and resume idling.
    public void RecoverToFloor()
    {
        _feet = new Vector2(_usable.Position.X + _usable.Size.X / 2f, _floorY);
        _fallSpeed = 0f;
        _climbTarget = null;
        _yaw = _targetYaw = CamYaw;
        EnterIdle();
    }

    /// Gently kick her back into a sensible state if animation stalled.
    public void Nudge()
    {
        if (CurrentState != State.Climb && CurrentState != State.Fall)
            EnterIdle();
    }

    // ── Per-state processing ──────────────────────────────────────

    private void ProcessIdle()
    {
        if (!HasSupport()) { EnterFall(); return; }
        if (_stateTimer < _stateDuration) return;

        _climbTarget = null;

        // Perched on a window: mostly keep lounging; sometimes stroll the
        // ledge to a new spot; rarely hop off the edge (gravity catches her).
        if (!OnFloor())
        {
            if (GD.Randf() < PerchStayChance) { EnterIdle(); return; }
            var rect = SupportRectAt(_feet.X, _feet.Y);
            if (rect.HasValue && GD.Randf() < 0.8f)
            {
                float left = rect.Value.Position.X + 30f;
                float right = rect.Value.Position.X + rect.Value.Size.X - 30f;
                EnterWalk((float)GD.RandRange(left, Math.Max(left + 1f, right)));
                return;
            }
            EnterWalk(_feet.X + (GD.Randf() < 0.5f ? -400f : 400f)); // step off → fall down
            return;
        }

        // From the floor, sometimes pick a window to scale and perch on.
        if (GD.Randf() < ClimbChance)
        {
            var candidates = ClimbCandidates();
            if (candidates.Count > 0)
            {
                var rect = candidates[(int)(GD.Randi() % (uint)candidates.Count)];
                float leftEdge = rect.Position.X - 12f;
                float rightEdge = rect.Position.X + rect.Size.X + 12f;
                // Approach whichever edge is closer, but keep it on-screen
                float minX = _usable.Position.X + 30, maxX = _usable.Position.X + _usable.Size.X - 30;
                float edge = Math.Abs(_feet.X - leftEdge) <= Math.Abs(_feet.X - rightEdge) ? leftEdge : rightEdge;
                if (edge < minX || edge > maxX)
                    edge = edge == leftEdge ? rightEdge : leftEdge;
                if (edge >= minX && edge <= maxX)
                {
                    _climbTarget = rect;
                    _climbEdgeX = edge;
                    EnterWalk(edge);
                    return;
                }
            }
        }

        // Otherwise: linger in place with another idle activity, or wander.
        if (GD.Randf() < LingerChance) { EnterIdle(); return; }

        float target = (float)GD.RandRange(_usable.Position.X + 60.0, _usable.Position.X + _usable.Size.X - 60.0);
        EnterWalk(target);
    }

    private void ProcessWalk(double delta)
    {
        if (!HasSupport()) { EnterFall(); return; }

        float dx = _walkTargetX - _feet.X;
        float step = WalkSpeed * (float)delta;

        if (Math.Abs(dx) <= step)
        {
            _feet.X = _walkTargetX;
            if (_climbTarget.HasValue) EnterClimb();
            else EnterTurnToFront();   // pivot to face front, then idle
        }
        else
        {
            _feet.X += Math.Sign(dx) * step;
        }
    }

    private void ProcessTurn(double delta)
    {
        if (!HasSupport()) { EnterFall(); return; }

        _turnTimer += (float)delta;

        // Snap root rotation to the new facing once the clip is mostly done
        // — this prevents the body from overshooting if the clip ends a few
        // frames before the wall-clock duration. UpdateYaw still drives the
        // smooth turn throughout; this just guarantees a clean handoff.
        if (_turnTimer >= _turnAnimDuration * 0.95f && !Mathf.IsEqualApprox(_yaw, _targetYaw))
            _yaw = _targetYaw;

        if (_turnTimer >= _turnAnimDuration)
        {
            if (_afterTurn == State.Walk)
            {
                _walkTargetX = _walkTargetXAfterTurn;
                CurrentState = State.Walk;
                _stateTimer = 0f;
                PlayWalkClip();
            }
            else
            {
                EnterIdle();
            }
        }
    }

    private void ProcessClimb(double delta)
    {
        if (!_climbTarget.HasValue) { EnterFall(); return; }
        var rect = _climbTarget.Value;

        // Abort if the window vanished or moved away mid-climb
        bool stillThere = false;
        foreach (var r in _windows.WindowLedges)
        {
            if (Math.Abs(r.Position.Y - rect.Position.Y) < 60 &&
                Math.Abs(r.Position.X - rect.Position.X) < 60)
            { rect = r; _climbTarget = r; stillThere = true; break; }
        }
        if (!stillThere) { EnterFall(); return; }

        _feet.X = _climbEdgeX;
        _feet.Y -= ClimbSpeed * (float)delta;

        if (_feet.Y <= rect.Position.Y)
        {
            // Topped out — step onto the window and stroll to a spot on it
            _feet.Y = rect.Position.Y;
            _climbTarget = null;
            float left = rect.Position.X + 30, right = rect.Position.X + rect.Size.X - 30;
            float spot = (float)GD.RandRange(left, Math.Max(left + 1, right));
            EnterWalk(spot);
        }
    }

    private void ProcessFall(double delta)
    {
        _fallSpeed = Math.Min(_fallSpeed + FallAccel * (float)delta, MaxFallSpeed);
        float newY = _feet.Y + _fallSpeed * (float)delta;

        // Land on the highest window top we pass through on the way down
        float landY = _floorY;
        foreach (var r in _windows.WindowLedges)
        {
            float top = r.Position.Y;
            if (_feet.X >= r.Position.X + 8 && _feet.X <= r.Position.X + r.Size.X - 8 &&
                top >= _feet.Y - 4 && top <= newY && top < landY)
                landY = top;
        }

        if (newY >= landY)
        {
            _feet.Y = landY;
            EnterIdle();
        }
        else
        {
            _feet.Y = newY;
        }
    }

    private void ProcessReact()
    {
        if (!HasSupport()) { EnterFall(); return; }
        if (_stateTimer >= _stateDuration)
            EnterIdle();
    }

    // ── Output ────────────────────────────────────────────────────

    private void ApplyScreenPosition()
    {
        // Orthographic camera (projection=1, size=8.0 in Main.tscn).
        // Visible world height = CamSize = 8 units. World Y goes +4 (top) to -4 (bottom).
        // We map _feet (screen pixels, top-left origin) to world space directly.
        const float CamSize = 8f;  // must match Camera3D.size in Main.tscn
        var vp = GetViewport().GetVisibleRect();
        float worldWidth = CamSize * (vp.Size.X / vp.Size.Y);

        // _feet is in global screen px; make it window-relative first
        // (a maximized window usually sits at the work-area origin, but don't assume).
        var winPos = DisplayServer.WindowGetPosition();
        float lx = _feet.X - winPos.X;
        float ly = _feet.Y - winPos.Y;

        float worldX = (lx / vp.Size.X - 0.5f) * worldWidth;
        float worldY = (0.5f - ly / vp.Size.Y) * CamSize;

        // _footPivotOffset is calibrated at startup: how far the model's visual
        // feet sit BELOW the pivot. Subtracting it raises the pivot so feet land
        // exactly at the floor line. Zeroed until calibration runs (~0.1s in).
        Position = new Vector3(worldX, worldY - _footPivotOffset, 0f);
    }

    // ── Animation ─────────────────────────────────────────────────

    /// <summary>
    /// Play an animation by short name, with crossfade to the previous one.
    /// Names map to the AnimationLibrary entries inside the imported Aria.glb.
    /// </summary>
    private void PlayAnim(string name, float playbackSpeed = 1f)
    {
        if (_anim == null) return;

        // Resolve the full animation key: if the library is named "" (default),
        // the key is just the short name. If it has a real name, format as "name/anim".
        StringName key = ResolveAnimKey(name);
        if (key == null)
        {
            GD.PrintErr($"[Aria] Animation '{name}' not found in any library");
            return;
        }

        // Avoid restarting the same animation every frame
        if (key == _curAnim && _anim.IsPlaying()) return;

        _curAnim = key;

        // Use a short crossfade so state transitions don't pop
        _anim.Play(key, AnimBlendTime);
        _anim.SpeedScale = playbackSpeed;
        GD.Print($"[Aria] PlayAnim('{name}') -> '{key}' (length={_anim.CurrentAnimationLength:F2}s, speed={playbackSpeed:F2}x, isPlaying={_anim.IsPlaying()})");
    }

    /// <summary>
    /// Length (seconds) of a clip by short name, or 0 if it doesn't exist.
    /// Used to time one-shot idle activities so they don't loop awkwardly.
    /// </summary>
    private float AnimLength(string shortName)
    {
        if (_anim == null) return 0f;
        StringName key = ResolveAnimKey(shortName);
        if (key == null) return 0f;
        var a = _anim.GetAnimation(key);
        return a != null ? (float)a.Length : 0f;
    }

    /// <summary>
    /// Find a full library/animation key for the given short name.
    /// Returns null if no matching animation exists.
    /// </summary>
    private StringName ResolveAnimKey(string shortName)
    {
        if (_anim == null) return null;

        foreach (var libName in _anim.GetAnimationLibraryList())
        {
            var lib = _anim.GetAnimationLibrary(libName);
            if (lib == null) continue;
            if (lib.HasAnimation(shortName))
            {
                // Godot 4: if library name is empty, the key is just the animation name.
                // If library name is non-empty, the key is "libraryName/animationName".
                if (libName.ToString().Length == 0)
                    return shortName;
                return $"{libName}/{shortName}";
            }
        }
        return null;
    }

    // Play the configured locomotion clip, falling back to the plain "walk"
    // clip if the strut didn't bake — so she never slides in a T-pose.
    private void PlayWalkClip()
    {
        if (ResolveAnimKey(WalkClip) != null) PlayAnim(WalkClip);
        else PlayAnim("walk");
    }

    private static string PickRandom(string[] arr) => arr[(int)(GD.Randi() % (uint)arr.Length)];

    // ── Foot calibration ─────────────────────────────────────────

    /// Measure how far the model's visual feet are below the CharacterController
    /// pivot when in the T-pose (called once, ~0.1s after first anim frame).
    /// Stored as _footPivotOffset and subtracted in ApplyScreenPosition so the
    /// floor line (which maps to our world-Y position) lands under the visual feet
    /// rather than under the pivot (hips), which would make her appear to float.
    private void CalibrateFootOffset()
    {
        var skelTf = _skeleton.GlobalTransform;

        float GetFootWorldY(int boneIdx)
        {
            if (boneIdx < 0) return float.MaxValue;
            var pose = _skeleton.GetBoneGlobalPose(boneIdx);
            return (skelTf * pose).Origin.Y;
        }

        float footYL = GetFootWorldY(_footBoneL);
        float footYR = GetFootWorldY(_footBoneR);

        float footY = footYL == float.MaxValue ? footYR
                    : footYR == float.MaxValue ? footYL
                    : Math.Min(footYL, footYR);

        if (footY == float.MaxValue) return;

        // footY is in world space; Position.Y is the pivot's world Y.
        // The pivot is currently placed at the world-floor line by ApplyScreenPosition.
        // Feet should be at that same line, so offset = (foot world Y) - (pivot world Y).
        _footPivotOffset = footY - Position.Y;
        GD.Print($"[Aria] Foot calibration: foot={footY:F3} pivot={Position.Y:F3} offset={_footPivotOffset:F3}");
    }

    private static Skeleton3D FindSkeletonUnder(Node root)
    {
        if (root is Skeleton3D sk) return sk;
        foreach (var child in root.GetChildren())
        {
            var found = FindSkeletonUnder(child);
            if (found != null) return found;
        }
        return null;
    }
}
