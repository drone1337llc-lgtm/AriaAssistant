using Godot;
using System;
using System.Collections.Generic;
using System.Text;
using Aria;

namespace Aria
{
    /// <summary>
    /// Debug scene for the procedural-IK + motion-diffusion stack.
    ///
    /// What it does:
    ///   • Loads Ariaversion4.glb in a regular (non-transparent) window
    ///   • Renders a HUD with: active IK chains, recent directives, queue
    ///     status, FPS, and per-bone solver diagnostics
    ///   • Lets you point-and-click anywhere in 3D to issue an ik_reach
    ///     (left mouse = right arm, shift+left = left arm, right = head)
    ///   • Keyboard shortcuts for testing: W = wave, L = look at cursor,
    ///     R = reach, K = ik_release_all, T = request_motion (text), etc.
    ///   • Visualises the active IK chain's joint positions in world space
    ///     (small cyan spheres at each joint, yellow line to target)
    ///
    /// This is a developer tool, not user-facing. Run it from the editor
    /// with F6 (or set as main scene in project.godot briefly).
    /// </summary>
    public partial class IKDebugScene : Node3D
    {
        [Export] public string AriaModelPath = "res://Ariaversion4.glb";
        [Export] public int HudFontSize = 14;
        [Export] public bool VisualizeJoints = true;
        [Export] public bool VisualizeTargets = true;
        [Export] public float JointMarkerRadius = 0.02f;

        private Node3D _ariaRoot;
        private Skeleton3D _skeleton;
        private AriaIKController _ik;
        private AriaIKControllerDriver _driver;   // the simulator drives the IK directly (no LLM)
        private Camera3D _camera;
        private DirectionalLight3D _light;
        private Label _hud;
        private Label _hudHelp;
        private MeshInstance3D _targetMarker;
        private readonly List<MeshInstance3D> _jointMarkers = new();
        private readonly List<ImmediateMesh> _jointLines = new();

        private Vector3? _lastClickTarget;
        private string _lastChain = "right_arm";
        private string _lastDirective = "(none)";
        private float _fps = 60f;
        private int _frame = 0;
        private RandomNumberGenerator _rng = new();
        private StringBuilder _sb = new();

