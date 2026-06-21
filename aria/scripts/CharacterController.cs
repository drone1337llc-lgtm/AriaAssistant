using Godot;
using System;
using System.Collections.Generic;
using System.Linq;

// The Aria namespace holds the directive + world-state types (AriaDirective.cs).
// They're nested under a namespace so Main.cs, CharacterController.cs, and LLMBridge.cs
// can share them without ambiguity (Main also has a top-level Main class).
using Aria;

public partial class CharacterController : Node3D
{
	public enum State { Idle, Walk, Turn, Climb, Fall, React, WalkStart, WalkStop }

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

	// One-shot transition clips that bookend the walk loop (the "Female Start/Stop
	// Walking" mocap). Clear either to disable that phase; and if the clip didn't
	// bake into the library, the walk simply begins/ends as before (graceful no-op).
	[Export] public string WalkStartClip = "walk_start";
	[Export] public string WalkStopClip = "walk_stop";
	// Cap on the stop-walk wind-down so she settles promptly instead of lingering in a
	// long clip after reaching her spot. Set to 0 to play the clip's full length.
	[Export] public float WalkStopMaxTime = 0.40f;
	// Cap on the start-walk wind-up so she gets moving promptly instead of playing a
	// long, obviously-separate start clip before the walk loop. 0 = full clip length.
	[Export] public float WalkStartMaxTime = 0.6f;
	[Export] public float ClimbSpeed = 240f;      // px/sec straight up a window edge
	[Export] public float SitHeightDrop = 100f;  // px to drop Aria when sitting on a window so her hips land on the ledge and feet dangle
	[Export] public float FallAccel = 12000f;     // px/sec^2 — fast fall so she jumps DOWN instead of sliding
	[Export] public float MaxFallSpeed = 4000f;
	[Export] public float FallSpeedPxPerSec = 250f; // smooth-fall rate: target ~250 px/sec, so a 500px drop takes 2s
	[Export] public float IdleMinTime = 5f;
	[Export] public float IdleMaxTime = 14f;
	[Export] public float PerchMinTime = 8f;      // idle time when on top of a window
	[Export] public float PerchMaxTime = 20f;
	// Climbing is enabled — set ClimbEnabled=false in the Inspector to disable.
	[Export] public bool ClimbEnabled = true;
	[Export] public float ClimbChance = 0.45f;    // odds an idle ends in a climb attempt
	[Export] public float AnimBlendTime = 0.15f;  // crossfade between animations (sec)
	[Export] public float CameraYawDeg = 0f;      // node yaw (deg) at which Aria faces the camera
	[Export] public float TurnSpeedDeg = 540f;    // how fast she pivots to a new facing, deg/sec
	[Export] public float TurnAnimDuration = 1.0f; // wall-clock seconds for a turn animation
	[Export] public float TurnAnimPlaybackSpeed = 3.5f; // play the 4.73s FBX at this multiplier so the visible turn takes ~TurnAnimDuration

	// Behaviour mix — the whole point of having 20+ clips is that she should
	// look like she's passing the time, not pacing the taskbar forever.
	[Export] public float DanceChance = 0.12f;        // odds a floor idle is a short dance
	[Export] public float OneShotIdleChance = 0.35f;  // odds a floor idle is look-around / yawn
	[Export] public float LingerChance = 0.70f;       // odds she stays put for another idle instead of wandering
	[Export] public float PerchStayChance = 0.65f;    // odds she keeps lounging when already on a window

	// Brain-driven movement (the {move} intent in her LLM reply).
	[Export] public float DirectedWalkDistance = 360f; // px a "go left/right" step travels
	[Export] public float StayPutSeconds = 25f;        // how long "stay" suppresses auto-roaming
	private float _stayUntil = 0f;                      // game-time (s) she won't auto-roam until

	public State CurrentState { get; private set; } = State.Idle;

	// Feet position in VIEWPORT-RELATIVE (window-local) px — Main uses this
	// for the click-through region and speech-bubble placement. Origin (0,0)
	// is the top-left of the visible window; +X right, +Y down.
	public Vector2 FeetScreen => _feet;
	// Approximate top-of-head position in viewport-relative (window-local) px.
	public Vector2 HeadScreen => new(_feet.X, _feet.Y - HeadHeightPx);
	// True while she is sitting/lounging on a window ledge (used for context).
	public bool IsPerched => !OnFloor();

	[Export] public float HeadHeightPx = 300f;   // feet→head distance on screen at current camera

	private AnimationPlayer _anim;
	private WindowDetector _windows;
	private StringName _curAnim = "";            // last animation we requested

	private Rect2I _usable;          // primary screen work area, global coords (excludes taskbar)
	private float _floorY;           // feet Y in viewport-relative (window-local) px — NOT global screen px
	private Vector2 _feet;           // feet position in viewport-relative (window-local) px
	private float _winOffsetX, _winOffsetY;  // global screen px → viewport-relative: subtract these
	private float _stateTimer, _stateDuration;
	private float _walkTargetX;
	private float _walkTargetY = float.NaN;  // NaN = stay on floor; finite = target Y for walk_to (e.g. window top)
	private float _yaw;          // current body yaw, radians
	private float _targetYaw;    // yaw we're turning toward, radians
	private float _fallSpeed;
	private float _fallStartY;       // Y where fall began
	private float _fallLandedY;      // Y where she will land (floor or window top)
	private float _fallDuration;     // seconds for the fall (set on EnterFall from distance / FallSpeedPxPerSec)
	private Rect2? _climbTarget;     // window we're walking toward / scaling
	private float _climbEdgeX;
	private float _turnTimer;
	private float _turnAnimDuration;    // computed from actual clip length / speed; replaces fixed export
	private bool _turnToRight;
	private float _walkTargetXAfterTurn;
	private State _afterTurn = State.Walk;
	private Skeleton3D _skeleton;
	private int _footBoneL = -1, _footBoneR = -1;
	private int _hipBone = -1;           // J_Bip_C_Hips — used for sit/sit_clap pose calibration
	private float _footPivotOffset = 0f;  // world-unit Y: subtract to place model feet at floor
	private string _curAnimName = "";    // last anim short-name; used for per-anim foot delta

	// Per-animation foot-pivot delta. The T-pose calibration measures the
	// feet in the rest pose, but the imported FBX animations (sit, climb,
	// fall, walk) have the character's feet at a different height relative
	// to the pivot than the T-pose. Subtract this delta from the model's Y
	// to keep the visual feet at the floor line for that animation.
	// Sign: positive = raise model UP (so feet stay at floor). Empirically
	// derived from the Sitting.fbx and Jump Down.fbx we baked:
	//   - sit: hip rest Y is higher than the model's T-pose foot, so we
	//     must lift the model slightly. Negative numbers lift DOWN, which
	//     sinks the feet. We use small positive for sit to compensate.
	//   - fall: jump-down lands feet-on-floor at end, but during the
	//     animation the feet are higher. End-aligned. ~0.
	//   - climb: feet dangle, no contact. ~0.
	private static readonly Dictionary<string, float> FootDeltaPerAnim = new()
	{
		// Per-animation foot-pivot compensation. The T-pose calibration
		// measures the rest pose feet relative to the pivot; different
		// FBX animations pose the model in different hip-to-foot distances,
		// so we lift/lower the model to keep the visual feet at the floor.
		// Sign: positive = raise model UP. Negative = lower model DOWN.
		// T-pose calibration handles idle/walk fine, so those get 0. Sit
		// uses 0 too — the Sitting.fbx's hip rest is similar enough to T-pose.
		{ "idle",      0.0f },
		{ "idle2",     0.0f },
		{ "walk",      0.0f },
		{ "walk_start",0.0f },
		{ "walk_stop", 0.0f },
		{ "run",       0.0f },
		{ "turn_left", 0.0f },
		{ "turn_right",0.0f },
		{ "change_dir",0.0f },
		{ "jump",      0.0f },
		{ "fall",      0.0f },
		{ "climb",     0.0f },
		{ "sit",       0.0f },
		{ "sit_clap",  0.0f },
		{ "react",     0.0f },
		{ "wave",      0.0f },
		{ "thankful",  0.0f },
		{ "look",      0.0f },
		{ "yawn",      0.0f },
		{ "dance_wave",0.0f },
	};

	// Per-animation hip-pivot delta. Used for SIT animations (sit, sit_clap)
	// where the feet dangle below the ledge — we want the HIPS to land on
	// the ledge (not the feet on the floor). For perching sit: the Sitting.fbx
	// drops the hips to about 0.4 units below T-pose pivot. Subtracting a
	// negative value raises the model so the visual hips sit at the world-Y
	// we targeted, with feet dangling below as the animation intends.
	//
	// Sign convention: SAME as FootDeltaPerAnim. positive = raise model UP
	// (so hips at world Y). The lift is computed as (restHipY_world - currentHipY).
	// For sit, restHipY is the T-pose hip (~0.94) and the sit anim drops the
	// hip to ~0.27, so we need to RAISE the model by ~0.67 to compensate.
	//
	// This is the FIX for the "head clips the top of the screen in sit"
	// bug: the old code used FootDeltaPerAnim for sit, which dropped the
	// WHOLE model by 0.378 to put feet on floor — leaving the head
	// 0.378 units too high.
	private static readonly Dictionary<string, float> HipDeltaPerAnim = new()
	{
		{ "idle",      0.0f },
		{ "idle2",     0.0f },
		{ "walk",      0.0f },
		{ "walk_start",0.0f },
		{ "walk_stop", 0.0f },
		{ "run",       0.0f },
		{ "turn_left", 0.0f },
		{ "turn_right",0.0f },
		{ "change_dir",0.0f },
		{ "jump",      0.0f },
		{ "fall",      0.0f },
		{ "climb",     0.0f },
		{ "sit",       0.0f },   // filled in by CalibrateAllAnimFeet
		{ "sit_clap",  0.0f },   // filled in by CalibrateAllAnimFeet
		{ "react",     0.0f },
		{ "wave",      0.0f },
		{ "thankful",  0.0f },
		{ "look",      0.0f },
		{ "yawn",      0.0f },
		{ "dance_wave",0.0f },
	};
	// Set of anims where HIPS should be placed at the world-Y (feet dangle
	// below). For all other anims, the FEET are placed at the world-Y.
	private static readonly HashSet<string> AnimsUseHipDelta = new()
	{
		"sit", "sit_clap",
	};

	// Per-animation PERCH foot dangle. Used when the character is on a
	// window ledge (IsPerched == true) AND playing one of the perch-aware
	// anims in AnimsUseHipDelta. The dangle is the distance from the
	// model's PIVOT to the FEET in the animation's mid-pose, measured at
	// startup. When perched, we position the pivot so the FEET land at
	// (ledgeY + dangle), i.e. the feet dangle below the ledge by the
	// pivot-to-foot distance. Without this, the feet floated slightly
	// ABOVE the ledge (the formula anchored on the hip and lifted the
	// model by _footLiftExtra, which placed the feet at ~ledgeY + 0.02).
	// Sign: dangle is the pivot-to-foot distance in the mid-pose, always
	// positive (feet are above the pivot in the sit pose — they hang off
	// the legs). Applied as: pivot_Y = worldY - dangle, so the feet land
	// at worldY (the ledge line) and dangle below the model origin.
	private static readonly Dictionary<string, float> PerchFootDanglePerAnim = new()
	{
		{ "idle",      0.0f },
		{ "idle2",     0.0f },
		{ "walk",      0.0f },
		{ "walk_start",0.0f },
		{ "walk_stop", 0.0f },
		{ "run",       0.0f },
		{ "turn_left", 0.0f },
		{ "turn_right",0.0f },
		{ "change_dir",0.0f },
		{ "jump",      0.0f },
		{ "fall",      0.0f },
		{ "climb",     0.0f },
		{ "sit",       0.0f },   // filled in by CalibrateAllAnimFeet (~0.47)
		{ "sit_clap",  0.0f },   // filled in by CalibrateAllAnimFeet (~0.46)
		{ "react",     0.0f },
		{ "wave",      0.0f },
		{ "thankful",  0.0f },
		{ "look",      0.0f },
		{ "yawn",      0.0f },
		{ "dance_wave",0.0f },
	};
	// Small extra lift to nudge the model up a hair above the world-floor line.
	// The T-pose calibration lands the feet exactly on the floor, but in the
	// idle/standing animation the feet relax slightly and read as below the
	// floor. Positive value LIFTS the model.
	private float _footLiftExtra = 0.02f;
	private bool _footCalibDone;
	private const float SupportTol = 26f;    // how close feet must be to a window top to stand on it
	private const float MinClimbHeight = 80f;   // ignore windows whose top is barely above the floor

