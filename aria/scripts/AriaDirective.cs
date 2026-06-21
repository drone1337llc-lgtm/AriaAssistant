using Godot;
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Aria
{
    /// <summary>
    /// WHERE to look when an LLM directive names a target by label
    /// (e.g. "user_cursor", "nearest_window", "highest_window").
    /// Resolved into a concrete Vector2 by CharacterController.SubmitDirective
    /// at execution time — the LLM never has to compute pixels.
    /// </summary>
    public enum DirectiveTarget
    {
        None,            // explicit x/y given
        UserCursor,      // last known cursor position (Main.cs caches from _Input)
        NearestWindow,   // closest window by horizontal distance
        HighestWindow,   // topmost window still in reach (smallest top y)
        LeftEdge,        // far left of the usable screen
        RightEdge,       // far right of the usable screen
        Center,          // horizontal centre of the usable screen
        Current,         // stay at current feet (no-op for x)
    }

    /// <summary>
    /// The vocabulary the LLM can use to direct Aria's body. Each Kind maps
    /// to a concrete action in CharacterController. Kinds are kept stable
    /// because the system prompt teaches Humanish the names verbatim.
    /// </summary>
    public enum DirectiveKind
    {
        // ── Body-level (drive the 8-state machine) ─────────────────────
        Idle,           // settle here, run the idle clip (or specified one) for `duration` sec
        TurnTo,         // rotate to face `target` (or specified yaw degrees)
        WalkTo,         // walk to absolute (x, y) in viewport-relative px, with optional target
        WalkToward,     // walk toward a named target (user cursor, nearest window, etc.)
        Climb,          // climb the window nearest her, or a specific window_id
        HopOff,         // step off a perch and fall (commit EnterFall)
        Gesture,        // one-shot gesture (wave, dance, react…) for `duration` sec
        Play,           // like Gesture but with rich per-anim controls: SpeedScale,
                        // CutAtSec, CutAtFrac. The LLM emits this as
                        // {"action":"play", "anim":"wave", "speed":0.7, "cut_at":0.5, "cut_at_frac":true}
        Say,            // placeholder: the brain already emits say/emotion out-of-band;
                        // this Kind exists so a directive can carry a delayed follow-up line
        Pause,          // wait `duration` seconds (e.g. "look at that for a moment")

        // ── IK (procedural inverse kinematics, layer over the animation) ─
        // All IK directives resolve the `chain` field against AriaIKChains.Resolve(name)
        // (arms, legs, spine, head, fingers). Targets are named (UserCursor / NearestWindow / …)
        // or absolute (x, y) in viewport-relative px. Bone-level pose deltas are
        // ADDITIVE on top of the playing animation (walk keeps going while she reaches).
        IkReach,        // chain: "arm_left"|"arm_right"|…, target: …, hand_orientation: optional
        IkPoint,        // like IkReach but orients the hand bone to point at the target
        IkLook,         // head/eyes look at target; uses HeadChain (2-bone analytical)
        IkLean,         // spine/torso lean direction (forward/back/left/right) by amount [0..1]
        IkTwist,        // upper-body twist (yaw + pitch, degrees)
        IkStep,         // leg step: foot lands at (x_offset, y_offset, height) relative to hips
        IkLiftLeg,      // lift foot to (x, y, height) — for stepping up / kicking
        IkGrip,         // finger pose preset: "open"|"closed"|"point"|"peace"|"thumbs_up"
        IkRelease,      // clear IK on a single chain (back to animation-driven)
        IkReleaseAll,   // clear IK on every chain (back to full animation-driven)
        IkHoldPose,     // freeze the current IK pose for `duration` seconds

        // ── Motion-diffusion (FloodDiffusion on PC 2) ──────────────────
        // Asks the AI server to generate a new motion clip from a text prompt,
        // queue it (cap 100, one at a time on the server), and auto-bake the
        // result into the AnimationLibrary when it arrives. The directive
        // completes when the request is enqueued (the actual generation is async).
        RequestMotion,
    }

    /// <summary>
    /// A single body command from the brain. Designed to be cheap to construct
    /// (struct-style public fields, no Godot.Collections), JSON-roundtrippable,
    /// and copyable by value into a queue.
    ///
    /// Resolution: the LLM emits JSON like
    ///   {"action":"walk_to", "x":800, "y":900}
    ///   {"action":"walk_toward", "target":"nearest_window"}
    ///   {"action":"climb"}
    ///   {"action":"gesture", "name":"wave", "duration":2.0}
    ///   {"action":"turn_to", "yaw_deg":90}
    ///   {"action":"turn_to", "target":"user_cursor"}
    ///   {"action":"pause", "duration":1.5}
    /// Targets that name a place are resolved against the live WorldState at
    /// execute time, not parse time, so they always reflect the latest layout.
    /// </summary>
    public partial class AriaDirective : GodotObject
    {
        [JsonPropertyName("action")]        public DirectiveKind Kind { get; set; } = DirectiveKind.Idle;
        [JsonPropertyName("name")]          public string Name { get; set; } = "";        // gesture / chain / preset name
        [JsonPropertyName("x")]             public float X { get; set; } = float.NaN;     // absolute viewport-relative px
        [JsonPropertyName("y")]             public float Y { get; set; } = float.NaN;
        [JsonPropertyName("z")]             public float Z { get; set; } = float.NaN;     // absolute world Z (used by debug scene for 3D targets; ignored by the main scene's pixel-based locomotion)
        [JsonPropertyName("target")]        public DirectiveTarget Target { get; set; } = DirectiveTarget.None;
        [JsonPropertyName("yaw_deg")]       public float YawDeg { get; set; } = float.NaN;
        [JsonPropertyName("pitch_deg")]     public float PitchDeg { get; set; } = float.NaN; // for IkTwist
        [JsonPropertyName("duration")]      public float Duration { get; set; } = 0f;    // seconds
        [JsonPropertyName("window_id")]     public int WindowId { get; set; } = -1;       // for climb
        [JsonPropertyName("amount")]        public float Amount { get; set; } = 0f;        // [0..1] for IkLean, [0..1] for IkGrip close
        [JsonPropertyName("direction")]     public string Direction { get; set; } = "";    // "forward"|"back"|"left"|"right" for IkLean
        [JsonPropertyName("hand")]          public string Hand { get; set; } = "";         // "left"|"right" for IkGrip / IkStep / IkLiftLeg
        [JsonPropertyName("height")]        public float Height { get; set; } = 0f;        // px for IkLiftLeg foot lift
        [JsonPropertyName("prompt")]        public string Prompt { get; set; } = "";       // for RequestMotion (text -> clip)
        [JsonPropertyName("frames")]        public int Frames { get; set; } = 0;           // for RequestMotion (clip length)
        [JsonPropertyName("weight")]        public float Weight { get; set; } = 1f;        // blend strength for IkReach/Point

        // ── PlayAnim fine-grained controls (action: "play" / "gesture") ──
        // speedScale multiplies the per-anim TravelSpeed when applying
        // the in-place translation. Default 1.0 = "use the anim's natural
        // cadence as the source-of-truth".
        [JsonPropertyName("speed")]         public float SpeedScale { get; set; } = 1.0f;
        // cutAtSec: stop the animation at this absolute time (seconds) once
        // the player reaches it. When the cut point is reached, CharacterController
        // fires its CutShortReached event and stops the player cleanly.
        // Default 0.0 = "no cut" (play the whole thing).
        [JsonPropertyName("cut_at")]        public float CutAtSec { get; set; } = 0.0f;
        // cutAtFrac: if true, CutAtSec is a fraction of the anim's
        // DurationSec (0.0..1.0). Useful for "play half the wave" without
        // the LLM having to know the clip's exact length.
        [JsonPropertyName("cut_at_frac")]   public bool CutAtFrac { get; set; } = false;

        public bool IsValid()
        {
            // Every kind has a minimal requirement; missing fields fall back to defaults.
            switch (Kind)
            {
                case DirectiveKind.WalkTo:
                    return !float.IsNaN(X) && !float.IsNaN(Y);
                case DirectiveKind.TurnTo:
                    return !float.IsNaN(YawDeg) || Target != DirectiveTarget.None;
                case DirectiveKind.WalkToward:
                    return Target != DirectiveTarget.None;
                case DirectiveKind.Climb:
                    return true;   // defaults to nearest
                case DirectiveKind.Gesture:
                    return !string.IsNullOrWhiteSpace(Name);
                case DirectiveKind.Idle:
                case DirectiveKind.HopOff:
                case DirectiveKind.Pause:
                case DirectiveKind.Say:
                    return true;
                case DirectiveKind.Play:
                    // Play: name is the short animation name; duration, speed
                    // and cut_at are optional (defaults are sensible).
                    return !string.IsNullOrWhiteSpace(Name);

                // ── IK kinds — chain is required; target is required for reach/look/point ──
                case DirectiveKind.IkReach:
                case DirectiveKind.IkPoint:
                    return !string.IsNullOrWhiteSpace(Name)   // Name is the chain
                        && (!float.IsNaN(X) && !float.IsNaN(Y) || Target != DirectiveTarget.None);
                case DirectiveKind.IkLook:
                    return !float.IsNaN(X) && !float.IsNaN(Y) || Target != DirectiveTarget.None;
                case DirectiveKind.IkLean:
                case DirectiveKind.IkTwist:
                    return true;   // direction/yaw default if missing
                case DirectiveKind.IkStep:
                case DirectiveKind.IkLiftLeg:
                    return !string.IsNullOrWhiteSpace(Hand);   // "left" / "right" required
                case DirectiveKind.IkGrip:
                    return !string.IsNullOrWhiteSpace(Hand) && !string.IsNullOrWhiteSpace(Name);
                case DirectiveKind.IkRelease:
                    return !string.IsNullOrWhiteSpace(Name);    // chain name to release
                case DirectiveKind.IkReleaseAll:
                    return true;
                case DirectiveKind.IkHoldPose:
                    return Duration > 0.05f;

                // ── Motion-diffusion request — text prompt is the only requirement ──
                case DirectiveKind.RequestMotion:
                    return !string.IsNullOrWhiteSpace(Prompt);
                default:
                    return false;
            }
        }

        public string Describe()
        {
            string s = Kind.ToString().ToLowerInvariant();
            if (!float.IsNaN(X) && !float.IsNaN(Y)) s += $"({X:F0},{Y:F0})";
            else if (Target != DirectiveTarget.None) s += $"→{Target.ToString().ToLowerInvariant()}";
            else if (!float.IsNaN(YawDeg)) s += $"@{YawDeg:F0}°";
            if (!string.IsNullOrEmpty(Name)) s += $" '{Name}'";
            if (!string.IsNullOrEmpty(Hand)) s += $" hand={Hand}";
            if (!string.IsNullOrEmpty(Direction)) s += $" dir={Direction}";
            if (Amount > 0) s += $" amt={Amount:F2}";
            if (Height > 0) s += $" h={Height:F0}";
            if (!string.IsNullOrEmpty(Prompt)) s += $" prompt='{Prompt}'";
            if (Duration > 0) s += $" {Duration:F1}s";
            if (Math.Abs(SpeedScale - 1.0f) > 0.001f) s += $" speed={SpeedScale:F2}x";
            if (CutAtSec > 0.0001f) s += $" cutAt={CutAtSec:F2}s{(CutAtFrac ? "(frac)" : "")}";
            return s;
        }
    }

    /// <summary>
    /// The LLM's "world state" payload — what Aria knows about her surroundings
    /// in the moment. Serialized into a compact JSON block and prepended to the
    /// system prompt on every call, so Humanish can plan directives against the
    /// actual scene rather than guessing.
    ///
    /// Keep fields small and stable: changing a name is a prompt break.
    /// </summary>
    public class WorldState
    {
        // Position / posture
        [JsonPropertyName("feet")]        public Vector2 Feet { get; set; }       // viewport-relative px
        [JsonPropertyName("head")]        public Vector2 Head { get; set; }       // viewport-relative px
        [JsonPropertyName("state")]       public string State { get; set; } = "idle";  // matches CharacterController.State
        [JsonPropertyName("is_perched")]  public bool IsPerched { get; set; }
        [JsonPropertyName("idle_sec")]    public float IdleSeconds { get; set; }   // how long in the current state
        [JsonPropertyName("emotion")]     public string Emotion { get; set; } = "neutral";

        // Bounds (in viewport-relative px)
        [JsonPropertyName("screen_w")]    public float ScreenW { get; set; }
        [JsonPropertyName("screen_h")]    public float ScreenH { get; set; }
        [JsonPropertyName("floor_y")]     public float FloorY { get; set; }

        // Windows on the desktop (id + bounding box + a one-word hint about size/position).
        // Limited to ~5 to keep the prompt small; the LLM doesn't need all of them.
        [JsonPropertyName("windows")]
        public List<WindowInfo> Windows { get; set; } = new();

        // The user — the brain talks to them, so it helps to know where they are
        [JsonPropertyName("user_cursor")] public Vector2? UserCursor { get; set; }   // last seen cursor pos, viewport-relative
        [JsonPropertyName("foreground")]  public string Foreground { get; set; } = ""; // title of the foreground app

        // Motion-diffusion queue (only present on the diffusion-enabled build;
        // omitted from the JSON on the IK-only build to keep the prompt slim)
        [JsonPropertyName("motion_queue_depth")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public int? MotionQueueDepth { get; set; }
        [JsonPropertyName("motion_queue_capacity")]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public int? MotionQueueCapacity { get; set; }
        [JsonPropertyName("motion_recent")]
        public List<string> MotionRecent { get; set; } = new();   // last few RequestMotion prompts so the brain remembers

        public class WindowInfo
        {
            [JsonPropertyName("id")]   public int Id { get; set; }
            [JsonPropertyName("x")]    public float X { get; set; }     // viewport-relative px
            [JsonPropertyName("y")]    public float Y { get; set; }     // viewport-relative px
            [JsonPropertyName("w")]    public float W { get; set; }
            [JsonPropertyName("h")]    public float H { get; set; }
            [JsonPropertyName("hint")] public string Hint { get; set; } = "";   // "near", "far-left", "tall", …
        }

        /// <summary>
        /// Render the world state as a one-line JSON snippet the system prompt
        /// can show the LLM verbatim. The brain only sends this when there's a
        /// real change OR when the LLM is being asked to plan actions — saves tokens.
        /// </summary>
        public string ToPromptBlock()
        {
            var opts = new JsonSerializerOptions { WriteIndented = false };
            opts.Converters.Add(new Vector2JsonConverter());
            opts.Converters.Add(new Vector2NullableJsonConverter());
            return JsonSerializer.Serialize(this, opts);
        }
    }

    // JSON converters for Vector2 / Nullable<Vector2> so the WorldState serializes cleanly.
    internal sealed class Vector2JsonConverter : JsonConverter<Vector2>
    {
        public override Vector2 Read(ref Utf8JsonReader r, Type t, JsonSerializerOptions o)
        {
            if (r.TokenType != JsonTokenType.StartArray) throw new JsonException("expected [x,y]");
            r.Read(); float x = (float)r.GetDouble();
            r.Read(); float y = (float)r.GetDouble();
            r.Read(); if (r.TokenType != JsonTokenType.EndArray) throw new JsonException("expected end of array");
            return new Vector2(x, y);
        }
        public override void Write(Utf8JsonWriter w, Vector2 v, JsonSerializerOptions o)
        {
            w.WriteStartArray();
            w.WriteNumberValue(MathF.Round(v.X));
            w.WriteNumberValue(MathF.Round(v.Y));
            w.WriteEndArray();
        }
    }
    internal sealed class Vector2NullableJsonConverter : JsonConverter<Vector2?>
    {
        public override Vector2? Read(ref Utf8JsonReader r, Type t, JsonSerializerOptions o)
        {
            if (r.TokenType == JsonTokenType.Null) return null;
            var v = JsonSerializer.Deserialize<Vector2>(ref r, o);
            return v;
        }
        public override void Write(Utf8JsonWriter w, Vector2? v, JsonSerializerOptions o)
        {
            if (v.HasValue) JsonSerializer.Serialize(w, v.Value, o);
            else w.WriteNullValue();
        }
    }
}