        public override void _Ready()
        {
            _rng.Randomize();
            // 1) Environment — fully lit, no transparency (regular Godot window)
            var env = new WorldEnvironment { Name = "WorldEnvironment" };
            env.Environment = new Godot.Environment
            {
                BackgroundMode = Godot.Environment.BGMode.Color,
                BackgroundColor = new Color(0.08f, 0.09f, 0.12f, 1.0f),
                AmbientLightSource = Godot.Environment.AmbientSource.Color,
                AmbientLightColor = new Color(0.4f, 0.4f, 0.45f, 1.0f),
                AmbientLightEnergy = 0.6f,
            };
            AddChild(env);

            // 2) Camera — orbit-style, positioned to see the whole rig
            _camera = new Camera3D
            {
                Name = "DebugCamera",
                Position = new Vector3(0, 1.5f, 4.0f),
                Current = true,
                Fov = 50,
            };
            _camera.LookAt(Vector3.Zero, Vector3.Up);
            AddChild(_camera);

            // 3) Light
            _light = new DirectionalLight3D
            {
                Name = "DebugLight",
                LightEnergy = 1.0f,
            };
            _light.Rotation = new Vector3(-0.5f, 0.7f, 0);
            AddChild(_light);

            // 4) Load Aria model
            var scene = ResourceLoader.Load<PackedScene>(AriaModelPath);
            if (scene == null)
            {
                GD.PrintErr($"[IKDebug] Failed to load {AriaModelPath}");
                return;
            }
            _ariaRoot = scene.Instantiate<Node3D>();
            _ariaRoot.Name = "Aria";
            AddChild(_ariaRoot);
            _skeleton = FindSkeletonUnder(_ariaRoot);
            if (_skeleton == null)
            {
                GD.PrintErr("[IKDebug] No Skeleton3D under Aria root!");
                return;
            }
            GD.Print($"[IKDebug] Skeleton has {_skeleton.GetBoneCount()} bones");

            // 5) Spin up a custom IK driver (no LLM needed for dev)
            _ik = new AriaIKController { Name = "DebugIK" };
            AddChild(_ik);
            _ik.Setup(_skeleton, _ariaRoot);
            _driver = new AriaIKControllerDriver();
            AddChild(_driver);
            _driver.AttachTo(_ik, _skeleton, _ariaRoot);

            // 6) Target marker — small red sphere at the current IK target
            var sphere = new SphereMesh { Radius = 0.05f, Height = 0.1f };
            _targetMarker = new MeshInstance3D { Name = "TargetMarker", Mesh = sphere };
            var mat = new StandardMaterial3D
            {
                AlbedoColor = new Color(1.0f, 0.4f, 0.2f, 1.0f),
                Emission = new Color(0.8f, 0.2f, 0.0f),
                EmissionEnabled = true,
                EmissionEnergyMultiplier = 2.0f,
                ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
                NoDepthTest = true,
            };
            _targetMarker.MaterialOverride = mat;
            _targetMarker.Visible = false;
            AddChild(_targetMarker);

            // 7) Joint markers (one per active chain, refreshed each frame)
            for (int i = 0; i < 8; i++)
            {
                var m = new MeshInstance3D { Mesh = sphere, Visible = false };
                m.MaterialOverride = new StandardMaterial3D
                {
                    AlbedoColor = new Color(0.2f, 0.8f, 1.0f, 1.0f),
                    ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded,
                    NoDepthTest = true,
                };
                AddChild(m);
                _jointMarkers.Add(m);
            }

            // 8) HUD — top-left for state, bottom-left for help
            _hud = new Label
            {
                Name = "HUD",
                Position = new Vector2(12, 12),
                LabelSettings = new LabelSettings
                {
                    FontSize = HudFontSize,
                    FontColor = new Color(0.9f, 0.9f, 0.95f, 1.0f),
                    OutlineSize = 2,
                    OutlineColor = new Color(0, 0, 0, 1),
                },
            };
            AddChild(_hud);

            _hudHelp = new Label
            {
                Name = "Help",
                Position = new Vector2(12, 0),
                AnchorLeft = 0,
                AnchorTop = 1,
                AnchorRight = 0,
                AnchorBottom = 1,
                OffsetTop = -110,
                LabelSettings = new LabelSettings
                {
                    FontSize = HudFontSize - 2,
                    FontColor = new Color(0.7f, 0.8f, 0.7f, 1.0f),
                    OutlineSize = 1,
                    OutlineColor = new Color(0, 0, 0, 1),
                },
                Text = "LMB = reach right arm to cursor · Shift+LMB = left arm · RMB = look · R = random reach · L = look_at cursor · " +
                       "T = lean forward · Y = twist · G = grip close · H = grip open · K = release all · F = fire random walk · " +
                       "Q/E = camera orbit · W/S = zoom · P = pick random animation · M = request_motion (1) · ESC = quit"
            };
            AddChild(_hudHelp);
        }

        public override void _Process(double delta)
        {
            _fps = _fps * 0.95f + (1.0f / (float)delta) * 0.05f;
            _frame++;
            // Drive the IK on a separate node so the controller can run
            // even when not in Main.cs
            _driver.Tick(delta);
            // Update visualization
            UpdateVisualization();
            // Update HUD
            UpdateHud();
        }

        public override void _Input(InputEvent e)
        {
            if (e is InputEventMouseButton mb && mb.Pressed)
            {
                HandleMouseClick(mb);
            }
            else if (e is InputEventKey key && key.Pressed && !key.Echo)
            {
                HandleKey(key);
            }
            else if (e is InputEventMouseMotion mm && _camera != null)
            {
                // Orbit camera with right-button drag (when not clicking IK)
                // — handled via simple keys Q/E below for predictability
            }
        }

