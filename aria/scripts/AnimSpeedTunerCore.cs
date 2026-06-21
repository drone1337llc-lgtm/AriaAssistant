using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Aria
{
    /// <summary>
    /// Pure-C# (Godot-free) core of the per-animation self-tuning speed
    /// tracker. Extracted into its own type so the algorithm is testable
    /// in a vanilla .NET process — the Godot wrapper (AnimSpeedTuner)
    /// delegates to it. The Godot wrapper handles the <c>Vector2</c> /
    /// <c>GD.Print</c> surface, this class handles the math + JSON.
    ///
    /// Behaviour matches the task spec verbatim:
    ///  1. First N &lt; 10 plays of any anim are SHADOW (log only, no override).
    ///  2. After N &gt;= 10 plays of the same anim, switch to ACTIVE mode.
    ///     tunedScale = current * 0.7 + (1 / ratio) * 0.3   (EMA, α=0.3)
    ///     ratio     = actualSum / expectedSum, clamped to [0.5, 2.0]
    ///     result    = re-clamped to [0.5, 2.0]
    ///  3. Effective scale = userSupplied * tunedScale (NEVER overridden).
    ///  4. Stats persist to JSON, schema:
    ///     { "&lt;anim&gt;": { "plays": int, "actualSum": float,
    ///                        "expectedSum": float, "tunedScale": float,
    ///                        "tunedAt": "&lt;iso&gt;" } }
    ///
    /// Logging: <see cref="Log"/> is a delegate the host wires to its own
    /// log sink (e.g. <c>GD.Print</c> in production, a List&lt;string&gt;
    /// in tests). Log level lets the test harness filter for shadow /
    /// active transitions.
    /// </summary>
    public sealed class AnimSpeedTunerCore
    {
        public const int   ActiveThreshold = 10;
        public const float EmaAlpha        = 0.3f;
        public const float MinScale        = 0.5f;
        public const float MaxScale        = 2.0f;

        public enum LogLevel { Info, Shadow, Active, Warn, Error }

        /// <summary>Host-supplied log sink. Null = no logging.</summary>
        public Action<LogLevel, string> Log;

        public sealed class Stat
        {
            public int   Plays       { get; set; }
            public float ActualSum   { get; set; }
            public float ExpectedSum { get; set; }
            public float TunedScale  { get; set; } = 1.0f;
            public string TunedAt    { get; set; } = "";
        }

        private readonly Dictionary<string, Stat> _stats = new();
        private readonly string _jsonPath;
        private readonly object _lock = new();

        public AnimSpeedTunerCore(string jsonPath)
        {
            _jsonPath = jsonPath;
        }

        public IReadOnlyDictionary<string, Stat> Snapshot()
        {
            lock (_lock) return new Dictionary<string, Stat>(_stats);
        }

        public void Load()
        {
            try
            {
                if (!File.Exists(_jsonPath)) return;
                string json = File.ReadAllText(_jsonPath);
                if (string.IsNullOrWhiteSpace(json)) return;
                var opts = new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true,
                    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                };
                var loaded = JsonSerializer.Deserialize<Dictionary<string, Stat>>(json, opts);
                if (loaded == null) return;
                lock (_lock)
                {
                    _stats.Clear();
                    foreach (var kv in loaded)
                    {
                        if (kv.Value == null) continue;
                        kv.Value.TunedScale = Math.Clamp(kv.Value.TunedScale, MinScale, MaxScale);
                        _stats[kv.Key] = kv.Value;
                    }
                }
                Log?.Invoke(LogLevel.Info, $"[SpeedTuner] loaded {loaded.Count} anim stats from {_jsonPath}");
            }
            catch (Exception e)
            {
                Log?.Invoke(LogLevel.Error, $"[SpeedTuner] failed to load {_jsonPath}: {e.Message}");
            }
        }

        public void Save()
        {
            try
            {
                var dir = Path.GetDirectoryName(_jsonPath);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                    Directory.CreateDirectory(dir);

                var opts = new JsonSerializerOptions
                {
                    WriteIndented = true,
                    DefaultIgnoreCondition = JsonIgnoreCondition.Never,
                    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                };
                Dictionary<string, Stat> snap;
                lock (_lock) snap = new Dictionary<string, Stat>(_stats);
                string json = JsonSerializer.Serialize(snap, opts);
                File.WriteAllText(_jsonPath, json);
            }
            catch (Exception e)
            {
                Log?.Invoke(LogLevel.Error, $"[SpeedTuner] failed to save {_jsonPath}: {e.Message}");
            }
        }

        /// <summary>
        /// Record one play observation. The two V2 inputs are flattened
        /// to their X magnitudes; locomotion anims only need horizontal
        /// travel. Persists after every record.
        /// </summary>
        public void RecordPlay(string anim, float requestedSpeedScale,
                               float actualTravelPx, float expectedTravelPx)
        {
            if (string.IsNullOrEmpty(anim)) return;
            float actual = Math.Abs(actualTravelPx);
            float expected = Math.Abs(expectedTravelPx);

            lock (_lock)
            {
                if (!_stats.TryGetValue(anim, out var s))
                {
                    s = new Stat();
                    _stats[anim] = s;
                }

                s.Plays += 1;
                s.ActualSum += actual;
                s.ExpectedSum += expected;

                if (s.Plays < ActiveThreshold)
                {
                    float ratio = expected > 0.0001f ? s.ActualSum / s.ExpectedSum : 1.0f;
                    Log?.Invoke(LogLevel.Shadow,
                        $"[SpeedTuner] shadow: anim={anim} plays={s.Plays} ratio={ratio:F3}");
                }
                else
                {
                    float ratio = s.ExpectedSum > 0.0001f
                        ? s.ActualSum / s.ExpectedSum
                        : 1.0f;
                    ratio = Math.Clamp(ratio, MinScale, MaxScale);
                    float inverse = 1.0f / ratio;
                    float newScale = s.TunedScale * (1.0f - EmaAlpha) + inverse * EmaAlpha;
                    s.TunedScale = Math.Clamp(newScale, MinScale, MaxScale);
                    s.TunedAt = DateTime.UtcNow.ToString("o");

                    Log?.Invoke(LogLevel.Active,
                        $"[SpeedTuner] active: anim={anim} tunedScale={s.TunedScale:F3} ratio={ratio:F3} plays={s.Plays}");
                }

                Save();
            }
        }

        /// <summary>1.0 for shadow / unknown anims, else the learned scale.</summary>
        public float GetEffectiveSpeedScale(string anim)
        {
            if (string.IsNullOrEmpty(anim)) return 1.0f;
            lock (_lock)
            {
                if (_stats.TryGetValue(anim, out var s) && s.Plays >= ActiveThreshold)
                    return s.TunedScale;
            }
            return 1.0f;
        }

        /// <summary>user * tuned, NEVER overrides user value (no clamp on output).</summary>
        public float Combine(string anim, float userSuppliedScale)
        {
            return userSuppliedScale * GetEffectiveSpeedScale(anim);
        }
    }
}
