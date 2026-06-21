using Godot;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Aria
{
    /// <summary>
    /// Mirrors the server-side motion_library.json into a faithful in-memory
    /// dictionary (AnimSources) that Aria's controllers / IK layer can read
    /// from without doing their own JSON parsing.
    ///
    /// The mirror is a singleton — <see cref="Instance"/> is set once from
    /// Main._Ready() and used as the read-only source of truth for the rest
    /// of the session. It is intentionally NOT a Godot Node on its own:
    /// keeping it as a plain C# object means callers can hit AnimSources
    /// from any thread (e.g. an LLM HTTP continuation) without worrying
    /// about Godot's main-thread marshal rules. Mutations are done on
    /// replace-whole-dict (atomic swap) so a reader iterating the dict
    /// never sees a torn write.
    ///
    /// The polling loop is a Godot Timer driven by Main, which calls
    /// <see cref="PollForUpdate"/> every 5 minutes. We use BOTH mtime
    /// AND a content sha256 to detect a change: mtime is cheap, the hash
    /// is the truth (some editors rewrite the file with the same mtime
    /// when only the contents changed; some "save" operations just touch
    /// mtime without rewriting).
    /// </summary>
    public partial class MotionLibraryMirror : Node
    {
        // ── Public API ────────────────────────────────────────────────────────

        /// <summary>Singleton. Set by Main._Ready() and treated as immutable for the session.</summary>
        public static MotionLibraryMirror Instance { get; private set; }

        /// <summary>
        /// Fires after a successful reload that produced a different AnimSources
        /// than the previous one (mtime/sha256 changed AND content decoded).
        /// The handler receives the new count + the new short sha256[:8] for logging.
        /// </summary>
        public event Action<int, string> LibraryUpdated;

        /// <summary>
        /// Fires after a successful reload that ADDED one or more animations
        /// relative to the previous snapshot. The handler receives the new
        /// entries (keyed by controller short name) so the Godot side can
        /// hot-swap the FBX/GLB into the AnimPlayer's animation library
        /// without waiting for the next 5-minute poll.
        ///
        /// This is what the auto-curator wires up: when the Python server's
        /// ingest_motion_library.py writes a new .fbx/.glb to aria/ani/incoming/
        /// and re-emits motion_library.json with a new entry, this event
        /// fires here on the next poll (or ReloadNow()).
        /// </summary>
        public event Action<IReadOnlyDictionary<string, AnimSpec>> LibraryAnimationsAdded;

        /// <summary>
        /// The current snapshot. Safe to iterate from any thread; the mirror
        /// atomically swaps the reference on reload. Use the property, not a
        /// captured local, if you need to see post-update data.
        /// </summary>
        public IReadOnlyDictionary<string, AnimSpec> AnimSources => _animSources;

        /// <summary>The file we last successfully loaded. Empty if we never loaded.</summary>
        public string CurrentPath => _currentPath;

        /// <summary>SHA-256 (hex) of the last successful load, or empty if never loaded.</summary>
        public string CurrentHash => _currentHash;

        /// <summary>Wall-clock UTC time of the last successful load, or DateTime.MinValue.</summary>
        public DateTime LastLoadedUtc { get; private set; } = DateTime.MinValue;

        /// <summary>Number of anims in the last successful load.</summary>
        public int LastCount { get; private set; }

        // ── Configuration ─────────────────────────────────────────────────────

        /// <summary>Where the JSON lives. <c>res://</c> / <c>user://</c> are OK
        /// (ProjectSettings.GlobalizePath resolves them). Empty → use the
        /// default next to the project root, which the Main.tscn exporter sets.</summary>
        [Export] public string MotionLibraryPath { get; set; } = "";

        [Export] public float PollIntervalSec { get; set; } = 300f;   // 5 minutes

        // ── Internal state ────────────────────────────────────────────────────

        // Atomic-swap dictionary: rebuild a fresh one on reload, then assign.
        // Readers always get a consistent snapshot.
        private volatile Dictionary<string, AnimSpec> _animSources = new();
        private string _currentPath = "";
        private string _currentHash = "";
        private DateTime _lastMtimeUtc = DateTime.MinValue;
        private Timer _pollTimer;
        private bool _attached;

        // Stable alias map: server emits snake_case names ("standing_greeting",
        // "wave_hip_hop_dance", "sitting", "sitting_clap", "climbing", …) but
        // the LLM directive vocabulary + the AnimationBuilder / Main.tscn
        // AnimSources use the short controller names ("wave", "react", "sit",
        // "sit_clap", "climb", …). We canonicalise to the controller name on
        // load so callers can index by a single name space.
        //
        // The keys here are SERVER names; the values are the controller names
        // that server entry will populate. A server entry can populate
        // MULTIPLE controller names (e.g. `standing_greeting` populates both
        // `wave` and `react`, because the same Standing Greeting.fbx backs
        // both controller names in the baked AnimSources). Conversely, a
        // controller name is populated by AT MOST ONE server entry — if the
        // JSON ever ships two server entries that both try to claim the same
        // controller name, the FIRST one (by JSON order) wins and the second
        // is logged as a conflict.
        //
        // Server names NOT in this table (e.g. `swimming`, `bashful`, …) are
        // still reflected: their controller name is their own server name, so
        // they're addressable as `PlayAnim("swimming")` etc. The LLM can
        // discover them through the AnimSources dict.
        //
        // The table is intentionally 1:1 OR 1:FEW per server name. NEVER
        // many:1 (multiple server names → same controller name). The
        // previous version of this table had a many:1 row
        //   { "wave": ["standing_greeting", "wave_hip_hop_dance", "wave"] }
        // which under a first-wins reverse map silently dropped
        // `wave_hip_hop_dance` from its dedicated `wave_hip` slot. The
        // verifier flagged that as a claim-vs-code discrepancy. This version
        // is faithful: every server entry in the JSON produces a populated
        // controller slot.
        private static readonly Dictionary<string, string[]> AliasToController = new(StringComparer.OrdinalIgnoreCase)
        {
            // `standing_greeting.fbx` is the source of BOTH the `wave` gesture
            // AND the `react` gesture in the existing AnimBuilder AnimSources
            // (see aria/scenes/Main.tscn: both keys point at Standing Greeting.fbx).
            // One server entry → two controller names.
            { "standing_greeting",       new[] { "wave", "react" } },

            // Each remaining server name maps to its own controller name.
            // No collisions: every controller name in the right column is
            // unique. If the JSON's server names drift in the future (e.g.
            // `walk_step` is added), adding a new 1:1 row here is the
            // supported extension.
            { "wave_hip_hop_dance",      new[] { "wave_hip" } },
            { "sitting",                 new[] { "sit" } },
            { "sitting_clap",            new[] { "sit_clap" } },
            { "climbing",                new[] { "climb" } },
            { "walking",                 new[] { "walk" } },
            { "female_start_walking",    new[] { "walk_start" } },
            { "female_stop_walking",     new[] { "walk_stop" } },
            { "running",                 new[] { "run" } },
            { "jump_down",               new[] { "fall" } },
            { "idle_1",                  new[] { "idle2" } },
            { "look_around",             new[] { "look" } },
            { "left_turn",               new[] { "turn_left" } },
            { "right_turn",              new[] { "turn_right" } },
            { "change_direction",        new[] { "change_dir" } },

            // Identity mappings (server name == controller name). Listed
            // explicitly so the alias table is the single source of truth
            // for "what controller names exist". Server names that AREN'T
            // listed here (swimming, bashful, climbing_down, …) still
            // appear in the dict under their own server name.
            { "idle",                    new[] { "idle" } },
            { "jump",                    new[] { "jump" } },
            { "yawn",                    new[] { "yawn" } },
            { "thankful",                new[] { "thankful" } },
        };

        // Reverse index: controller name → first server name that claims it.
        // Used only as a "first-claim wins" guardrail when the JSON ships
        // two server entries that both try to populate the same controller
        // slot (e.g. a future server entry literally named `wave` AND
        // `standing_greeting` both in the file). The first JSON occurrence
        // wins, and the second is logged as a conflict for debugging.
        private static readonly Dictionary<string, string> ControllerFirstClaimer = BuildControllerFirstClaimer();

        private static Dictionary<string, string> BuildControllerFirstClaimer()
        {
            // Build a flat list of (controller, server) pairs in AliasToController
            // iteration order. The first occurrence of each controller name is
            // the "winner" if the JSON later has a collision.
            var claimer = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var (server, controllers) in AliasToController)
            {
                foreach (var c in controllers)
                {
                    if (!claimer.ContainsKey(c)) claimer[c] = server;
                }
            }
            return claimer;
        }

        // ── Lifecycle ─────────────────────────────────────────────────────────

        /// <summary>
        /// Wire the singleton + start the polling timer. Call from Main._Ready
        /// AFTER you've set <see cref="MotionLibraryPath"/>. The first load
        /// happens synchronously here (so AnimSources is populated by the time
        /// the first directive can fire); subsequent loads happen on the
        /// 5-minute timer.
        /// </summary>
        public void Attach(AnimationPlayer animPlayer = null, Node parent = null)
        {
            if (_attached)
            {
                GD.Print("[MotionLibrary] already attached; ignoring duplicate Attach()");
                return;
            }
            _attached = true;
            Instance = this;

            // Standalone mode: if Attach was called without adding us to a
            // scene tree (Main wires the node, but the singleton can also be
            // created and never parented), we need to be a Node so the Timer
            // ticks. Add to Main if no parent given.
            if (parent != null && GetParent() == null)
                parent.AddChild(this);

            if (string.IsNullOrWhiteSpace(MotionLibraryPath))
                MotionLibraryPath = DefaultPath();

            // Resolve res:// / user:// → absolute path for File APIs.
            string resolved = ResolveConfigPath(MotionLibraryPath);
            _currentPath = resolved;
            GD.Print($"[MotionLibrary] watching '{resolved}' (poll={PollIntervalSec:F0}s)");

            // First load (synchronous; cheap JSON parse).
            ReloadNow();

            // Set up the polling timer. We use a real Godot Timer rather
            // than a delta accumulator in _Process because:
            //   1. the cadence is 5 minutes, not 16ms — a delta poll would
            //      fire 18750 times before each real check, wasting CPU;
            //   2. Timer survives pause / focus changes more cleanly.
            _pollTimer = new Timer
            {
                Name = "MotionLibraryPoll",
                WaitTime = PollIntervalSec,
                OneShot = false,
                Autostart = true,
            };
            AddChild(_pollTimer);
            _pollTimer.Timeout += OnPollTimer;
        }

        /// <summary>Force a reload right now (e.g. for tests / hot-reload debugging).
        /// Returns the count of animations loaded, or -1 on failure.</summary>
        public int ReloadNow()
        {
            try
            {
                if (!File.Exists(_currentPath))
                {
                    GD.PrintErr($"[MotionLibrary] file not found: {_currentPath} — keeping last-known AnimSources (count={_animSources.Count})");
                    return _animSources.Count;
                }

                DateTime mtime = File.GetLastWriteTimeUtc(_currentPath);
                if (mtime == _lastMtimeUtc && !string.IsNullOrEmpty(_currentHash))
                {
                    // Same mtime as last successful load. Skip hash check too?
                    // No — mtime can stay the same when contents change (rare
                    // but real: a touch-only save). We accept the cheap hash
                    // read once per poll cycle.
                }

                string raw = File.ReadAllText(_currentPath, Encoding.UTF8);
                string sha = Sha256Hex(raw);

                // Skip if neither mtime nor hash changed.
                if (mtime == _lastMtimeUtc && sha == _currentHash)
                {
                    return _animSources.Count;
                }

                var newDict = ParseAnimations(raw, _currentPath);
                if (newDict == null) return -1;

                // Capture the previous name set BEFORE swapping, so we can
                // diff and emit LibraryAnimationsAdded with the entries that
                // are truly new. This is what the auto-curator uses to
                // hot-swap freshly downloaded FBX/GLB into the AnimPlayer.
                var prevNames = new HashSet<string>(_animSources.Keys, StringComparer.OrdinalIgnoreCase);
                var added = new Dictionary<string, AnimSpec>(StringComparer.OrdinalIgnoreCase);
                foreach (var kv in newDict)
                {
                    if (!prevNames.Contains(kv.Key)) added[kv.Key] = kv.Value;
                }

                _animSources = newDict;
                _currentHash = sha;
                _lastMtimeUtc = mtime;
                LastLoadedUtc = DateTime.UtcNow;
                LastCount = newDict.Count;

                GD.Print($"[MotionLibrary] loaded {newDict.Count} animations, hash={sha.Substring(0, 8)} (added {added.Count} new)");
                LibraryUpdated?.Invoke(newDict.Count, sha.Substring(0, 8));
                if (added.Count > 0)
                {
                    // Log the new entries so the operator can see what changed
                    // without attaching a debugger. Keep the log compact.
                    var addedNames = string.Join(", ", added.Keys.OrderBy(k => k, StringComparer.OrdinalIgnoreCase));
                    GD.Print($"[MotionLibrary] LibraryAnimationsAdded: {added.Count} new ({addedNames})");
                    LibraryAnimationsAdded?.Invoke(added);
                }
                return newDict.Count;
            }
            catch (Exception e)
            {
                GD.PrintErr($"[MotionLibrary] reload failed: {e.Message}");
                return -1;
            }
        }

        // ── Internals ─────────────────────────────────────────────────────────

        private void OnPollTimer()
        {
            ReloadNow();
        }

        private static string DefaultPath()
        {
            // Server is configured to drop motion_library.json under
            //   C:\Users\Tench\Documents\AriaAssistantAppIKdiffusion\astro_assistant\
            // (one level up from the Godot project, in the "astro_assistant" sibling).
            // The Main.tscn exporter defaults MotionLibraryPath to that; this is
            // a defensive fallback if the export is missing.
            try
            {
                string projectDir = ProjectSettings.GlobalizePath("res://");
                if (!string.IsNullOrEmpty(projectDir))
                {
                    string sibling = Path.GetFullPath(Path.Combine(projectDir, "..", "astro_assistant", "motion_library.json"));
                    return sibling.Replace('\\', '/');
                }
            }
            catch (Exception e)
            {
                // Original code silently fell through. That meant: if ProjectSettings
                // didn't resolve or the sibling path was unreachable, Aria just
                // quietly used the bare filename "motion_library.json" and the
                // operator had no idea why the library was empty. Now we surface
                // the failure; the run still continues with the fallback.
                GD.PrintErr($"[MotionLibrary] DefaultPath resolution failed: {e.Message} — falling back to bare filename");
            }
            return "motion_library.json";
        }

        private static string ResolveConfigPath(string p)
        {
            if (string.IsNullOrWhiteSpace(p)) return p;
            if (p.StartsWith("res://") || p.StartsWith("user://"))
                return ProjectSettings.GlobalizePath(p);
            return p;
        }

        // Parse the motion_library.json produced by ingest_motion_library.py
        // into a flat dict of (controller short name → AnimSpec).
        //
        // Each server AnimFileEntry produces one or more AnimSpec entries —
        // one per canonical controller name in AliasToController[a.Name]
        // (which is 1:1 except for `standing_greeting` → [wave, react] which
        // is 1:2 because the same FBX backs both controller names in the
        // baked AnimSources). Server names not in AliasToController fall
        // through to their own server name as the controller key, so every
        // server entry is reflected at least once.
        //
        // Collision handling: if the JSON ever ships two server entries
        // whose controller name lists overlap, the FIRST occurrence (by JSON
        // order) wins. The losing entry is logged as a conflict and skipped.
        // This can only happen if the AliasToController table itself has
        // controller names that overlap between server names — the current
        // table is collision-free, so this branch is dormant today but
        // logged if a future alias edit introduces a clash.
        private static Dictionary<string, AnimSpec> ParseAnimations(string raw, string path)
        {
            try
            {
                var opts = new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true,
                    ReadCommentHandling = JsonCommentHandling.Skip,
                    AllowTrailingCommas = true,
                };
                var file = JsonSerializer.Deserialize<MotionLibraryFile>(raw, opts);
                if (file == null || file.Animations == null)
                {
                    GD.PrintErr($"[MotionLibrary] '{path}' parsed but has no 'animations' array");
                    return null;
                }

                var result = new Dictionary<string, AnimSpec>(StringComparer.OrdinalIgnoreCase);
                int aliasedCount = 0;
                int conflictCount = 0;
                foreach (var a in file.Animations)
                {
                    if (a == null || string.IsNullOrWhiteSpace(a.Name)) continue;

                    // Resolve the list of controller names this server entry
                    // populates. Default to the server's own name (1 entry)
                    // if no alias is registered — every server entry in the
                    // JSON is reflected at least once.
                    string[] controllerNames;
                    if (AliasToController.TryGetValue(a.Name, out var mapped))
                    {
                        controllerNames = mapped;
                        aliasedCount++;
                    }
                    else
                    {
                        controllerNames = new[] { a.Name };
                    }

                    // Emit one AnimSpec per controller name. They share the
                    // same underlying AnimFileEntry data (duration, isInPlace,
                    // travel, etc.) — different controller names that point
                    // at the same FBX (wave vs react) get identical AnimSpec
                    // values, which is exactly the "one source, multiple
                    // entry points" semantic the LLM wants.
                    foreach (var controllerName in controllerNames)
                    {
                        if (result.ContainsKey(controllerName))
                        {
                            // The AliasToController table itself is
                            // collision-free (every controller name is unique
                            // across server entries), so the only way we hit
                            // this branch is if the JSON ships two server
                            // entries whose controller-name lists overlap —
                            // e.g. a future server entry literally named
                            // `wave` would collide with `standing_greeting`.
                            // The first JSON occurrence wins; the loser is
                            // logged for the producer.
                            conflictCount++;
                            GD.Print($"[MotionLibrary] conflict: server entry '{a.Name}' tried to populate already-claimed controller '{controllerName}' (kept the earlier entry from '{ControllerFirstClaimer[controllerName]}')");
                            continue;
                        }
                        result[controllerName] = AnimSpec.FromFile(a, controllerName);
                    }
                }

                // Diagnostic: how many server entries used the alias table
                // vs. fell through to their own name. This is logged so
                // future audits can spot when the alias table drifts from
                // the actual server output.
                int unaliased = file.Animations.Count(a => a != null && !string.IsNullOrWhiteSpace(a.Name)) - aliasedCount;
                GD.Print($"[MotionLibrary] parsed {file.Animations.Count} server entries: {aliasedCount} aliased, {unaliased} identity-mapped, {result.Count} controller slots, {conflictCount} conflicts");

                if (result.Count == 0)
                {
                    GD.PrintErr($"[MotionLibrary] '{path}' had {file.Animations.Count} anim entries but none mapped to a controller name; check the alias table");
                    return null;
                }
                return result;
            }
            catch (JsonException je)
            {
                GD.PrintErr($"[MotionLibrary] JSON parse error in '{path}': {je.Message}");
                return null;
            }
        }

        private static string Sha256Hex(string s)
        {
            using var sha = SHA256.Create();
            byte[] bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(s));
            var sb = new StringBuilder(bytes.Length * 2);
            foreach (byte b in bytes) sb.Append(b.ToString("x2"));
            return sb.ToString();
        }

        // ── File / Spec types ─────────────────────────────────────────────────

        // Schema mirror of astro_assistant/motion_library.json. Field names
        // are PascalCase here, but the JSON property names are case-insensitive
        // (JsonSerializerOptions.PropertyNameCaseInsensitive=true above).
        internal class MotionLibraryFile
        {
            [JsonPropertyName("schemaVersion")] public int SchemaVersion { get; set; }
            [JsonPropertyName("generatedAt")]  public string GeneratedAt { get; set; } = "";
            [JsonPropertyName("generator")]    public string Generator { get; set; } = "";
            [JsonPropertyName("modelPath")]    public string ModelPath { get; set; } = "";
            [JsonPropertyName("animations")]   public List<AnimFileEntry> Animations { get; set; } = new();
        }

        internal class AnimFileEntry
        {
            [JsonPropertyName("name")]            public string Name { get; set; } = "";
            [JsonPropertyName("file")]            public string File { get; set; } = "";
            [JsonPropertyName("curatorState")]    public string CuratorState { get; set; } = "raw";
            [JsonPropertyName("durationSec")]     public float DurationSec { get; set; }
            [JsonPropertyName("isInPlace")]       public bool IsInPlace { get; set; } = true;
            [JsonPropertyName("rootMotion")]      public RootMotionEntry RootMotion { get; set; }
            [JsonPropertyName("contactFrames")]   public List<float> ContactFrames { get; set; } = new();
            [JsonPropertyName("fps")]             public int Fps { get; set; } = 30;
            [JsonPropertyName("boneSet")]         public string BoneSet { get; set; } = "mixamo";
            [JsonPropertyName("trackCount")]      public int TrackCount { get; set; }
            [JsonPropertyName("needsRetarget")]   public bool NeedsRetarget { get; set; }
            [JsonPropertyName("godotUid")]        public string GodotUid { get; set; } = "";
        }

        internal class RootMotionEntry
        {
            [JsonPropertyName("dx")]    public float Dx { get; set; }
            [JsonPropertyName("dy")]    public float Dy { get; set; }
            [JsonPropertyName("dz")]    public float Dz { get; set; }
            [JsonPropertyName("total")] public float Total { get; set; }
        }
    }

    /// <summary>
    /// Public, immutable view of one animation's metadata. Created from
    /// motion_library.json; defaults applied for missing fields so consumers
    /// never have to null-check.
    /// </summary>
    public sealed class AnimSpec
    {
        /// <summary>Canonical controller short name (e.g. "wave", "walk").</summary>
        public string Name { get; init; } = "";

        /// <summary>Server-emitted file path (e.g. "aria/ani/Standing Greeting.fbx").</summary>
        public string File { get; init; } = "";

        /// <summary>Length of the clip in seconds.</summary>
        public float DurationSec { get; init; }

        /// <summary>True if the animation has no real locomotion — feet stay
        /// planted. Used to decide whether to apply in-place translation.</summary>
        public bool IsInPlace { get; init; } = true;

        /// <summary>World-units of horizontal travel per second of clip time.
        /// For in-place anims this is ~0.</summary>
        public float TravelSpeed { get; init; }

        /// <summary>Allowed speed-scale range for this anim. Default
        /// [0.5, 2.0] is the safe range where most mocap clips still
        /// look natural (too slow = jitter; too fast = foot slide).</summary>
        public (float Min, float Max) SpeedScaleRange { get; init; } = (0.5f, 2.0f);

        /// <summary>True if the LLM is allowed to issue a cut-short for this
        /// anim (e.g. "wave for half duration"). False for looped anims where
        /// cutting in the middle would leave a frozen pose.</summary>
        public bool CanCutShort { get; init; } = true;

        /// <summary>If set, the earliest point in the clip where a cut is
        /// allowed. Default 0.0 = "any prefix is fine".</summary>
        public float CutShortAtSec { get; init; } = 0.0f;

        /// <summary>Root-motion summary — total world-unit displacement of
        /// the hips bone from t=0 to t=end. Useful for sanity-checking
        /// isInPlace + travelSpeed.</summary>
        public float RootMotionTotal { get; init; }

        /// <summary>Frame times (seconds) where a foot is in contact with
        /// the ground. Used by future auto-looping logic; consumers can
        /// also use them to time cut-short points at "feet planted".</summary>
        public IReadOnlyList<float> ContactFrames { get; init; } = Array.Empty<float>();

        /// <summary>"mixamo" / "vrm" / etc. — informs retargeting decisions.</summary>
        public string BoneSet { get; init; } = "mixamo";

        /// <summary>True if the server flagged this anim as needing retarget
        /// (e.g. boneSet != "mixamo", or tracks reference a non-Aria skeleton).</summary>
        public bool NeedsRetarget { get; init; }

        /// <summary>"curated" / "raw" / "auto" — what pipeline produced this entry.</summary>
        public string CuratorState { get; init; } = "raw";

        /// <summary>FPS the track keys were sampled at.</summary>
        public int Fps { get; init; } = 30;

        /// <summary>Number of tracks in the source clip.</summary>
        public int TrackCount { get; init; }

        /// <summary>Server-emitted Godot UID for the imported .tres (if any).</summary>
        public string GodotUid { get; init; } = "";

        // Internal factory: pulls fields from the file entry, applies defaults.
        internal static AnimSpec FromFile(MotionLibraryMirror.AnimFileEntry a, string controllerName)
        {
            float total = a.RootMotion?.Total ?? 0f;
            // Travel speed = world-unit displacement per second of clip time.
            // For in-place anims this collapses to ~0. For locomotion anims
            // it's a real m/s number.
            float travel = a.DurationSec > 0.01f ? total / a.DurationSec : 0f;

            return new AnimSpec
            {
                Name = controllerName,
                File = a.File ?? "",
                DurationSec = a.DurationSec,
                IsInPlace = a.IsInPlace,
                TravelSpeed = travel,
                SpeedScaleRange = (0.5f, 2.0f),
                CanCutShort = a.IsInPlace,    // in-place anims are cuttable; locomotion anims generally aren't
                CutShortAtSec = 0.0f,
                RootMotionTotal = total,
                ContactFrames = a.ContactFrames?.ToArray() ?? Array.Empty<float>(),
                BoneSet = string.IsNullOrEmpty(a.BoneSet) ? "mixamo" : a.BoneSet,
                NeedsRetarget = a.NeedsRetarget,
                CuratorState = string.IsNullOrEmpty(a.CuratorState) ? "raw" : a.CuratorState,
                Fps = a.Fps > 0 ? a.Fps : 30,
                TrackCount = a.TrackCount,
                GodotUid = a.GodotUid ?? "",
            };
        }
    }
}