        private void HandleMouseClick(InputEventMouseButton mb)
        {
            // Convert screen click to a 3D world point at a fixed distance
            // from the camera (ray-plane intersection at y=0.5)
            var from = _camera.ProjectRayOrigin(mb.Position);
            var dir = _camera.ProjectRayNormal(mb.Position);
            float t = (1.5f - from.Y) / dir.Y;   // y=1.5 plane
            if (t < 0) return;
            var worldPoint = from + dir * t;

            if (mb.ButtonIndex == MouseButton.Left && !mb.ShiftPressed)
            {
                IssueReach("right_arm", worldPoint);
            }
            else if (mb.ButtonIndex == MouseButton.Left && mb.ShiftPressed)
            {
                IssueReach("left_arm", worldPoint);
            }
            else if (mb.ButtonIndex == MouseButton.Right)
            {
                IssueLook(worldPoint);
            }
        }

        private void HandleKey(InputEventKey key)
        {
            var k = key.Keycode;
            if (k == Key.Escape) GetTree().Quit();
            else if (k == Key.K) { _ik?.ReleaseAll(); _lastDirective = "ik_release_all"; }
            else if (k == Key.R)
            {
                var rnd = new Vector3((float)_rng.RandfRange(-1.5f, 1.5f), 1.5f, (float)_rng.RandfRange(0.2f, 1.5f));
                IssueReach("right_arm", rnd);
            }
            else if (k == Key.L)
            {
                IssueLook(_ariaRoot.GlobalPosition + new Vector3((float)_rng.RandfRange(-1.5f, 1.5f), 1.0f, 0.5f));
            }
            else if (k == Key.T)
            {
                // Lean forward 0.5
                var d = new AriaDirective
                {
                    Kind = DirectiveKind.IkLean,
                    Direction = "forward",
                    Amount = 0.6f,
                };
                _driver.ApplyDirective(d);
                _lastDirective = "ik_lean forward amt=0.6";
            }
            else if (k == Key.Y)
            {
                var d = new AriaDirective { Kind = DirectiveKind.IkTwist, YawDeg = 30, PitchDeg = -5 };
                _driver.ApplyDirective(d);
                _lastDirective = "ik_twist yaw=30 pitch=-5";
            }
            else if (k == Key.G)
            {
                var d = new AriaDirective { Kind = DirectiveKind.IkGrip, Hand = "right", Name = "closed", Amount = 1f };
                _driver.ApplyDirective(d);
                _lastDirective = "ik_grip right closed";
            }
            else if (k == Key.H)
            {
                var d = new AriaDirective { Kind = DirectiveKind.IkGrip, Hand = "right", Name = "open", Amount = 1f };
                _driver.ApplyDirective(d);
                _lastDirective = "ik_grip right open";
            }
            else if (k == Key.M)
            {
                // Submit a fake request_motion (will only work if a motion
                // server is reachable; otherwise the client logs MotionFailed)
                var d = new AriaDirective
                {
                    Kind = DirectiveKind.RequestMotion,
                    Prompt = "Aria waves from the hip with a big smile",
                    Frames = 60,
                    Name = "wave_hip",
                };
                _driver.ApplyDirective(d);
                _lastDirective = "request_motion wave_hip";
            }
            else if (k == Key.F)
            {
                // Random walk to test motion
                var d = new AriaDirective
                {
                    Kind = DirectiveKind.WalkTo,
                    X = (float)_rng.RandfRange(-2.5f, 2.5f),
                    Y = 0,
                };
                _driver.ApplyDirective(d);
                _lastDirective = "walk_to random";
            }
            else if (k == Key.P)
            {
                // Pick a random animation from the library and play it
                var player = _skeleton.GetParent()?.GetNodeOrNull<AnimationPlayer>("AnimationPlayer");
                if (player != null)
                {
                    var libs = player.GetAnimationLibraryList();
                    if (libs.Count > 0)
                    {
                        var lib = player.GetAnimationLibrary(libs[0]);
                        var names = lib.GetAnimationList();
                        if (names.Count > 0)
                        {
                            var name = names[(int)(_rng.Randi() % (uint)names.Count)];
                            _lastDirective = $"play_anim '{name}'";
                            player.Play(name);
                        }
                    }
                }
            }
            else if (k == Key.Q) _camera.RotateY(0.1f);
            else if (k == Key.E) _camera.RotateY(-0.1f);
            else if (k == Key.W) _camera.Position = _camera.Position + _camera.Transform.Basis.Z * -0.2f;
            else if (k == Key.S) _camera.Position = _camera.Position + _camera.Transform.Basis.Z * 0.2f;
        }