	// ── Directive queue (LLM-driven body control) ──────────────────────
	// The brain can submit a sequenced plan (walk there, wave, pause, sit) and
	// these execute one-at-a-time in _Process, preempting the state machine.
	// When the queue is empty, the state machine runs as before.
	private readonly Queue<Aria.AriaDirective> _directiveQueue = new();
	private Aria.AriaDirective _activeDirective;
	private float _directiveDwell = 0f;          // how long the current directive has been active (sec)
	private const float DirectiveTimeout = 30f;  // a stuck directive is killed after this
	public bool HasPendingDirectives => _activeDirective != null || _directiveQueue.Count > 0;
	public int PendingDirectiveCount => (_activeDirective != null ? 1 : 0) + _directiveQueue.Count;

	// Procedural IK layer. Set up in Init() once the skeleton is known. The IK
	// controller runs on TOP of the animation every frame; you can drive her
	// arms, spine, head, legs, and fingers to any target the LLM names.
	private AriaIKController _ik;
	private SpringBoneSimulator _spring;
	private int _lastSpringInvokeCount = 0;   // diagnostic: tracks modifier-stack activity for the spring fallback
	private bool _sitDiagLogged = false;       // one-shot log for the sit-pose diagnostic; reset on EnterSit / sit anim change
	public AriaIKController IK => _ik;

	// Motion-diffusion client. Created by Main when a motion server URL is
	// configured. The brain issues RequestMotion directives; this client
	// enqueues them with the server (cap 100) and bakes the reply into the
	// AnimationLibrary when it arrives.
	private AriaMotionClient _motionClient;
	public void SetMotionClient(AriaMotionClient c) => _motionClient = c;
	public AriaMotionClient MotionClient => _motionClient;

	private static readonly string[] FloorIdleLoops = { "idle", "idle2" };
	private static readonly string[] FloorIdleOneShots = { "look", "yawn" };
	private static readonly string[] DanceAnims = { };   // dance_tut removed — no dance on idle rolls

	public void Init(AnimationPlayer anim, WindowDetector windows)
	{
		_anim = anim;
		_windows = windows;
		int screen = DisplayServer.WindowGetCurrentScreen();
		_usable = DisplayServer.ScreenGetUsableRect(screen);
		// Compute viewport (window-local) coordinate system.
		// DisplayServer.WindowGetPosition / ScreenGetUsableRect sometimes
		// return values that don't match the actual screen layout (e.g. a
		// 1440p display reports the usable rect at y=1080..2520, and the
		// window position at y=1080). We pin everything to the viewport's
		// visible rect — that one matches the actual screen — and derive
		// _winOffsetX/_winOffsetY from it.
		var vp = GetViewport().GetVisibleRect();
		float visibleW = vp.Size.X;
		float visibleH = vp.Size.Y;
		// _floorY: bottom of the visible viewport = the actual desktop floor.
		_floorY = visibleH;
		// Horizontal: center the spawn in the middle of the visible viewport.
		_feet = new Vector2(visibleW / 2f, _floorY);
		// Offsets: global-screen-px − (these) = viewport-relative px. We use
		// the viewport as the "true" window, so the offset maps any global
		// screen coordinate into window-local space.
		//
		// For a fullscreen window on a SINGLE-monitor setup, _winOffsetY
		// is just winPos.Y. For the user's MULTI-monitor setup (Aria's game
		// window on the lower monitor, app windows on the upper monitor)
		// this is wrong: the apps end up at negative viewport y (off-screen)
		// and Aria can never climb them.
		//
		// To make climb work across monitors, we treat Aria's world as
		// spanning the upper monitor into the upper half of her viewport.
		// Apps at the upper-monitor bottom (global y = 0) land at Aria's
		// viewport y = UpperMonitorViewportY (e.g. 1080, leaving the lower
		// 360px as her floor). So:
		//   _winOffsetY = 0 − UpperMonitorViewportY  (negative)
		//   viewportY = globalY − _winOffsetY
		//              = globalY + UpperMonitorViewportY
		// For a 1080-tall upper monitor and 1440-tall viewport:
		//   globalY=0 (upper-monitor bottom)   → viewportY=1080
		//   globalY=-1080 (upper-monitor top) → viewportY=0
		const float UpperMonitorViewportY = 1080f;  // apps span the top 75% of Aria's viewport
		var winPos = DisplayServer.WindowGetPosition();
		_winOffsetX = winPos.X;
		_winOffsetY = -UpperMonitorViewportY;

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
				_hipBone = _skeleton.FindBone("J_Bip_C_Hips");
				if (_footBoneL < 0 && _footBoneR < 0)
					GD.PrintErr("[Aria] Foot bones not found (J_Bip_L_Foot / J_Bip_R_Foot); no floor calibration");
				else
					GD.Print($"[Aria] Foot bones: L={_footBoneL}, R={_footBoneR} hip={_hipBone}");
				// the walk/sit/dance animations keep playing while the LLM drives
				// arms/head/legs toward its targets.
				_ik = new AriaIKController { Name = "AriaIKController" };
				AddChild(_ik);
				_ik.Setup(_skeleton, aria);
				// Spring-bone physics for J_Sec_* bones (skirt, hair, bust).
				// Implemented as a SkeletonModifier3D so it runs in the
				// Skeleton3D's modifier stack AFTER the AnimationPlayer has
				// applied its pose — this prevents the AnimationPlayer from
				// stomping our SetBonePoseRotation() calls the same frame.
				// (The previous Node-based approach ran in our _Process, but
				// the AnimationPlayer ran in its own _Process too, and the
				// order of those two calls left the spring rotations dead.)
				_spring = new SpringBoneSimulator
				{
					Name = "SpringBoneSimulator",
				};
				// Add the modifier as a child of the Skeleton3D so it registers
				// in the modifier stack. GetSkeleton() on the modifier returns
				// the parent Skeleton3D at _Ready time.
				_skeleton.AddChild(_spring);
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
			CalibrateAllAnimFeet();
		}

		// ── Cut-short: stop the animation cleanly when it reaches the
		// user-requested cut point (set via PlayAnim(name, …, cutAtSec)).
		// Fires CutShortReached with the absolute cut time, then stops
		// the AnimationPlayer and clears the timer so the next directive /
		// state can take over without restarting the same clip.
		if (_cutAtSecActive > 0.0001f && _anim != null && _anim.IsPlaying()
			&& _anim.CurrentAnimationPosition >= _cutAtSecActive)
		{
			float hitTime = _cutAtSecActive;
			string hitName = _cutAtName;
			_anim.Stop();                          // hard stop; the next PlayAnim will restart cleanly
			_cutAtSecActive = 0f;
			_cutAtName = "";
			GD.Print($"CutShortReached anim={hitName} at {hitTime:F2}s");
			try { CutShortReached?.Invoke(hitName, hitTime); }
			catch (Exception e) { GD.PrintErr($"[Aria] CutShortReached handler threw: {e.Message}"); }
			// End the enclosing React state too (if any) so the directive
			// completes promptly instead of waiting out the full React
			// duration. Without this, a 0.5s cut-short on a directive with
			// a 2s duration would still keep the state machine in React
			// for 1.5s of dead time.
			if (CurrentState == State.React)
			{
				_stateTimer = _stateDuration;
			}
		}

		// 1) LLM-driven directives take priority. They can drive any state and
		//    preempt the random/idle brain. The state machine still runs for
		//    in-flight physics (climb/fall) and when the queue is empty.
		bool directiveActive = _activeDirective != null;
		if (!directiveActive && _directiveQueue.Count > 0)
		{
			_activeDirective = _directiveQueue.Dequeue();
			_directiveDwell = 0f;
			GD.Print($"[Directive] dequeue → {_activeDirective.Describe()}  remaining={_directiveQueue.Count}");
			StartDirective(_activeDirective);
			directiveActive = true;
		}
		if (directiveActive)
		{
			_directiveDwell += (float)delta;
			bool done = TickDirective(_activeDirective, delta);
			if (_directiveDwell > DirectiveTimeout)
			{
				GD.PrintErr($"[Directive] timeout after {DirectiveTimeout:F0}s on {_activeDirective.Describe()} — clearing");
				_activeDirective = null;
			}
			else if (done)
			{
				GD.Print($"[Directive] complete: {_activeDirective.Describe()}");
				_activeDirective = null;
			}
		}
		else
		{
			// 2) No directive in flight — run the autonomous state machine.
			switch (CurrentState)
			{
				case State.Idle:  ProcessIdle();         break;
				case State.Walk:  ProcessWalk(delta);    break;
				case State.Turn:  ProcessTurn(delta);    break;
				case State.Climb: ProcessClimb(delta);   break;
				case State.Fall:  ProcessFall(delta);    break;
				case State.React: ProcessReact();        break;
				case State.WalkStart: ProcessWalkStart(delta); break;
				case State.WalkStop:  ProcessWalkStop(delta);  break;
			}
		}

		UpdateYaw(delta);
		ApplyScreenPosition();

		// Procedural IK layer — applies additive IK pose deltas on top of the
		// animation. Runs AFTER the state machine so it sees the latest bone
		// poses; the IK controller itself is what writes new pose rotations
		// back into the Skeleton3D.
		_ik?.Update(delta);
		// Spring-bone physics for skirt/hair/bust is now a SkeletonModifier3D
		// child of the Skeleton3D — it runs in the skeleton's modifier stack
		// AFTER the AnimationPlayer (and after our procedural IK above, since
		// we just called SetBonePoseRotation on the skeleton). The modifier
		// stack calls _ProcessModificationWithDelta() on our SpringBoneSimulator
		// automatically, in the skeleton's deferred update tick.
		//
		// SAFETY FALLBACK: if the modifier stack is NOT running (e.g. due to
		// a C# binding issue or order-of-operations race), the springs would
		// be silently dormant. We track the last seen InvokeCount from the
		// modifier and, if it stalls, call _spring.Update(delta) directly
		// from here. This is belt-and-suspenders: the manual call races with
		// the AnimationPlayer (so its SetBonePoseRotation will get stomped
		// the next frame), but the user still sees SOME motion rather than
		// none, and the diagnostic log tells us the modifier isn't firing.
		if (_spring != null)
		{
			int prevCount = _lastSpringInvokeCount;
			_lastSpringInvokeCount = _spring.InvokeCount;
			// Godot 4.6.3: SkeletonModifier3D bone writes don't reach the skinned
			// mesh, but _Process writes do (IK above proves it). So when
			// DriveFromProcess is set, run the spring sim here EVERY frame, right
			// after IK. Otherwise fall back to the old "modifier stalled" check.
			if (_spring.DriveFromProcess || prevCount == _lastSpringInvokeCount)
			{
				_spring.Update(delta);
			}
		}

