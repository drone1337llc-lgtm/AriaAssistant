using Godot;
using System;
using System.Collections.Generic;
using System.IO;

namespace Aria
{
    /// <summary>
    /// Godot-facing wrapper around <see cref="AnimSpeedTunerCore"/>.
    /// The core is pure C# (testable in a vanilla .NET process); this
    /// class adds the <c>Vector2</c> / <c>GD.Print</c> surface and
    /// resolves the default JSON path via Godot's <c>res://</c> prefix.
    ///
    /// Singleton: instantiate one in Main._Ready() and pass it to
    /// CharacterController via <c>SetTuner()</c>.
    /// </summary>
    public sealed class AnimSpeedTuner
    {
        // ── Configuration (re-exposed as constants for callers) ─────

        public const int   ActiveThreshold = AnimSpeedTunerCore.ActiveThreshold;
        public const float EmaAlpha        = AnimSpeedTunerCore.EmaAlpha;
        public const float MinScale        = AnimSpeedTunerCore.MinScale;
        public const float MaxScale        = AnimSpeedTunerCore.MaxScale;

        /// <summary>Default JSON path: &lt;res://&gt;/../logs/anim_speed_tuner.json.</summary>
        public static string DefaultJsonPath =>
            Path.Combine(
                ProjectSettings.GlobalizePath("res://"),
                "..", "logs", "anim_speed_tuner.json");

        // ── Public surface ────────────────────────────────────────────

        public static AnimSpeedTuner Instance { get; private set; }

        public sealed class Stat
        {
            public int   Plays       { get; set; }
            public float ActualSum   { get; set; }
            public float ExpectedSum { get; set; }
            public float TunedScale  { get; set; } = 1.0f;
            public string TunedAt    { get; set; } = "";
        }

        // ── Internals ─────────────────────────────────────────────────

        private readonly AnimSpeedTunerCore _core;
        private readonly string _jsonPath;

        public AnimSpeedTuner(string jsonPath = null)
        {
            _jsonPath = jsonPath ?? DefaultJsonPath;
            _core = new AnimSpeedTunerCore(_jsonPath);
            _core.Log = OnLog;
            Instance = this;
            _core.Load();
        }

        private static void OnLog(AnimSpeedTunerCore.LogLevel level, string msg)
        {
            switch (level)
            {
                case AnimSpeedTunerCore.LogLevel.Error:
                case AnimSpeedTunerCore.LogLevel.Warn:
                    GD.PrintErr(msg);
                    break;
                default:
                    GD.Print(msg);
                    break;
            }
        }

        // ── Public API (matches the spec verbatim) ────────────────────

        /// <summary>
        /// Record one play observation. Updates the per-anim EMA in
        /// shadow mode (N &lt; 10) or active mode (N &gt;= 10). Persists
        /// after every record.
        /// </summary>
        public void RecordPlay(string anim, float requestedSpeedScale,
                               Vector2 actualTravelPx, Vector2 expectedTravelPx)
        {
            _core.RecordPlay(anim, requestedSpeedScale, actualTravelPx.X, expectedTravelPx.X);
        }

        /// <summary>
        /// Returns 1.0 for any anim with fewer than 10 recorded plays
        /// (including unknown anims). The user value multiplies against
        /// this — see <see cref="Combine"/>.
        /// </summary>
        public float GetEffectiveSpeedScale(string anim)
        {
            return _core.GetEffectiveSpeedScale(anim);
        }

        /// <summary>
        /// userSupplied * tunedScale. The user value is NEVER overridden,
        /// only multiplied. The [0.5, 2.0] safety band applies only to
        /// the tuner's own TunedScale field, NOT to the multiplied output.
        /// </summary>
        public float Combine(string anim, float userSuppliedScale)
        {
            return _core.Combine(anim, userSuppliedScale);
        }

        /// <summary>Read-only snapshot of all stats. For diagnostics / tests.</summary>
        public IReadOnlyDictionary<string, Stat> Snapshot()
        {
            var src = _core.Snapshot();
            var dst = new Dictionary<string, Stat>(src.Count);
            foreach (var kv in src)
            {
                dst[kv.Key] = new Stat
                {
                    Plays       = kv.Value.Plays,
                    ActualSum   = kv.Value.ActualSum,
                    ExpectedSum = kv.Value.ExpectedSum,
                    TunedScale  = kv.Value.TunedScale,
                    TunedAt     = kv.Value.TunedAt,
                };
            }
            return dst;
        }
    }
}