        private void IssueReach(string chain, Vector3 world)
        {
            _lastChain = chain;
            _lastClickTarget = world;
            _targetMarker.GlobalPosition = world;
            _targetMarker.Visible = VisualizeTargets;
            var d = new AriaDirective
            {
                Kind = DirectiveKind.IkReach,
                Name = chain,
                X = world.X,
                Y = world.Y,
                Z = world.Z,
            };
            _driver.ApplyDirective(d);
            _lastDirective = $"ik_reach {chain} ({world.X:F2},{world.Y:F2},{world.Z:F2})";
        }

        private void IssueLook(Vector3 world)
        {
            _lastClickTarget = world;
            _targetMarker.GlobalPosition = world;
            _targetMarker.Visible = VisualizeTargets;
            var d = new AriaDirective
            {
                Kind = DirectiveKind.IkLook,
                X = world.X,
                Y = world.Y,
                Z = world.Z,
            };
            _driver.ApplyDirective(d);
            _lastDirective = $"ik_look ({world.X:F2},{world.Y:F2},{world.Z:F2})";
        }

        // ── Visualization ───────────────────────────────────────────────
        private void UpdateVisualization()
        {
            if (!VisualizeJoints || _ik == null) return;
            int idx = 0;
            foreach (var (name, ac) in _ik.Active)
            {
                if (idx >= _jointMarkers.Count) break;
                _jointMarkers[idx].Visible = true;
                _jointMarkers[idx].GlobalPosition = new Vector3(ac.Target.X, ac.Target.Y, ac.Target.Z);
                idx++;
            }
            for (; idx < _jointMarkers.Count; idx++) _jointMarkers[idx].Visible = false;
        }

        // ── HUD ─────────────────────────────────────────────────────────
        private void UpdateHud()
        {
            _sb.Clear();
            _sb.AppendLine($"=== Aria IK Debug — FPS {_fps:F1} ===");
            _sb.AppendLine("");
            _sb.AppendLine($"Skeleton: {_skeleton?.GetBoneCount() ?? 0} bones, Aria root: {_ariaRoot?.Name}");
            _sb.AppendLine("");
            _sb.AppendLine("Active IK chains:");
            if (_ik != null)
            {
                foreach (var (name, ac) in _ik.Active)
                {
                    _sb.AppendLine($"  • {name,-12} target=({ac.Target.X:F2},{ac.Target.Y:F2},{ac.Target.Z:F2}) " +
                                   $"mode={ac.Mode} weight={ac.Weight:F2}");
                }
                if (_ik.Active.Count == 0) _sb.AppendLine("  (none)");
            }
            _sb.AppendLine("");
            _sb.AppendLine($"Last directive: {_lastDirective}");
            if (_lastClickTarget.HasValue)
                _sb.AppendLine($"Last target:    ({_lastClickTarget.Value.X:F2},{_lastClickTarget.Value.Y:F2},{_lastClickTarget.Value.Z:F2})");
            _sb.AppendLine("");
            _sb.AppendLine("Frame: " + _frame);
            _hud.Text = _sb.ToString();
        }