		// One-shot diagnostic: when the FIRST IK directive is applied,
		// print the active chain + the world target + the actual bone
		// transform we wrote. Useful for "why isn't it moving?" debugging.
		// (Comment out to silence.)
		if (_ik != null && _ik.Active.Count > 0 && !_ikDiagnosticsLogged)
		{
			foreach (var (name, ac) in _ik.Active)
			{
				GD.Print($"[IK] active chain '{name}' target=({ac.Target.X:F2},{ac.Target.Y:F2},{ac.Target.Z:F2}) mode={ac.Mode} weight={ac.Weight:F2}");
			}
			_ikDiagnosticsLogged = true;
		}
	}

	private bool _ikDiagnosticsLogged;

	// ── Facing ────────────────────────────────────────────────────

	private float CamYaw => Mathf.DegToRad(CameraYawDeg);

	private void FaceCamera() => _targetYaw = CamYaw;

	// Turn to a left/right side profile. +90° from camera-facing aims her at
	// +X (screen right); -90° aims at -X (screen left).
	private void FaceWalk(bool right) => _targetYaw = CamYaw + (right ? Mathf.Pi / 2f : -Mathf.Pi / 2f);

	// Turn her back to the user (180° from camera) — used while climbing so she
	// faces the wall/window she's scaling.
	private void FaceAway() => _targetYaw = CamYaw + Mathf.Pi;

	private void UpdateYaw(double delta)
	{
		float maxStep = Mathf.DegToRad(TurnSpeedDeg) * (float)delta;
		float diff = Mathf.AngleDifference(_yaw, _targetYaw);
		_yaw = Math.Abs(diff) <= maxStep ? _targetYaw : _yaw + Math.Sign(diff) * maxStep;
		Rotation = new Vector3(0f, _yaw, 0f);
	}

	// ── Support / geometry helpers ────────────────────────────────

	private bool OnFloor() => Math.Abs(_feet.Y - _floorY) < 2f;

	// Top of a window that spans x near nearY, if any.
	// _windows.WindowLedges is in GLOBAL screen px (Win32 GetWindowRect).
	// nearY is in viewport-relative px, so we add _winOffsetY to compare.
	private float? SupportTopAt(float x, float nearY)
	{
		foreach (var r in _windows.WindowLedges)
		{
			float rx = r.Position.X - _winOffsetX;
			float ry = r.Position.Y - _winOffsetY;
			if (x >= rx + 8 && x <= rx + r.Size.X - 8 &&
				Math.Abs(ry - nearY) <= SupportTol)
				return ry;
		}
		return null;
	}

	// The full rect of the window currently under our feet, if any.
	// Returned rect is in viewport-relative coords.
	private Rect2? SupportRectAt(float x, float nearY)
	{
		foreach (var r in _windows.WindowLedges)
		{
			float rx = r.Position.X - _winOffsetX;
			float ry = r.Position.Y - _winOffsetY;
			if (x >= rx + 8 && x <= rx + r.Size.X - 8 &&
				Math.Abs(ry - nearY) <= SupportTol)
				return new Rect2(new Vector2(rx, ry), r.Size);
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
		var vp = GetViewport().GetVisibleRect();
		float visibleW = vp.Size.X;
		foreach (var r in _windows.WindowLedges)
		{
			// Convert the global-px rect to viewport-relative for comparison.
			float top = r.Position.Y - _winOffsetY;
			float left = r.Position.X - _winOffsetX;
			float right = left + r.Size.X;
			if (top > _floorY - MinClimbHeight) continue;          // barely off the floor
			if (top < 60f) continue;                               // too high / off-screen
			if (r.Size.X < 160) continue;                          // too narrow to perch on
			if (right < 60f || left > visibleW - 60f)
				continue;                                          // not really on this screen
			// Return rect in viewport-relative coords so callers don't re-subtract.
			result.Add(new Rect2(new Vector2(left, top), r.Size));
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
			// Don't shift _feet.Y. The "sit" clip naturally drops the hips
			// below the T-pose pivot and repositions the feet; altering
			// _feet here fights the animation and causes HasSupport to
			// fail on the next frame (sit → fall loop). Trust the
			// animation; if visual position is off, tune the FBX.
			PlayAnim("sit");
			_sitDiagLogged = false;   // re-arm the one-shot sit diag on next sit entry
			_stateDuration = (float)GD.RandRange(PerchMinTime, PerchMaxTime);
			return;
		}

		// On the floor: weight toward calm idles, with the occasional look-around,
		// yawn, or short dance so she reads as "entertaining herself".
		float roll = GD.Randf();
		if (roll < DanceChance && DanceAnims.Length > 0)
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
			_walkTargetX = targetX;
			FaceWalk(toRight);
			EnterWalkStart();   // play the step-off clip, then the walk loop
			return;
		}

		// Otherwise, go through a Turn state first: play the right/left turn
		// animation, rotate to the new side profile, then resume Walk.
		_walkTargetXAfterTurn = targetX;
		EnterTurn(toRight, newTargetYaw, State.Walk);
	}

	private void EnterClimb()
	{
		// Drop any persistent IK — a climb animation drives both arms and we
		// don't want an old "reach for window" pinning the hand mid-air.
		if (AutoReleaseIKOnGesture) _ik?.ReleaseAll();
		CurrentState = State.Climb;
		_stateTimer = 0f;
		FaceAway();           // back to the user while scaling the window
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
		// Use the new PlayAnim signature (no playback-speed overload). The
		// turn clip needs a higher playback rate so the visible turn takes
		// ~TurnAnimDuration, not the clip's full ~4.7s. We do that via the
		// explicit SetAnimPlaybackSpeed helper, separate from the per-anim
		// travel-speed scale.
		PlayAnim(clip);
		SetAnimPlaybackSpeed(TurnAnimPlaybackSpeed);

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
		if (AutoReleaseIKOnGesture) _ik?.ReleaseAll();
		CurrentState = State.Fall;
		_stateTimer = 0f;
		_fallSpeed = 0f;
		_climbTarget = null;
		_fallStartY = _feet.Y;
		_fallLandedY = _floorY;
		// Find the highest window top we'll land on. If we're starting on
		// a window, the landing is that window's top (no descent). If we're
		// above a window, we'll land on it. Otherwise the floor.
		foreach (var r in _windows.WindowLedges)
		{
			float top = r.Position.Y - _winOffsetY;
			float left = r.Position.X - _winOffsetX;
			if (_feet.X >= left + 8 && _feet.X <= left + r.Size.X - 8 &&
				top >= _feet.Y - 4 && top < _fallLandedY)
				_fallLandedY = top;
		}
		// Duration is time-based with a floor of 0.85s and a ceiling of 1.4s.
		// The previous formula used Math.Max(0.5f, dist / 250) which gave 0.50s
		// for any perch-to-floor drop under 125px — the fall completed in
		// ~15 frames at 30 fps and the eye read it as a "snap". 0.85s is the
		// minimum duration at which a quadratic ease-out (fast start, slow end)
		// visibly conveys a fall: ~25 frames of mid-descent, with the slow-end
		// portion overlapping the landing animation. 320 px/s is the speed
		// equivalent so longer falls still feel proportional — a 500px drop
		// takes 1.4s (clamped to ceiling) instead of 2.0s. The visible motion
		// is slower per-frame but the duration is right.
		float dist = Mathf.Abs(_fallStartY - _fallLandedY);
		float dur = Mathf.Clamp(dist / 320f, 0.85f, 1.4f);
		_fallDuration = dur;
		PlayAnim("fall");
		// Time-scale the jump-down clip so its full launch→descend→land arc plays
		// across the (short) descent instead of freezing on the opening wind-up.
		// At 1x, a 0.85-1.4s drop only ever showed the first ~25-40% of the 3.38s
		// clip — the static crouch — which read as a "stiff slide". Matching the
		// clip rate to the fall duration (capped at 3x so it never looks frantic)
		// makes the actual falling + landing motion visible.
		float fallClip = AnimLength("fall");
		if (fallClip > 0.01f && _fallDuration > 0.01f)
			SetAnimPlaybackSpeed(Mathf.Clamp(fallClip / _fallDuration, 1.0f, 3.0f));
		GD.Print($"[Fall] enter: dist={dist:F0}px dur={_fallDuration:F2}s clipRate={(fallClip > 0.01f ? Mathf.Clamp(fallClip / _fallDuration, 1.0f, 3.0f) : 1f):F2}x feet=({_feet.X:F0},{_feet.Y:F0}) -> landY={_fallLandedY:F0}");
	}

	public void EnterReact(float duration = 3f) => PlayGesture("react", duration);

	// Public hook for the AI brain: trigger a one-shot gesture (wave, dance,
	// thankful, react, …) that plays for `duration` then returns to Idle.
	// Auto-releases any active IK chains so the gesture's animation actually
	// drives the arms/legs (without this, "wave" plays on top of "reach for
	// the window" and you get a zombie arm stuck at the window).
	[Export] public bool AutoReleaseIKOnGesture = true;
	public void PlayGesture(string animName, float duration = 3f)
	{
		if (CurrentState == State.Climb || CurrentState == State.Fall || CurrentState == State.Turn) return;
		// Drop any persistent IK bindings so the new animation has the rig to itself.
		// (Override-mode chains like fingers stay released; a follow-up ik_reach
		//  re-asserts the new target.)
		if (AutoReleaseIKOnGesture) _ik?.ReleaseAll();
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
		var vp = GetViewport().GetVisibleRect();
		const float margin = 220f;
		if (_feet.X < -margin || _feet.X > vp.Size.X + margin) return true;
		if (_feet.Y < -margin || _feet.Y > _floorY + margin) return true;
		return false;
	}

	/// Teleport back to the desktop floor and resume idling.
	public void RecoverToFloor()
	{
		var vp = GetViewport().GetVisibleRect();
		_feet = new Vector2(vp.Size.X / 2f, _floorY);
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

		// If the brain told her to stay put, keep idling here instead of roaming.
		if (NowSeconds() < _stayUntil) { EnterIdle(); return; }

		// From the floor, sometimes pick a window to scale and perch on
		// (only when ClimbEnabled is true in the Inspector).
		if (ClimbEnabled && GD.Randf() < ClimbChance)
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
			// If a directive set a non-floor target Y close to a window top
			// under us, snap onto that window (perch). Otherwise keep the
			// standard climb-or-stop behaviour.
			if (!float.IsNaN(_walkTargetY))
			{
				var s = SupportTopAt(_feet.X, _feet.Y);
				if (s.HasValue && Math.Abs(s.Value - _walkTargetY) < 40f)
				{
					_feet.Y = s.Value;
					_climbTarget = null;
					EnterIdle();
					return;
				}
			}
			if (_climbTarget.HasValue) EnterClimb();
			else EnterWalkStop();   // settle to a stop, then pivot to face front
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
				RestoreWalkTargetAfterTurn();
				EnterWalkStart();   // step-off clip → walk loop, after the turn
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
		// _climbTarget is in viewport-relative coords (set by ClimbCandidates).
		var rect = _climbTarget.Value;

		// Abort if the window vanished or moved away mid-climb.
		// _windows.WindowLedges is in global px; convert for comparison.
		bool stillThere = false;
		foreach (var r in _windows.WindowLedges)
		{
			float rx = r.Position.X - _winOffsetX;
			float ry = r.Position.Y - _winOffsetY;
			if (Math.Abs(ry - rect.Position.Y) < 60 &&
				Math.Abs(rx - rect.Position.X) < 60)
			{
				rect = new Rect2(new Vector2(rx, ry), r.Size);
				_climbTarget = rect;
				stillThere = true;
				break;
			}
		}
		if (!stillThere) { EnterFall(); return; }

		_feet.X = _climbEdgeX;
		_feet.Y -= ClimbSpeed * (float)delta;

		if (_feet.Y <= rect.Position.Y)
		{
			// Topped out — step onto the window and stroll to a spot on it.
			// _feet.X was clamped to _climbEdgeX (just outside the window edge),
			// so the first HasSupport() check inside ProcessWalk would fail and
			// send us straight to EnterFall. Snap feet fully INSIDE the rect
			// (clamped to interior) so the first HasSupport() always finds a
			// window under us. Then pick a TARGET spot in the INTERIOR of the
			// rect, biased 30-70% from the climb edge in the chosen direction
			// — this makes her walk visibly across the ledge instead of
			// stopping in place or being clamped back to the climb edge.
			//
			// Why center-bias instead of "walkDist from edge + clamp": on
			// narrow ledges (~640px), the edge is close to the interior
			// boundary and a "200-500 px from edge" walk could land
			// OUTSIDE the interior. The old Mathf.Clamp then snapped the
			// spot back to rectLeft+30 (basically the edge) and she barely
			// moved. Center-bias picks a point in [30%, 70%] of the interior
			// width from the climb edge, which is always a real walk across.
			_feet.Y = rect.Position.Y;
			_climbTarget = null;
			float rectLeft = rect.Position.X + 30f;
			float rectRight = rect.Position.X + rect.Size.X - 30f;
			float interiorWidth = rectRight - rectLeft;
			float walkDir = (_climbEdgeX < rect.Position.X + rect.Size.X * 0.5f) ? 1f : -1f;
			float walkFrac = (float)GD.RandRange(0.30, 0.70);
			float spot = walkDir > 0
				? rectLeft + walkFrac * interiorWidth
				: rectRight - walkFrac * interiorWidth;
			float safeX = Mathf.Clamp(spot, rect.Position.X + 16f, rect.Position.X + rect.Size.X - 16f);
			// Stand at the edge she just climbed (snapped just inside the rect so
			// HasSupport() passes), THEN walk across to safeX. Previously _feet.X
			// was snapped straight to the destination and EnterWalk had zero
			// distance to cover — she appeared to teleport onto the ledge.
			_feet.X = Mathf.Clamp(_climbEdgeX, rect.Position.X + 16f, rect.Position.X + rect.Size.X - 16f);
			GD.Print($"[Climb] topped out: startX={_feet.X:F0} y={_feet.Y:F0} -> walkTo={safeX:F0} walkFrac={walkFrac:F2} dir={walkDir:F0} interiorW={interiorWidth:F0}");
			EnterWalk(safeX);
		}
	}

	private void ProcessFall(double delta)
	{
		// Smooth time-based fall: interpolate _feet.Y from _fallStartY to
		// _fallLandedY over _fallDuration. This keeps the fall in sync with
		// the Jump Down animation (3.38s); instead of physics-accelerating
		// to 4000 px/s in 0.3s and "teleporting" the body, we drop at
		// FallSpeedPxPerSec px/sec (default 250) so a 500px perch-to-floor
		// drop takes ~2s — matches the animation's slow descent + landing.
		//
		// IMPORTANT: _stateTimer is already incremented at the top of _Process,
		// so we do NOT add delta again here — that would double-count and the
		// fall would complete in half the intended duration. EnterFall() resets
		// _stateTimer = 0 so the normalized t starts at 0.
		float t = _fallDuration > 0.01f ? Mathf.Clamp(_stateTimer / _fallDuration, 0f, 1f) : 1f;
		// EASE-OUT (quadratic): 1 - (1-t)². Real gravity is fast at the start
		// and slows toward the end (think of a skydiver reaching terminal
		// velocity, or a ball decelerating as it lands). The previous
		// smoothstep Hermite was still reading as a "snap" in the round-3
		// recording at 0:35-0:36 because the middle of the fall was the
		// fastest portion — and the user's eye is drawn to the bottom of
		// the screen where the late-fall deceleration happens. Ease-OUT
		// (fast start, slow end) matches the visual intuition for a fall
		// and keeps the visible late-fall portion slow.
		//
		// Ease direction reference:
		//   t*t           : ease-IN  (slow start, fast end) — "snap at the bottom"
		//   1-(1-t)²      : ease-OUT (fast start, slow end) — gravity-like
		//   t³(6t²-15t+10): smoothstep (zero derivative at both ends) — symmetric
		//   t             : linear — uniform speed
		float eased = 1f - (1f - t) * (1f - t);
		_feet.Y = _fallStartY + (_fallLandedY - _fallStartY) * eased;

		if (t >= 1f)
		{
			_feet.Y = _fallLandedY;
			GD.Print($"[Fall] landed: feet=({_feet.X:F0},{_feet.Y:F0}) t={t:F2} eased={eased:F2} dur={_fallDuration:F2}s");
			EnterIdle();
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
		// _feet is in VIEWPORT-RELATIVE (window-local) px, top-left origin, so
		// no window-position subtraction is needed — the viewport rect IS the
		// window. (Earlier this subtracted DisplayServer.WindowGetPosition(),
		// which can return a broken value when the OS reports a usable-rect
		// bigger than the actual screen.)
		const float CamSize = 8f;  // must match Camera3D.size in Main.tscn
		var vp = GetViewport().GetVisibleRect();
		float worldWidth = CamSize * (vp.Size.X / vp.Size.Y);

		float lx = _feet.X;
		float ly = _feet.Y;

		float worldX = (lx / vp.Size.X - 0.5f) * worldWidth;
		float worldY = (0.5f - ly / vp.Size.Y) * CamSize;

		// _footPivotOffset is calibrated at startup: how far the model's visual
		// feet sit BELOW the pivot in T-pose (~0.094u). Subtracting it raises
		// the pivot so feet land exactly at the floor line. Zeroed until
		// calibration runs (~0.1s in).
		//
		// For sit/sit_clap we anchor on the HIPS instead of the feet: the feet
		// are supposed to dangle below the ledge. We use _tposeHipY (~0.89u,
		// the T-pose hip height above the pivot) as the anchor, and the
		// per-anim hipDelta compensates for the sit animation's specific
		// hip-local Y. (The OLD code used FootDeltaPerAnim for sit, which
		// dropped the whole model by 0.378 to put feet on the floor — pushing
		// the head off the top of the screen. That was the "sit head clip"
		// bug.)
		//
		// PERCH OVERRIDE (round 4): when IsPerched AND the current anim is in
		// AnimsUseHipDelta (sit / sit_clap), use PerchFootDanglePerAnim
		// instead. The dangle is the pivot-to-foot distance in the mid-pose
		// (calibrated at startup). With dangle=0.472 (sit) we set
		// pivot_Y = worldY - 0.472, so the feet land at worldY (the ledge)
		// and dangle below the model origin by 0.472u — i.e. the natural
		// pivot-to-foot length of the sit pose. The previous formula used
		// _tposeHipY = 0.894 with _footLiftExtra = 0.02, which placed the
		// feet at worldY + 0.02 — i.e. 0.02u ABOVE the ledge, reading as
		// "feet floating in mid-air above the window ledge". Dropping the
		// _footLiftExtra on the perch path and using the dangle instead
		// puts the feet at worldY (the ledge) and the rest of the body
		// above it, with the legs naturally hanging over the edge.
		float anchorTposeY;
		float animDelta;
		float lift = _footLiftExtra;
		bool perchedHipAnim = IsPerched && AnimsUseHipDelta.Contains(_curAnimName);
		if (perchedHipAnim)
		{
			// PERCH: anchor on FEET-in-world using the per-anim dangle.
			// The pivot moves up by the dangle so the feet land at worldY.
			// No liftExtra — the dangle is already accurate.
			float dangle = PerchFootDanglePerAnim.TryGetValue(_curAnimName, out float dv) ? dv : 0f;
			anchorTposeY = dangle;
			animDelta = 0f;
			lift = 0f;
			// Single-shot diagnostic for the sit case (the user's reported bug).
			// Confirms the computed feet-Y matches the ledge-Y. Fires once per
			// sit entry to avoid log spam.
			if (_curAnimName == "sit" && !_sitDiagLogged)
			{
				float pivotY = worldY - anchorTposeY + lift + animDelta;
				float feetY = pivotY + dangle;
				GD.Print($"[Sit] PERCH diag: worldY={worldY:F3} dangle={dangle:F3} pivotY={pivotY:F3} feetY={feetY:F3} ledge=feetY? {Math.Abs(feetY - worldY) < 0.01f} dangleBelow=(worldY - feetY):{worldY - feetY:F3}");
				_sitDiagLogged = true;
			}
		}
		else if (AnimsUseHipDelta.Contains(_curAnimName))
		{
			anchorTposeY = _tposeHipY;
			animDelta = HipDeltaPerAnim.TryGetValue(_curAnimName, out float hv) ? hv : 0f;
		}
		else
		{
			anchorTposeY = _footPivotOffset;
			animDelta = FootDeltaPerAnim.TryGetValue(_curAnimName, out float v) ? v : 0f;
		}
		Position = new Vector3(worldX, worldY - anchorTposeY + lift + animDelta, 0f);
	}

	// ── Animation ─────────────────────────────────────────────────

	// Per-animation travel speed default table. Used when the
	// MotionLibraryMirror hasn't loaded the server-supplied spec yet
	// (offline / pre-load) — gives the in-place travel system a sensible
	// baseline so e.g. a "wave" doesn't physically walk the body forward
	// and a "walk" loop moves at the right cadence. Keys are controller
	// short names; values are world units per second (the in-place
	// horizontal translation rate applied while the animation plays).
	//
	// For the locomotion anims (walk/run/sneak/climb) the values are real
	// travel speeds that match the rest of the project's walk-speed math
	// (WalkSpeed=160 px/s, the orthographic camera maps 1 world unit to
	// ~135 px on a 1080p monitor, so 1.4 m/s ≈ 190 px/s ≈ 1.4 world u/s).
	// For the in-place gestures the value is 0 — those clips don't move
	// the body, the per-anim travel scale just gets ignored.
	private static readonly Dictionary<string, float> DefaultTravelSpeed = new(StringComparer.OrdinalIgnoreCase)
	{
		// Locomotion
		{ "walk",    1.4f },    // ~0.9 m/s strut, matches the visual foot cadence
		{ "run",     3.0f },    // ~3 m/s sprint
		{ "sneak",   0.7f },    // ~0.5 m/s stealthy
		{ "climb",   0.4f },    // vertical climb rate in world units / sec
		// In-place (no travel)
		{ "sit",     0.0f },
		{ "idle",    0.0f },
		{ "jump",    0.0f },
		{ "fall",    0.0f },
		{ "yawn",    0.0f },
		{ "wave",    0.0f },
		{ "sit_clap",0.0f },
		{ "clap",    0.0f },
		{ "sit_in",  0.0f },
		{ "sit_out", 0.0f },
	};

	/// <summary>Resolve a per-animation travel speed in world units per
	/// second. Prefers the MotionLibraryMirror spec (server-authoritative);
	/// falls back to the hard-coded table; finally defaults to 0.</summary>
	private float ResolveTravelSpeed(string shortName)
	{
		var mirror = Aria.MotionLibraryMirror.Instance;
		if (mirror?.AnimSources != null && mirror.AnimSources.TryGetValue(shortName, out var spec))
			return spec.TravelSpeed;
		if (DefaultTravelSpeed.TryGetValue(shortName, out float def))
			return def;
		return 0f;
	}

	// Event raised by the controller when a PlayAnim cut-short point is
	// reached. The handler receives the anim short name + the absolute
	// time (seconds) at which the cut was applied. Useful for chaining
	// a follow-up directive (e.g. "/play wave 0.5" then "say hi" once
	// the wave finishes its first half).
	public event Action<string, float> CutShortReached;

	// The cut-short target the user requested on the last PlayAnim call.
	// 0.0 = no cut. Tracked here so _Process can detect when the player
	// crosses it and fire the event + stop the animation cleanly.
	private float _cutAtSecActive = 0f;
	private string _cutAtName = "";

	/// <summary>
	/// Play an animation by short name, with crossfade to the previous one.
	/// Names map to the AnimationLibrary entries inside the imported Aria.glb.
	///
	/// Parameters:
	///   name        — controller short name (e.g. "wave", "walk").
	///   speedScale  — multiplier on the per-anim travel speed. 1.0 = use
	///                 the anim's natural cadence; 0.5 = half-speed travel;
	///                 0.0 = no horizontal motion even if the anim is a
	///                 locomotion clip. Does NOT change the AnimationPlayer
	///                 playback rate (use SetAnimPlaybackSpeed for that).
	///   cutAtSec    — absolute time (sec) at which to stop the animation
	///                 and fire CutShortReached. 0.0 = no cut.
	///   cutAtFrac   — if true, cutAtSec is treated as a fraction of
	///                 DurationSec (0.0..1.0). Default false.
	/// </summary>
	public void PlayAnim(string name, float speedScale = 1.0f, float cutAtSec = 0.0f, bool cutAtFrac = false)
	{
		if (_anim == null) return;

		// ── Tuner: flush the previous play's observation ─────────────
		// We compute "actual travel" as the _feet.X delta between this
		// PlayAnim call and the previous one — that's the body travel
		// that happened during the previous clip. Expected travel is the
		// theoretical distance per the per-anim travel speed × duration ×
		// pxPerWorldUnit × the user-supplied speedScale. We skip the
		// flush for in-place anims (expected ~ 0) because their ratio
		// would explode to ±inf.
		if (_tuner != null && !string.IsNullOrEmpty(_tunePrevAnim))
		{
			float actualPx = _feet.X - _tunePrevStartFeetX;
			if (_tunePrevExpectedPx > 0.5f)   // skip in-place anims
			{
				_tuner.RecordPlay(
					_tunePrevAnim,
					_tunePrevUserScale,
					new Vector2(actualPx, 0f),
					new Vector2(_tunePrevExpectedPx, 0f));
			}
		}

		// Resolve the full animation key: if the library is named "" (default),
		// the key is just the short name. If it has a real name, format as "name/anim".
		StringName key = ResolveAnimKey(name);
		if (key == null)
		{
			GD.PrintErr($"[Aria] Animation '{name}' not found in any library");
			return;
		}

		// Compute the absolute cut time (seconds). The fraction form needs
		// the anim's DurationSec, which we can read from the resolved key
		// before we kick the player. If the user asked for a cut but we
		// can't measure the length, just no-op the cut (safer than firing
		// at time 0).
		float cutAbs = 0f;
		if (cutAtSec > 0.0001f)
		{
			var animRes = _anim.GetAnimation(key);
			float dur = animRes != null ? (float)animRes.Length : 0f;
			cutAbs = cutAtFrac && dur > 0.01f ? cutAtSec * dur : cutAtSec;
			if (cutAbs > 0.01f)
			{
				_cutAtSecActive = cutAbs;
				_cutAtName = name;
			}
			else
			{
				_cutAtSecActive = 0f;
				_cutAtName = "";
			}
		}
		else
		{
			_cutAtSecActive = 0f;
			_cutAtName = "";
		}

		// Avoid restarting the same animation every frame — unless the new
		// call has a cut-short that hasn't fired yet, in which case we need
		// to restart so the timer starts fresh from t=0.
		bool restartForCut = _cutAtSecActive > 0.0001f;
		if (key == _curAnim && _anim.IsPlaying() && !restartForCut) return;

		_curAnim = key;
		_curAnimName = name;

		// Resolve the per-anim travel speed and remember the (clamped) speed
		// scale so other systems (e.g. ProcessWalk) can read it.
		float travel = ResolveTravelSpeed(name);
		// Tuner: multiply the user-supplied scale by the auto-tuned scale
		// (returns 1.0 until N>=10 plays of this anim). The user value is
		// NEVER overridden — only multiplied. Tuner output is also
		// clamped to the [0.5, 2.0] safety band inside Combine().
		float userScale = _tuner != null ? _tuner.Combine(name, speedScale) : speedScale;
		_speedScale = Mathf.Clamp(userScale, 0f, 4f);   // hard ceiling at 4x
		// Effective travel = per-anim speed × user scale. Stored separately
		// from the AnimationPlayer's playback rate (which stays 1.0 unless
		// the caller asked for a playback tweak via SetAnimPlaybackSpeed).
		_curTravelSpeed = travel * _speedScale;

		// ── Tuner: start tracking this play ─────────────────────────
		// Capture the body position at start so the NEXT PlayAnim can
		// compute the actual-vs-expected travel delta. Expected travel
		// is the per-anim speed × clip duration × px/world-unit × the
		// RAW user-supplied scale (not the tuned one — the tuner is
		// measuring how off the source animation is from reality, not
		// compounding with its own past corrections).
		_tunePrevAnim = name;
		_tunePrevStartFeetX = _feet.X;
		float clipDur = (float)_anim.CurrentAnimationLength;
		float pxPerUnit = GetViewport().GetVisibleRect().Size.Y / 8f;   // cam.Size=8
		_tunePrevExpectedPx = travel * clipDur * pxPerUnit * Mathf.Max(0f, speedScale);
		_tunePrevUserScale = speedScale;

		// Use a short crossfade so state transitions don't pop
		_anim.Play(key, AnimBlendTime);
		// The AnimationPlayer's playback rate stays at 1.0 here. The
		// "speed" param the LLM sends is a TRAVEL-SPEED multiplier, not a
		// playback-rate multiplier — they're different concerns. A caller
		// who wants playback-rate scaling uses SetAnimPlaybackSpeed().
		_anim.SpeedScale = 1.0f;
		GD.Print($"[Aria] PlayAnim('{name}') -> '{key}' (length={_anim.CurrentAnimationLength:F2}s, " +
				 $"travel={_curTravelSpeed:F2}u/s [scale={_speedScale:F2}x * base={travel:F2}], " +
				 $"cutAt={_cutAtSecActive:F2}s{(cutAtFrac ? " (frac)" : "")}, " +
				 $"isPlaying={_anim.IsPlaying()})");
	}

	/// <summary>Set the AnimationPlayer's playback rate (1.0 = normal).
	/// Separate from the per-anim travel speed scale; used internally by
	/// the turn clip to play its 4.7s clip in ~1.3s of wall clock.</summary>
	public void SetAnimPlaybackSpeed(float speed)
	{
		if (_anim != null) _anim.SpeedScale = speed;
	}

	// Per-anim travel speed the current PlayAnim resolved. Read by
	// ProcessWalk / the in-place translation system to slide the body
	// at the right rate. Defaults to 0 = "no in-place translation".
	private float _curTravelSpeed = 0f;
	// The most recent speedScale value passed to PlayAnim.
	private float _speedScale = 1.0f;
	// Public read-only access for the IK / locomotion layers.
	public float CurrentTravelSpeed => _curTravelSpeed;
	public float CurrentSpeedScale => _speedScale;

	// ── AnimSpeedTuner hookup ─────────────────────────────────────
	//
	// The tuner is a per-anim self-tuning multiplier. It observes actual
	// vs expected travel for every PlayAnim call and slowly adjusts the
	// effective speed so locomotion anims match their intended cadence.
	// Injected from Main._Ready(); null is fine (tuner is optional).
	private Aria.AnimSpeedTuner _tuner;
	/// <summary>Inject the singleton tuner. Called from Main._Ready().</summary>
	public void SetTuner(Aria.AnimSpeedTuner tuner) { _tuner = tuner; }

	// Tracking for the in-flight play: when a NEW PlayAnim call lands we
	// compute the actual-vs-expected delta of the PREVIOUS play and feed
	// it to the tuner, then start a new tracking window.
	private string _tunePrevAnim = "";
	private float _tunePrevStartFeetX = 0f;
	private float _tunePrevExpectedPx = 0f;
	private float _tunePrevUserScale = 1.0f;

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

	// ── Walk start / stop transitions ────────────────────────────
	// Short one-shot mocap clips that bookend the walk loop. Each guards on
	// ResolveAnimKey: if the clip isn't in the baked library we fall straight
	// through to the previous behaviour, so locomotion can never get stuck.

	private void EnterWalkStart()
	{
		if (ResolveAnimKey(WalkStartClip) == null) { BeginWalkLoop(); return; }
		CurrentState = State.WalkStart;
		_stateTimer = 0f;
		float full = AnimLength(WalkStartClip);
		_stateDuration = WalkStartMaxTime > 0f ? Math.Min(full, WalkStartMaxTime) : full;
		PlayAnim(WalkStartClip);
	}

	private void ProcessWalkStart(double delta)
	{
		if (!HasSupport()) { EnterFall(); return; }
		// Accelerate from a near-stand up to full walk speed across the (capped) start
		// clip, so by the time the walk loop takes over there's no speed pop and she
		// doesn't dawdle at the start.
		float p = _stateDuration > 0.01f ? Mathf.Clamp(_stateTimer / _stateDuration, 0f, 1f) : 1f;
		float speedFactor = Mathf.Lerp(0.55f, 1.0f, p);
		float dx = _walkTargetX - _feet.X;
		if (Math.Abs(dx) > 0.01f)
			_feet.X += Math.Sign(dx) * WalkSpeed * speedFactor * (float)delta;
		if (_stateTimer >= _stateDuration) BeginWalkLoop();
	}

	private void BeginWalkLoop()
	{
		CurrentState = State.Walk;
		_stateTimer = 0f;
		PlayWalkClip();
	}

	private void EnterWalkStop()
	{
		if (ResolveAnimKey(WalkStopClip) == null) { EnterTurnToFront(); return; }
		CurrentState = State.WalkStop;
		_stateTimer = 0f;
		float fullStop = AnimLength(WalkStopClip);
		_stateDuration = WalkStopMaxTime > 0f ? Math.Min(fullStop, WalkStopMaxTime) : fullStop;
		PlayAnim(WalkStopClip);
	}

	private void ProcessWalkStop(double delta)
	{
		if (!HasSupport()) { EnterFall(); return; }
		if (_stateTimer >= _stateDuration) EnterTurnToFront();
	}

	// ── Brain-driven body commands ───────────────────────────────
	// Her LLM "brain" calls these to direct her body at a high level (the {move}
	// intent in its reply); the state machine above carries them out.

	private float NowSeconds() => (float)(Time.GetTicksMsec() / 1000.0);

	/// <summary>
	/// Autonomy-loop entry point: walk to an absolute viewport-relative X position.
	/// Safe to call any time — ignored during climb/fall. Clamps to screen bounds.
	/// </summary>
	public void WalkTo(float targetX)
	{
		if (CurrentState == State.Climb || CurrentState == State.Fall) return;
		var vp = GetViewport().GetVisibleRect();
		EnterWalk(Mathf.Clamp(targetX, 40f, vp.Size.X - 40f));
	}

	/// <summary>High-level locomotion the brain can request: left/right/come/roam/stay.</summary>
	public void CommandMove(string dir)
	{
		dir = (dir ?? "stay").Trim().ToLowerInvariant();
		// Don't interrupt a climb, fall, or turn — let those finish to avoid jank.
		if (CurrentState == State.Climb || CurrentState == State.Fall || CurrentState == State.Turn)
			return;

		switch (dir)
		{
			case "left":
				_stayUntil = 0f;
				EnterWalk(_feet.X - DirectedWalkDistance);
				break;
			case "right":
				_stayUntil = 0f;
				EnterWalk(_feet.X + DirectedWalkDistance);
				break;
			case "come":
			case "here":
			case "approach":
			case "toward_me":
				_stayUntil = 0f;
				EnterWalk(_usable.Position.X + _usable.Size.X * 0.5f);  // stroll toward centre screen
				break;
			case "roam":
			case "wander":
				_stayUntil = 0f;   // clear any "stay" → resume autonomous wandering
				break;
		default:               // "stay" / "still" / "none" / unknown → settle, suppress roaming
			_stayUntil = NowSeconds() + StayPutSeconds;
			if (CurrentState == State.Walk) EnterIdle();
			break;
		}
	}

	// ── Brain-driven directive queue (LLM full-takeover mode) ──────────
	// The brain's reply can carry a "directives" array. Submit them here and
	// the controller will execute them in order, preempting the random/idle
	// state machine until the queue is empty.  Each Submit* call REPLACES the
	// pending queue (so a fresh reply supersedes an earlier one) unless the
	// caller asks to append.

	/// <summary>Enqueue a single directive; clears any pending queue (most LLM
	/// replies are self-contained plans).</summary>
	public void SubmitDirective(AriaDirective d, bool append = false)
	{
		if (d == null) return;
		if (!append)
		{
			_directiveQueue.Clear();
			_activeDirective = null;
		}
		_directiveQueue.Enqueue(d);
		GD.Print($"[Directive] enqueue {d.Describe()}  queue={_directiveQueue.Count}");
	}

	/// <summary>Enqueue a batch of directives in the given order.</summary>
	public void SubmitDirectives(IEnumerable<AriaDirective> directives, bool append = false)
	{
		if (directives == null) return;
		if (!append)
		{
			_directiveQueue.Clear();
			_activeDirective = null;
		}
		foreach (var d in directives) if (d != null) _directiveQueue.Enqueue(d);
		GD.Print($"[Directive] enqueue batch of {directives.Count()}  total={_directiveQueue.Count}");
	}

	/// <summary>Cancel all pending directives and let the state machine take over again.</summary>
	public void ClearDirectives()
	{
		int dropped = (_activeDirective != null ? 1 : 0) + _directiveQueue.Count;
		_activeDirective = null;
		_directiveQueue.Clear();
		if (dropped > 0) GD.Print($"[Directive] cleared {dropped} pending");
	}

	// ── World state snapshot for the brain ─────────────────────────────
	// Called by Main before each SendMessage so the LLM can plan directives
	// against the actual scene (window positions, cursor, current emotion, …).

	/// <summary>Build a JSON-serializable snapshot of the avatar's current
	/// situation. Cheap to call (allocates a small object tree); safe to call
	/// every reply. The list of windows is capped at 5 nearest-by to keep the
	/// prompt small.</summary>
	public Aria.WorldState BuildWorldState(Vector2? userCursor = null, string foregroundTitle = "",
		int? motionQueueDepth = null, int? motionQueueCapacity = null,
		List<string> motionRecent = null)
	{
		var vp = GetViewport().GetVisibleRect();
		var ws = new Aria.WorldState
		{
			Feet = FeetScreen,
			Head = HeadScreen,
			State = CurrentState.ToString().ToLowerInvariant(),
			IsPerched = IsPerched,
			IdleSeconds = _stateTimer,
			Emotion = _lastEmotion ?? "neutral",
			ScreenW = vp.Size.X,
			ScreenH = vp.Size.Y,
			FloorY = _floorY,
			UserCursor = userCursor,
			Foreground = foregroundTitle ?? "",
			MotionQueueDepth = motionQueueDepth,
			MotionQueueCapacity = motionQueueCapacity,
			MotionRecent = motionRecent ?? new List<string>(),
		};

		// Take the 5 windows closest to her feet, in horizontal distance order.
		// Each window gets a one-word hint the LLM can lean on (tall, narrow,
		// near, far-left, etc.) without computing geometry.
		if (_windows != null)
		{
			var ranked = new List<(int Id, float X, float Y, float W, float H, float Dist, string Hint)>();
			int id = 0;
			foreach (var r in _windows.WindowLedges)
			{
				float vx = r.Position.X - _winOffsetX;
				float vy = r.Position.Y - _winOffsetY;
				float dist = Math.Abs(vx + r.Size.X * 0.5f - FeetScreen.X);
				string hint = DescribeWindowHint(vx, r.Size.X, r.Size.Y, FeetScreen, vp.Size.X);
				ranked.Add((id, vx, vy, r.Size.X, r.Size.Y, dist, hint));
				id++;
			}
			ranked.Sort((a, b) => a.Dist.CompareTo(b.Dist));
			int max = Math.Min(5, ranked.Count);
			for (int i = 0; i < max; i++)
			{
				var w = ranked[i];
				ws.Windows.Add(new WorldState.WindowInfo
				{
					Id = w.Id, X = w.X, Y = w.Y, W = w.W, H = w.H, Hint = w.Hint,
				});
			}
		}
		return ws;
	}

	private static string DescribeWindowHint(float vx, float vw, float vh, Vector2 feet, float screenW)
	{
		float midX = vx + vw * 0.5f;
		string side = midX < screenW * 0.33f ? "left" : midX > screenW * 0.66f ? "right" : "center";
		string size = vh > 400 ? "tall" : vh < 200 ? "short" : vw < 250 ? "narrow" : "wide";
		string reach = Math.Abs(midX - feet.X) < 200 ? "near" : "far";
		return $"{side} {size} {reach}";
	}

	// Track the last emotion the brain set on us so the WorldState can report it.
	private string _lastEmotion;
	public void SetEmotionTag(string emotion) => _lastEmotion = string.IsNullOrWhiteSpace(emotion) ? "neutral" : emotion.Trim().ToLowerInvariant();

	// ── Directive execution (StartDirective / TickDirective) ────────────
	// StartDirective: called once when a directive becomes active; resolves any
	// named target to concrete coordinates and triggers the right state transition.
	// TickDirective: called every frame; returns true when the directive is done.

	private void StartDirective(AriaDirective d)
	{
		_directiveDwell = 0f;
		_stayUntil = 0f;  // a directive overrides the brain's "stay" timer
		switch (d.Kind)
		{
			case DirectiveKind.Idle:
				EnterIdle();
				break;

			case DirectiveKind.TurnTo:
				{
					float targetYaw;
					if (!float.IsNaN(d.YawDeg)) targetYaw = Mathf.DegToRad(d.YawDeg);
					else if (d.Target != DirectiveTarget.None) targetYaw = YawToFace(d.Target);
					else targetYaw = CamYaw;  // default to camera
					_queuedTurnYaw = targetYaw;
					if (Mathf.Abs(Mathf.AngleDifference(_yaw, targetYaw)) < 0.05f)
					{
						// already there — skip
					}
					else
					{
						bool clipRight = Mathf.AngleDifference(_yaw, targetYaw) >= 0f;
						EnterTurn(clipRight, targetYaw, State.Idle);
					}
				}
				break;

			case DirectiveKind.WalkTo:
				{
					// Convert NaN Y → floor (so walk_to x,y=NaN,500 means "walk to x, stay on the floor").
					float y = float.IsNaN(d.Y) ? _floorY : d.Y;
					_walkTargetX = Mathf.Clamp(d.X, 40f, GetViewport().GetVisibleRect().Size.X - 40f);
					_walkTargetY = Mathf.Clamp(y, 60f, _floorY);
					_climbTarget = null;  // fresh walk
					// No-op guard: if the walk target is essentially where we already
					// are, skip the whole turn-walk-stop sequence. Otherwise the state
					// machine thrashes and looks like a glitch.
					if (Mathf.Abs(_walkTargetX - _feet.X) < 50f)
					{
						GD.Print($"[Directive] walk_to: already at {_walkTargetX:F0}, skipping");
						break;
					}
					bool toRight = _walkTargetX > _feet.X;
					float targetYaw = CamYaw + (toRight ? Mathf.Pi / 2f : -Mathf.Pi / 2f);
					if (Mathf.Abs(Mathf.AngleDifference(_yaw, targetYaw)) < 0.05f)
					{
						EnterWalkStart();
					}
					else
					{
						_walkTargetXAfterTurn = _walkTargetX;
						_queuedWalkTargetY = _walkTargetY;
						EnterTurn(toRight, targetYaw, State.Walk);
					}
				}
				break;

			case DirectiveKind.WalkToward:
				{
					var pt = ResolveTarget(d.Target);
					if (pt.HasValue)
					{
						// If the resolved target is essentially where we are,
						// skip the whole walk — the state machine would otherwise
						// turn + step + unstep and look like a glitch.
						if (Mathf.Abs(pt.Value.X - _feet.X) < 50f)
						{
							GD.Print($"[Directive] walk_toward: already at {pt.Value.X:F0}, skipping");
							break;
						}
						d.X = pt.Value.X;
						d.Y = float.IsNaN(d.Y) ? _floorY : d.Y;
						// Re-enter StartDirective with a WalkTo by swapping Kind in-place
						// (the queue is ours; no aliasing).
						d.Kind = DirectiveKind.WalkTo;
						StartDirective(d);
					}
					else
					{
						GD.PrintErr($"[Directive] walk_toward: target '{d.Target}' could not be resolved");
					}
				}
				break;

			case DirectiveKind.Climb:
				{
					var rect = PickClimbTarget(d.WindowId);
					if (rect.HasValue)
					{
						_climbTarget = rect;
						_climbEdgeX = NearestEdgeX(rect.Value);
						_climbEdgeX = Mathf.Clamp(_climbEdgeX, 40f, GetViewport().GetVisibleRect().Size.X - 40f);
						_walkTargetX = _climbEdgeX;
						_walkTargetY = _floorY;
						bool toRight = _walkTargetX > _feet.X;
						float targetYaw = CamYaw + (toRight ? Mathf.Pi / 2f : -Mathf.Pi / 2f);
						if (Mathf.Abs(Mathf.AngleDifference(_yaw, targetYaw)) < 0.05f)
							EnterWalkStart();
						else
						{
							_walkTargetXAfterTurn = _walkTargetX;
							_queuedWalkTargetY = _walkTargetY;
							EnterTurn(toRight, targetYaw, State.Walk);
						}
					}
					else
					{
						GD.PrintErr("[Directive] climb: no suitable window nearby");
					}
				}
				break;

			case DirectiveKind.HopOff:
				// Fall works regardless of perch; EnterFall will land her on
				// the highest window under her or the floor.
				EnterFall();
				break;

			case DirectiveKind.Gesture:
				{
					string name = string.IsNullOrWhiteSpace(d.Name) ? "react" : d.Name;
					float dur = d.Duration > 0.05f ? d.Duration : 3f;
					// PlayGesture already handles "no-op during climb/fall/turn".
					PlayGesture(name, dur);
				}
				break;

			case DirectiveKind.Play:
				{
					// Like Gesture but with per-anim speedScale and cut-short.
					// The LLM emits this as
					//   {"action":"play", "anim":"wave", "speed":0.7, "cut_at":0.5, "cut_at_frac":true}
					// We honour the same climb/fall/turn guard as PlayGesture
					// (those state transitions own the body and shouldn't be
					//  hijacked mid-flight by a one-shot play).
					if (CurrentState == State.Climb || CurrentState == State.Fall || CurrentState == State.Turn) break;
					if (AutoReleaseIKOnGesture) _ik?.ReleaseAll();
					string name = string.IsNullOrWhiteSpace(d.Name) ? "react" : d.Name;
					float dur = d.Duration > 0.05f ? d.Duration : 3f;
					CurrentState = State.React;
					_stateTimer = 0f;
					_stateDuration = dur;
					FaceCamera();
					// Pass through speedScale + cutAt (frac-aware) to PlayAnim.
					PlayAnim(name, d.SpeedScale, d.CutAtSec, d.CutAtFrac);
				}
				break;

			case DirectiveKind.Pause:
				// Pause is just a dwell timer; no state change. TickDirective will
				// wait until _directiveDwell >= duration. Stay on whatever she's on
				// (usually Idle).
				if (CurrentState == State.Climb || CurrentState == State.Fall) EnterIdle();
				break;

			case DirectiveKind.Say:
				// Out-of-band: LLMBridge already emitted the speech bubble. Nothing
				// to do for the body. The directive is considered "done" on the
				// next TickDirective call.
				break;

			// ── Procedural IK directives ──────────────────────────────────
			case DirectiveKind.IkReach:
			case DirectiveKind.IkPoint:
			{
				if (_ik == null) { GD.PrintErr("[Directive] IkReach: IK controller not initialized"); break; }
				var target = ResolveWorldTarget(d);
				if (!target.HasValue) { GD.PrintErr("[Directive] IkReach: target could not be resolved"); break; }
				var pole = ComputePoleHint(d);
				_ik.SolveAndApply(d.Name, target.Value, pole,
								  AriaIKController.BlendMode.Additive,
								  weight: d.Weight > 0 ? d.Weight : 1f,
								  holdSeconds: -1f);  // persistent until released
				GD.Print($"[Directive] ik_{d.Kind.ToString().ToLowerInvariant()} chain={d.Name} target=({target.Value.X:F0},{target.Value.Y:F0},{target.Value.Z:F0})");
				break;
			}

			case DirectiveKind.IkLook:
			{
				if (_ik == null) break;
				var target = ResolveWorldTarget(d);
				if (!target.HasValue) break;
				// Use the 2-bone neck chain — faster + more controllable than spine
				_ik.SolveAndApply("head", target.Value, null,
								  AriaIKController.BlendMode.Override, 1f, -1f);
				break;
			}

			case DirectiveKind.IkLean:
			{
				if (_ik == null) break;
				// Resolve lean direction. Spine chain reaches forward in world space;
				// we offset the spine tip toward the lean target.
				var vp = GetViewport().GetVisibleRect();
				var hips = _skeleton?.GetBoneGlobalPose(_skeleton.FindBone("J_Bip_C_Hips")).Origin ?? new Vector3(0, 0, 0);
				var head = _skeleton?.GetBoneGlobalPose(_skeleton.FindBone("J_Bip_C_Head")).Origin ?? hips + new Vector3(0, 1.6f, 0);
				float amount = Mathf.Clamp(d.Amount, 0f, 1f);
				if (amount < 0.01f) amount = 0.4f;
				// Translate the head target by (lean x, 0, lean z) where the axis
				// depends on the named direction. For "left" we shift head -X, etc.
				var leanOffset = new Vector3(0, 0, 0);
				switch ((d.Direction ?? "forward").ToLowerInvariant())
				{
					case "forward": case "front": leanOffset.Z = -0.6f * amount; break;
					case "back": case "behind": leanOffset.Z = 0.4f * amount; break;
					case "left": leanOffset.X = -0.4f * amount; break;
					case "right": leanOffset.X = 0.4f * amount; break;
				}
				var target = head + leanOffset;
				_ik.SolveAndApply("spine", target, null,
								  AriaIKController.BlendMode.Additive, amount, -1f);
				break;
			}

			case DirectiveKind.IkTwist:
			{
				if (_ik == null) break;
				// Twist the upper body around the world Y axis by d.YawDeg and tilt
				// forward/back by d.PitchDeg. We approximate by reaching the spine
				// tip at a yaw-rotated point. (For a real "twist" you'd need an
				// extra yaw-only chain; this is a reasonable v1.)
				var hips = _skeleton?.GetBoneGlobalPose(_skeleton.FindBone("J_Bip_C_Hips")).Origin ?? Vector3.Zero;
				var head = _skeleton?.GetBoneGlobalPose(_skeleton.FindBone("J_Bip_C_Head")).Origin ?? hips;
				float yaw = float.IsNaN(d.YawDeg) ? 0 : Mathf.DegToRad(d.YawDeg);
				float pitch = float.IsNaN(d.PitchDeg) ? 0 : Mathf.DegToRad(d.PitchDeg);
				var toHead = head - hips;
				var rotated = new Vector3(
					(float)(toHead.X * Math.Cos(yaw) - toHead.Z * Math.Sin(yaw)),
					toHead.Y - (float)Math.Sin(pitch) * toHead.Length() * 0.3f,
					(float)(toHead.X * Math.Sin(yaw) + toHead.Z * Math.Cos(yaw)));
				_ik.SolveAndApply("spine", hips + rotated, null,
								  AriaIKController.BlendMode.Additive, 1f, -1f);
				break;
			}

			case DirectiveKind.IkStep:
			case DirectiveKind.IkLiftLeg:
			{
				if (_ik == null) break;
				string hand = (d.Hand ?? "left").ToLowerInvariant();
				string legChain = hand == "right" ? "leg_right" : "leg_left";
				var hips = _skeleton?.GetBoneGlobalPose(_skeleton.FindBone("J_Bip_C_Hips")).Origin ?? Vector3.Zero;
				// x/y are in viewport-relative px; convert to world units (heuristic)
				float scale = GetViewport().GetVisibleRect().Size.Y / 8f;  // px per world unit
				var target = new Vector3(
					hips.X + (float.IsNaN(d.X) ? 0 : d.X) / scale * 0.01f,   // 0.01 = 1% of screen width per world unit
					hips.Y - (float.IsNaN(d.Y) ? 0 : d.Y) / scale * 0.01f,
					d.Height > 0 ? d.Height / scale : 0f);
				_ik.SolveAndApply(legChain, target, null,
								  AriaIKController.BlendMode.Additive, 1f, -1f);
				break;
			}

			case DirectiveKind.IkGrip:
			{
				if (_ik == null) break;
				// Finger pose presets. We approximate each preset by curling
				// the proximal joints of the named hand's fingers toward the
				// palm. The simplest implementation: a "closed" preset is just
				// override-rotate every finger bone 80° inward. We'll refine
				// later with a proper finger IK chain.
				string hand = (d.Hand ?? "left").ToLowerInvariant();
				string prefix = hand == "right" ? "R" : "L";
				float close = Mathf.Clamp(d.Amount, 0f, 1f);
				if (close < 0.01f) close = 1f;
				switch ((d.Name ?? "closed").ToLowerInvariant())
				{
					case "point":
						// Index extended, others curled
						ApplyFingerCurl(prefix, "Index", 0.05f, _ik);   // mostly straight
						ApplyFingerCurl(prefix, "Middle", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Ring", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Little", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Thumb", 0.5f * close, _ik);
						break;
					case "peace":
						ApplyFingerCurl(prefix, "Index", 0.05f, _ik);
						ApplyFingerCurl(prefix, "Middle", 0.05f, _ik);
						ApplyFingerCurl(prefix, "Ring", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Little", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Thumb", 0.5f * close, _ik);
						break;
					case "thumbs_up":
						ApplyFingerCurl(prefix, "Thumb", 0.05f, _ik);
						ApplyFingerCurl(prefix, "Index", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Middle", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Ring", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Little", 0.9f * close, _ik);
						break;
					case "open":
					default:
						ApplyFingerCurl(prefix, "Index", 0.05f, _ik);
						ApplyFingerCurl(prefix, "Middle", 0.05f, _ik);
						ApplyFingerCurl(prefix, "Ring", 0.05f, _ik);
						ApplyFingerCurl(prefix, "Little", 0.05f, _ik);
						ApplyFingerCurl(prefix, "Thumb", 0.1f, _ik);
						break;
					case "closed":
					case "fist":
						ApplyFingerCurl(prefix, "Index", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Middle", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Ring", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Little", 0.9f * close, _ik);
						ApplyFingerCurl(prefix, "Thumb", 0.7f * close, _ik);
						break;
				}
				break;
			}

			case DirectiveKind.IkRelease:
			{
				_ik?.Release(d.Name);
				break;
			}

			case DirectiveKind.IkReleaseAll:
			{
				_ik?.ReleaseAll();
				break;
			}

			case DirectiveKind.IkHoldPose:
			{
				// No-op: the existing IK bindings stay active. The directive
				// completes when the dwell timer in TickDirective hits Duration.
				break;
			}

			case DirectiveKind.RequestMotion:
			{
				// Hand off to the motion-diffusion client (separate Node). It
				// will HTTP-POST to the AI server, and the server's eventual
				// reply triggers a new AnimationLibrary entry.
				_motionClient?.RequestMotion(d.Prompt, d.Frames, d.Name);
				break;
			}
		}
	}

	// ── IK helpers ────────────────────────────────────────────────────
	// Simple per-finger curl: rotate each finger's proximal joint toward the
	// palm. Used for the IkGrip presets. This is a coarse approximation — for
	// hand-grade fidelity you'd add a separate 3-bone FABRIK chain per finger.
	private void ApplyFingerCurl(string sidePrefix, string finger, float curl, AriaIKController ik)
	{
		if (ik == null || _skeleton == null) return;
		string prox = $"J_Bip_{sidePrefix}_{finger}1";
		int idx = _skeleton.FindBone(prox);
		if (idx < 0) return;
		// Chain name format expected by AriaIKChains.Resolve: "index_l" / "index_r" /
		// "thumb_l" / "thumb_r" / "middle_l" / "middle_r" / "ring_l" / "ring_r" /
		// "pinky_l" / "pinky_r"
		string chainName = $"{finger.ToLowerInvariant()}_{(sidePrefix == "R" ? "r" : "l")}";
		// The "target" for an Override-mode finger chain is a "place" the tip
		// should reach (closer to the palm = more curled). We use the proximal
		// joint's current position as the target; the chain solver will pull
		// the tip into the proximal + a small downward offset (= toward palm).
		var proxPos = _skeleton.GetBoneGlobalPose(idx).Origin;
		var palmTarget = proxPos + new Vector3(0.04f, -0.08f, 0.0f) * curl;
		_ik.SolveAndApply(chainName, palmTarget, null,
						  AriaIKController.BlendMode.Override, 1f, -1f);
	}

	// Convert a directive's (x, y, target, …) into a world-space Vector3 for IK.
	// x, y are viewport-relative pixels (matches the existing locomotion API).
	// target=NamedTarget uses Main's cached _userCursor or nearest window.
	// Where IK targets land in world space. The LLM gives us viewport-relative
	// pixels (x, y) — but Aria is a 3D object at z≈0 in the orthographic camera,
	// so a "target in front of her" is some positive z (toward the camera at z=10).
	// Without this offset, the arms would try to reach the body's midline plane and
	// the head would look at the chest — visually invisible motion. Push targets
	// forward by IK_FORWARD_Z world units so the LLM's 2D intent maps to a 3D
	// target the brain can visibly act on.
	private const float IK_FORWARD_Z = 1.5f;

	private Vector3? ResolveWorldTarget(AriaDirective d)
	{
		if (d.Target != DirectiveTarget.None)
		{
			var resolved = ResolveTarget(d.Target);
			if (resolved.HasValue)
			{
				var r = resolved.Value;
				// Convert viewport-relative px to world units
				var vp = GetViewport().GetVisibleRect();
				float scale = vp.Size.Y / 8f;
				// world: x = (px/screenW - 0.5) * worldWidth, y = (0.5 - px/screenH) * camSize
				float worldW = 8f * vp.Size.X / vp.Size.Y;
				return new Vector3((r.X / vp.Size.X - 0.5f) * worldW,
								   (0.5f - r.Y / vp.Size.Y) * 8f,
								   IK_FORWARD_Z);
			}
		}
		if (!float.IsNaN(d.X) && !float.IsNaN(d.Y))
		{
			var vp = GetViewport().GetVisibleRect();
			float worldW = 8f * vp.Size.X / vp.Size.Y;
			return new Vector3((d.X / vp.Size.X - 0.5f) * worldW,
							   (0.5f - d.Y / vp.Size.Y) * 8f,
							   IK_FORWARD_Z);
		}
		// Z field is set (the debug scene uses 3D coords) — honour it
		if (!float.IsNaN(d.X) && !float.IsNaN(d.Y) && !float.IsNaN(d.Z))
		{
			return new Vector3(d.X, d.Y, d.Z);
		}
		return null;
	}

	// A pole hint for the arm IK — keeps the elbow on the back-side of the
	// body so the arm doesn't twist into the chest.
	private Vector3? ComputePoleHint(AriaDirective d)
	{
		if (d.Name == null) return null;
		if (d.Name.StartsWith("arm_left") || d.Name == "l_arm" || d.Name == "left_arm")
			return new Vector3(0, 1f, -1f);  // back-up
		if (d.Name.StartsWith("arm_right") || d.Name == "r_arm" || d.Name == "right_arm")
			return new Vector3(0, 1f, -1f);
		return null;
	}

	private bool TickDirective(AriaDirective d, double delta)
	{
		// The state machine (ProcessTurn, ProcessWalk, etc.) is what actually
		// drives the body forward — but the main loop SUPPRESSES it while a
		// directive is active (line 264 switch is gated on _activeDirective).
		// So if a directive's StartDirective puts the state machine into a
		// working state (Turn, Walk, WalkStart, WalkStop, React, Climb, Fall),
		// the matching Process*() must be called from here or the body never
		// advances and the directive's `State.Idle` completion check hangs
		// until the 30-second watchdog kills it.
		switch (CurrentState)
		{
			case State.Turn:      ProcessTurn(delta);       break;
			case State.Walk:      ProcessWalk(delta);       break;
			case State.WalkStart: ProcessWalkStart(delta);  break;
			case State.WalkStop:  ProcessWalkStop(delta);   break;
			case State.React:     ProcessReact();           break;
			case State.Climb:     ProcessClimb(delta);      break;
			case State.Fall:      ProcessFall(delta);       break;
		}

		switch (d.Kind)
		{
			case DirectiveKind.Idle:
			case DirectiveKind.Pause:
			{
				float needed = d.Duration > 0.05f ? d.Duration : 2f;
				return _directiveDwell >= needed;
			}

			case DirectiveKind.TurnTo:
				// Complete when state is back to Idle (turn clip finished +
				// ProcessTurn called EnterIdle).
				return CurrentState == State.Idle && _directiveDwell > 0.1f;

			case DirectiveKind.WalkTo:
			case DirectiveKind.WalkToward:
			{
				// Done when state is Idle (walk_stop finished + turn back to front).
				// Mid-walk, fall, etc. means we're not done yet.
				return CurrentState == State.Idle && _directiveDwell > 0.2f;
			}

			case DirectiveKind.Climb:
				// Done when we've topped out and are walking on the window top.
				return CurrentState == State.Idle && _directiveDwell > 0.2f;

			case DirectiveKind.HopOff:
				// Done when we land (state back to Idle, feet at or below floor).
				return CurrentState == State.Idle && _directiveDwell > 0.2f;

			case DirectiveKind.Gesture:
				// PlayGesture() sets state to React with a duration; done when
				// state returns to Idle (i.e. the gesture finished).
				return CurrentState == State.Idle && _directiveDwell > 0.1f;

			case DirectiveKind.Play:
				// Play = like Gesture, but the anim may cut-short mid-flight.
				// Done when EITHER the state returns to Idle (full clip played
				// OR the cut-short fired and the state machine fell back to
				// Idle on the next frame).
				return CurrentState == State.Idle && _directiveDwell > 0.1f;

			case DirectiveKind.Say:
				return true;   // no-op directive

			// ── IK directive completion ─────────────────────────────────────
			// Most IK directives set up persistent state and complete in one
			// frame. Only IkHoldPose waits for a timer.
			case DirectiveKind.IkReach:
			case DirectiveKind.IkPoint:
			case DirectiveKind.IkLook:
			case DirectiveKind.IkLean:
			case DirectiveKind.IkTwist:
			case DirectiveKind.IkStep:
			case DirectiveKind.IkLiftLeg:
			case DirectiveKind.IkGrip:
			case DirectiveKind.IkRelease:
			case DirectiveKind.IkReleaseAll:
			case DirectiveKind.RequestMotion:
				return _directiveDwell > 0.05f;   // one frame is enough
			case DirectiveKind.IkHoldPose:
			{
				float needed = d.Duration > 0.05f ? d.Duration : 2f;
				return _directiveDwell >= needed;
			}
		}
		return true;
	}

	// ── Target resolution ─────────────────────────────────────────────
	// Convert a named target ("user_cursor", "nearest_window", "left_edge" …)
	// into a concrete Vector2 the body can walk/face. Returns null if the
	// target can't be resolved (e.g. nearest_window when there are none).

	private Vector2? ResolveTarget(DirectiveTarget t)
	{
		switch (t)
		{
			case DirectiveTarget.None:
			case DirectiveTarget.Current:
				return FeetScreen;

			case DirectiveTarget.LeftEdge:
				{
					var vp = GetViewport().GetVisibleRect();
					return new Vector2(vp.Size.X * 0.1f, _floorY);
				}
			case DirectiveTarget.RightEdge:
				{
					var vp = GetViewport().GetVisibleRect();
					return new Vector2(vp.Size.X * 0.9f, _floorY);
				}
			case DirectiveTarget.Center:
				{
					var vp = GetViewport().GetVisibleRect();
					return new Vector2(vp.Size.X * 0.5f, _floorY);
				}
			case DirectiveTarget.NearestWindow:
			case DirectiveTarget.HighestWindow:
			{
				if (_windows == null) return null;
				Rect2? best = t == DirectiveTarget.HighestWindow ? HighestWindow() : NearestWindow();
				if (!best.HasValue) return null;
				var r = best.Value;
				// Aim for the centre of the top edge — natural place to approach from.
				return new Vector2(r.Position.X + r.Size.X * 0.5f, _floorY);
			}
			case DirectiveTarget.UserCursor:
				// Main.cs caches the last cursor position on the controller
				// (via SetUserCursor); we read it back here. The Godot window
				// is click-through, so the OS often routes mouse motion
				// events to apps behind Aria instead of to Godot. As a
				// pragmatic fallback, step ~600 px to Aria's RIGHT when we
				// don't have a recorded cursor position yet — that way
				// "come to me" at least moves her somewhere visible instead
				// of trying to walk to her own feet (which would no-op and
				// make the state machine thrash through turn/walk/stop).
				if (_userCursor.HasValue) return _userCursor.Value;
				var vpF = GetViewport().GetVisibleRect();
				float fallbackX = Mathf.Clamp(_feet.X + 600f, vpF.Position.X + 60f, vpF.Position.X + vpF.Size.X - 60f);
				return new Vector2(fallbackX, _floorY);
		}
		return null;
	}

	// Cached cursor position, written by Main from _Input.
	private Vector2? _userCursor;
	public void SetUserCursor(Vector2? pos) => _userCursor = pos;

	// Yaw in radians so the body FACES the named target. Returns CamYaw (≈0)
	// for unresolvable targets; the caller is expected to validate.
	private float YawToFace(DirectiveTarget t)
	{
		var pt = ResolveTarget(t);
		if (!pt.HasValue) return CamYaw;
		float dx = pt.Value.X - FeetScreen.X;
		if (Math.Abs(dx) < 4f) return CamYaw;
		// Body is at CamYaw when facing camera; turning right means +Yaw.
		// dx > 0 → look right → add 90° to CamYaw.
		bool toRight = dx > 0f;
		return CamYaw + (toRight ? Mathf.Pi / 2f : -Mathf.Pi / 2f);
	}

	private Rect2? NearestWindow()
	{
		Rect2? best = null;
		float bestDist = float.MaxValue;
		foreach (var r in _windows.WindowLedges)
		{
			float vx = r.Position.X - _winOffsetX;
			float midX = vx + r.Size.X * 0.5f;
			float dist = Math.Abs(midX - FeetScreen.X);
			if (dist < bestDist) { bestDist = dist; best = new Rect2(new Vector2(vx, r.Position.Y - _winOffsetY), r.Size); }
		}
		return best;
	}

	private Rect2? HighestWindow()
	{
		Rect2? best = null;
		float bestY = float.MaxValue;
		foreach (var r in _windows.WindowLedges)
		{
			float vy = r.Position.Y - _winOffsetY;
			if (vy < bestY) { bestY = vy; best = new Rect2(new Vector2(r.Position.X - _winOffsetX, vy), r.Size); }
		}
		return best;
	}

	// Pick a window to climb: explicit window_id (if valid) > nearest > null.
	private Rect2? PickClimbTarget(int windowId)
	{
		if (windowId < 0 || _windows == null) return NearestWindow();
		int id = 0;
		foreach (var r in _windows.WindowLedges)
		{
			if (id == windowId)
			{
				float vx = r.Position.X - _winOffsetX;
				float vy = r.Position.Y - _winOffsetY;
				return new Rect2(new Vector2(vx, vy), r.Size);
			}
			id++;
		}
		return NearestWindow();
	}

	private float NearestEdgeX(Rect2 r)
	{
		float left = r.Position.X - 12f;
		float right = r.Position.X + r.Size.X + 12f;
		return Math.Abs(_feet.X - left) <= Math.Abs(_feet.X - right) ? left : right;
	}

	// Stash for the Turn state's WalkTo target Y (otherwise the walk step
	// loses the LLM-provided Y when control hands back).
	private float _queuedTurnYaw;
	private float _queuedWalkTargetY;

	// Re-stamp the walk target after a turn completes so ProcessWalk knows
	// where to go. The state machine's normal EnterTurn path only stashes X.
	// Overrides after a turn if a directive set Y.
	private void RestoreWalkTargetAfterTurn()
	{
		if (_afterTurn == State.Walk && !float.IsNaN(_queuedWalkTargetY))
			_walkTargetY = _queuedWalkTargetY;
	}

	private static string PickRandom(string[] arr)
	{
		if (arr == null || arr.Length == 0) return "";
		return arr[(int)(GD.Randi() % (uint)arr.Length)];
	}

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

		// Also measure head height for THIS model so the speech bubble clears the top
		// of her head instead of relying on the hardcoded HeadHeightPx guess.
		int headBone = FindHeadBone();
		if (headBone >= 0)
		{
			float headY = (skelTf * _skeleton.GetBoneGlobalPose(headBone)).Origin.Y;
			float headAboveFeetUnits = Math.Abs(headY - footY);
			float pxPerUnit = GetViewport().GetVisibleRect().Size.Y / 8f;  // CamSize = 8
			// Head bone sits at the skull base; pad ~18% for the crown + a little air.
			HeadHeightPx = headAboveFeetUnits * pxPerUnit * 1.18f + 28f;
			GD.Print($"[Aria] Head calibration: {headAboveFeetUnits:F3}u above feet -> HeadHeightPx={HeadHeightPx:F0}");
		}
	}

	// Animations to per-frame calibrate. The T-pose calibration is the
	// reference; for each of these we measure the foot Y at the anim's
	// mid-pose and compute the lift needed so the visual feet still land
	// on the floor line.
	private static readonly string[] AnimsToCalibrate = new[]
	{
		"sit", "sit_clap", "climb", "fall", "walk", "run", "jump", "yawn",
	};

	// Reference T-pose foot and hip Y (above the pivot). Filled at first
	// calibration; used as the "neutral" for the per-anim delta math.
	private float _tposeFootY = 0.094f;    // matches the historical T-pose foot height
	private float _tposeHipY  = 0.940f;    // hips sit ~0.94u above the pivot in T-pose

	/// Per-animation foot delta (world Y added to model pivot so visual feet
	/// land on the floor). Filled by CalibrateAllAnimFeet(), which measures
	/// the actual foot Y for each anim at its mid-pose. Also fills
	/// HipDeltaPerAnim for anims where the HIPS should land at the world-Y
	/// (sit, sit_clap) — this is the "feet dangle below the perch" case.
	private void CalibrateAllAnimFeet()
	{
		if (_anim == null || _skeleton == null) return;
		string lib = _anim.GetAnimationLibraryList().Count > 0
			? _anim.GetAnimationLibraryList()[0].ToString() : "";
		var libObj = _anim.GetAnimationLibrary(lib);
		if (libObj == null) return;
		var cachedAnim = _curAnimName;
		var cachedPos = _anim.CurrentAnimationPosition;
		// Set the pivot to a known reference: world Y = 0.
		Position = new Vector3(Position.X, 0f, Position.Z);
		_footPivotOffset = 0f;  // we'll compute per-anim

		// First, measure T-pose reference values for foot and hip. We
		// temporarily seek the "idle" anim at t=0 (closest to T-pose) to get
		// the "neutral" hip/foot Y. If idle is missing, fall back to the
		// hardcoded constants above.
		float tposeFootRef = _tposeFootY;
		float tposeHipRef  = _tposeHipY;
		if (libObj.HasAnimation("idle"))
		{
			var idleAnim = libObj.GetAnimation("idle");
			_anim.Play("idle", customBlend: -1.0f, customSpeed: 0.0f, fromEnd: false);
			_anim.Seek(0.0, true);
			_anim.Advance(0.0);
			_skeleton.GlobalTransform = _skeleton.GlobalTransform;
			var skelTf = _skeleton.GlobalTransform;
			float fyL = SampleBoneWorldY(_footBoneL, skelTf);
			float fyR = SampleBoneWorldY(_footBoneR, skelTf);
			tposeFootRef = Math.Min(fyL, fyR);
			float hy = SampleBoneWorldY(_hipBone, skelTf);
			if (hy != float.MaxValue) tposeHipRef = hy;
			_tposeFootY = tposeFootRef;
			_tposeHipY = tposeHipRef;
		}

		GD.Print($"[Aria] Per-anim foot+hip calibration (T-pose foot={tposeFootRef:F3}, hip={tposeHipRef:F3}):");
		foreach (var name in AnimsToCalibrate)
		{
			if (!libObj.HasAnimation(name)) continue;
			var anim = libObj.GetAnimation(name);
			float mid = (float)anim.Length * 0.5f;
			_anim.Play(name, customBlend: -1.0f, customSpeed: 0.0f, fromEnd: false);
			_anim.Seek(mid, true);
			_anim.Advance(0.0);
			// Force the skeleton to apply the seeked pose.
			_skeleton.GlobalTransform = _skeleton.GlobalTransform;
			var skelTf = _skeleton.GlobalTransform;
			float fyL = SampleBoneWorldY(_footBoneL, skelTf);
			float fyR = SampleBoneWorldY(_footBoneR, skelTf);
			float fy = Math.Min(fyL, fyR);
			// T-pose reference for feet is tposeFootRef; the anim's foot
			// is at fy. We want the anim's foot to be at tposeFootRef ABOVE
			// the pivot. So raise the model by (tposeFootRef - fy):
			float footDelta = tposeFootRef - fy;
			FootDeltaPerAnim[name] = footDelta;

			// Hip delta: same idea but with the hip bone. For sit/sit_clap
			// we use the hip to position the model (feet dangle).
			float hipY = SampleBoneWorldY(_hipBone, skelTf);
			float hipDelta = (hipY == float.MaxValue) ? 0f : (tposeHipRef - hipY);
			HipDeltaPerAnim[name] = hipDelta;

			// Perch foot dangle: distance from the model pivot to the feet
			// in this anim's mid-pose. During calibration, Position.Y = 0
			// (set at line 2035), so the foot's world-Y IS the pivot-to-foot
			// distance. Used by ApplyScreenPosition when the character is
			// perched (IsPerched) to position the pivot so the feet land
			// AT the world-Y (the ledge), with the rest of the body above
			// the ledge and the feet naturally dangling by fy units.
			PerchFootDanglePerAnim[name] = fy;

			GD.Print($"  [{name}] mid={mid:F2}s  footY={fy:F3}  animDelta={footDelta:+0.000;-0.000}  hipY={hipY:F3}  hipDelta={hipDelta:+0.000;-0.000}  perchDangle={fy:F3}");
		}
		// Restore the original animation.
		if (!string.IsNullOrEmpty(cachedAnim))
		{
			_anim.Play(cachedAnim, customBlend: -1.0f, customSpeed: 1.0f);
			_anim.Seek(cachedPos, true);
		}
		_footPivotOffset = 0.094f;  // T-pose reference
	}

	// Helper for the per-anim calibration: world Y of a given bone, or +MaxValue
	// if the bone is missing. Uses the instance skeleton directly.
	private float SampleBoneWorldY(int boneIdx, Transform3D skelTf)
	{
		if (boneIdx < 0) return float.MaxValue;
		var pose = _skeleton.GetBoneGlobalPose(boneIdx);
		return (skelTf * pose).Origin.Y;
	}

	private int FindHeadBone()
	{
		if (_skeleton == null) return -1;
		foreach (var n in new[] { "J_Bip_C_Head", "Head", "head" })
		{
			int b = _skeleton.FindBone(n);
			if (b >= 0) return b;
		}
		for (int i = 0; i < _skeleton.GetBoneCount(); i++)
			if (_skeleton.GetBoneName(i).ToString().ToLower().Contains("head")) return i;
		return -1;
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