        // ── Helpers ─────────────────────────────────────────────────────
        private static Skeleton3D FindSkeletonUnder(Node root)
        {
            if (root is Skeleton3D sk) return sk;
            foreach (var c in root.GetChildren())
            {
                var found = FindSkeletonUnder(c);
                if (found != null) return found;
            }
            return null;
        }
    }

    /// <summary>
    /// Applies AriaDirective objects to a live AriaIKController. Mirrors
    /// what CharacterController.StartDirective does for IK kinds, but
    /// without the body-level state machine. Lets the debug scene test
    /// IK in isolation.
    /// </summary>
    public partial class AriaIKControllerDriver : Node
    {
        private AriaIKController _ik;
        private Skeleton3D _skel;
        private Node3D _root;

        public void AttachTo(AriaIKController ik, Skeleton3D skel, Node3D root)
        {
            _ik = ik;
            _skel = skel;
            _root = root;
        }

        public void ApplyDirective(AriaDirective d)
        {
            if (d == null || _ik == null) return;
            switch (d.Kind)
            {
                case DirectiveKind.IkReach:
                case DirectiveKind.IkPoint:
                {
                    var target = new Vector3(d.X, d.Y, d.Z);
                    _ik.SolveAndApply(d.Name, target, null, AriaIKController.BlendMode.Additive, 1f, -1f);
                    break;
                }
                case DirectiveKind.IkLook:
                {
                    var target = new Vector3(d.X, d.Y, d.Z);
                    _ik.SolveAndApply("head", target, null, AriaIKController.BlendMode.Override, 1f, -1f);
                    break;
                }
                case DirectiveKind.IkLean:
                {
                    if (_skel == null) break;
                    var head = _skel.GetBoneGlobalPose(_skel.FindBone("J_Bip_C_Head")).Origin;
                    var hips = _skel.GetBoneGlobalPose(_skel.FindBone("J_Bip_C_Hips")).Origin;
                    float amt = Mathf.Clamp(d.Amount > 0.01f ? d.Amount : 0.4f, 0f, 1f);
                    var lean = new Vector3(0, 0, 0);
                    switch ((d.Direction ?? "forward").ToLowerInvariant())
                    {
                        case "back": lean.Z = 0.4f * amt; break;
                        case "left": lean.X = -0.4f * amt; break;
                        case "right": lean.X = 0.4f * amt; break;
                        default: lean.Z = -0.6f * amt; break;
                    }
                    _ik.SolveAndApply("spine", head + lean, null, AriaIKController.BlendMode.Additive, amt, -1f);
                    break;
                }
                case DirectiveKind.IkTwist:
                {
                    if (_skel == null) break;
                    var head = _skel.GetBoneGlobalPose(_skel.FindBone("J_Bip_C_Head")).Origin;
                    var hips = _skel.GetBoneGlobalPose(_skel.FindBone("J_Bip_C_Hips")).Origin;
                    float yaw = float.IsNaN(d.YawDeg) ? 0 : Mathf.DegToRad(d.YawDeg);
                    var toHead = head - hips;
                    var rotated = new Vector3(
                        (float)(toHead.X * Math.Cos(yaw) - toHead.Z * Math.Sin(yaw)),
                        toHead.Y,
                        (float)(toHead.X * Math.Sin(yaw) + toHead.Z * Math.Cos(yaw)));
                    _ik.SolveAndApply("spine", hips + rotated, null, AriaIKController.BlendMode.Additive, 1f, -1f);
                    break;
                }
                case DirectiveKind.IkGrip:
                {
                    // Per-finger curl — same code as CharacterController.ApplyFingerCurl
                    string side = (d.Hand ?? "left").ToLowerInvariant();
                    string prefix = side == "right" ? "R" : "L";
                    float close = Mathf.Clamp(d.Amount, 0f, 1f);
                    if (close < 0.01f) close = 1f;
                    switch ((d.Name ?? "closed").ToLowerInvariant())
                    {
                        case "point":
                            ApplyFingerCurl(prefix, "Index", 0.05f);
                            ApplyFingerCurl(prefix, "Middle", 0.9f * close);
                            ApplyFingerCurl(prefix, "Ring", 0.9f * close);
                            ApplyFingerCurl(prefix, "Little", 0.9f * close);
                            ApplyFingerCurl(prefix, "Thumb", 0.5f * close);
                            break;
                        case "peace":
                            ApplyFingerCurl(prefix, "Index", 0.05f);
                            ApplyFingerCurl(prefix, "Middle", 0.05f);
                            ApplyFingerCurl(prefix, "Ring", 0.9f * close);
                            ApplyFingerCurl(prefix, "Little", 0.9f * close);
                            ApplyFingerCurl(prefix, "Thumb", 0.5f * close);
                            break;
                        case "open":
                        default:
                            ApplyFingerCurl(prefix, "Index", 0.05f);
                            ApplyFingerCurl(prefix, "Middle", 0.05f);
                            ApplyFingerCurl(prefix, "Ring", 0.05f);
                            ApplyFingerCurl(prefix, "Little", 0.05f);
                            ApplyFingerCurl(prefix, "Thumb", 0.1f);
                            break;
                        case "closed": case "fist":
                            ApplyFingerCurl(prefix, "Index", 0.9f * close);
                            ApplyFingerCurl(prefix, "Middle", 0.9f * close);
                            ApplyFingerCurl(prefix, "Ring", 0.9f * close);
                            ApplyFingerCurl(prefix, "Little", 0.9f * close);
                            ApplyFingerCurl(prefix, "Thumb", 0.7f * close);
                            break;
                    }
                    break;
                }
                case DirectiveKind.IkRelease:
                    _ik.Release(d.Name);
                    break;
                case DirectiveKind.IkReleaseAll:
                    _ik.ReleaseAll();
                    break;
                case DirectiveKind.WalkTo:
                {
                    // No state machine in the debug scene — just translate the
                    // aria root as a visual stand-in
                    if (_root != null)
                    {
                        _root.GlobalPosition = new Vector3(d.X, _root.GlobalPosition.Y, d.Y);
                    }
                    break;
                }
                case DirectiveKind.RequestMotion:
                {
                    // The debug scene has no AriaMotionClient. If the user
                    // wants to test the request_motion path, they should use
                    // Main.tscn. We just print here.
                    GD.Print($"[Debug] request_motion would POST: prompt='{d.Prompt}' frames={d.Frames} name={d.Name}");
                    break;
                }
                // Other kinds (Idle, TurnTo, WalkToward, Climb, …) require the
                // state machine — print a hint and ignore in the debug scene.
                default:
                    GD.Print($"[Debug] directive '{d.Kind}' needs the main scene's state machine — ignored here");
                    break;
            }
        }

        // Per-finger curl (mirror of CharacterController.ApplyFingerCurl)
        private void ApplyFingerCurl(string sidePrefix, string finger, float curl)
        {
            if (_skel == null) return;
            string prox = $"J_Bip_{sidePrefix}_{finger}1";
            int idx = _skel.FindBone(prox);
            if (idx < 0) return;
            string chainName = $"{finger.ToLowerInvariant()}_{(sidePrefix == "R" ? "r" : "l")}";
            var proxPos = _skel.GetBoneGlobalPose(idx).Origin;
            var palmTarget = proxPos + new Vector3(0.04f, -0.08f, 0.0f) * curl;
            _ik.SolveAndApply(chainName, palmTarget, null, AriaIKController.BlendMode.Override, 1f, -1f);
        }

        // The IK controller does its work in _Process; in the debug scene
        // the controller itself is in the tree, so it ticks automatically.
        // We don't need to do anything per-frame here, but expose Tick for
        // potential future use (e.g. stepping frame-by-frame).
        public void Tick(double delta) { }
    }
}
