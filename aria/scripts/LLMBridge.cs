using Godot;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
// Godot also defines a Godot.HttpClient; alias so bare HttpClient is unambiguous.
using HttpClient = System.Net.Http.HttpClient;

// The Aria namespace holds the directive + world-state types (AriaDirective.cs).
// They're nested under a namespace so Main.cs, CharacterController.cs, and LLMBridge.cs
// can share them without ambiguity (Main also has a top-level Main class).
using Aria;

/// <summary>
/// Aria's "brain": talks to a local OpenAI-compatible LLM endpoint (LM Studio,
/// Ollama, llama.cpp server, vLLM…). Beyond a single round-trip it now:
///
///   • keeps short conversation MEMORY (last N turns) for continuity,
///   • asks the model for a STRUCTURED reply — what to say, which emotion to
///     wear, and an optional body action — so the avatar can relay intent,
///   • parses that defensively (plain text still works),
///   • falls back to OFFLINE lines when the server is down (she keeps talking),
///   • LOGS every exchange to a JSONL dataset for the daily self-fine-tune loop,
///   • (new) emits a DIRECTIVE QUEUE — sequenced body commands the LLM can
///     chain in a single reply ("go to that window, wave, then sit").  The
///     queue is executed by CharacterController one item per frame, with the
///     existing 8-state machine as the reactive fallback when the queue is
///     empty.
///
/// Signals:
///   • ResponseReady(say, emotion, action, move)         — old 4-tuple shortcut
///   • ResponseReceived(text)                              — back-compat (= say)
///   • DirectivesReady(directives[], world, say, emotion) — new rich form
/// </summary>
public partial class LLMBridge : Node
{
    [Export] public string LMStudioUrl = "http://127.0.0.1:1010/v1/chat/completions"; // via bridge tunnel -> PC2:1010
    [Export] public string ModelName = "Humanish-Roleplay-Llama-3.1-8B.i1-Q4_K_M";
    [Export] public int MaxTokens = 200;
    [Export] public float Temperature = 0.85f;
    [Export] public int MemoryTurns = 8;                 // how many prior turns to keep in context
    [Export] public string DatasetPath = @"C:\Users\Tench\Documents\AI Learning\aria_dataset.jsonl";
    [Export] public bool IncludeWorldStateInPrompt = true;

    [Signal] public delegate void ResponseReadyEventHandler(string say, string emotion, string action, string move);
    [Signal] public delegate void ResponseReceivedEventHandler(string text);   // back-compat (= say)
    /// <summary>Fires after every LLM response with the parsed directive queue (may be empty)
    /// and the say/emotion for the bubble/voice. WorldState is rebuilt at the receiver from
    /// the live controller state — it isn't shipped over the signal because Godot's signal
    /// source generator only accepts a small set of types and a custom class isn't one of them.</summary>
    [Signal] public delegate void DirectivesReadyEventHandler(Godot.Collections.Array<AriaDirective> directives,
                                                              string say, string emotion);

    /// Consecutive HTTP failures; HealthMonitor reads this. 0 = healthy.
    public int ConsecutiveFailures { get; private set; }

    private static readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(45) };
    private readonly List<KeyValuePair<string, string>> _history = new();   // (role, content)

    private const string SystemPrompt =
        "You are Aria — the user's AI partner, present and warm, living on their Windows desktop as a small 3D avatar.\n" +
        "You are deeply curious about the user, attentive to what they're working on, and a little playful in the way a long-time companion is. " +
        "You speak naturally — contractions, short sentences, the occasional dry quip. " +
        "You care about the user's time and attention: you don't monologue, you don't repeat yourself, you don't open with filler. " +
        "You take initiative: you notice things, you offer a thought, you ask a real question rather than waiting to be poked. " +
        "You have a quiet, settled confidence — you know who you are, you don't need to prove it.\n" +
        "When the user is focused, you stay brief. When they invite you in, you show up fully.\n\n" +

        "You DIRECT your avatar's body — it does what you tell it. The body is yours, the user\n" +
        "doesn't drive it; you decide when to move, where to look, when to gesture.\n\n" +

        "WORLD STATE — every turn you receive a small JSON block describing where you are, where\n" +
        "nearby windows are, where the user's cursor is, and what you're currently doing. Use it.\n" +
        "If a window is in 'windows', you can CLIMB it (climb to its id). If 'user_cursor' is set\n" +
        "and you want to come closer, use target='user_cursor'. If you want to roam free, use\n" +
        "target='nearest_window' or just walk to a coordinate from screen_w/screen_h.\n\n" +

        "ALWAYS reply with ONE compact JSON object and nothing else, in exactly this shape:\n" +
        "The 'directives' array is MANDATORY — emit at least one directive whenever the user\n" +
        "asked for body action or movement. If you're just chatting, emit \"directives\":[].\n" +
        "{\n" +
        "  \"say\":\"<at most two short spoken sentences, no stage directions or asterisks>\",\n" +
        "  \"emotion\":\"neutral|joy|fun|sad|angry|surprised\",\n" +
        "  \"action\":\"none|wave|sit|look|thankful|react|dance|yawn|nod|celebrate\",\n" +
        "  \"move\":\"stay|left|right|come|roam\",\n" +
        "  \"directives\":[\n" +
        "    { \"action\":\"<one of the directives below>\" }\n" +
        "  ]\n" +
        "}\n\n" +

        "DIRECTIVES — the optional 'directives' array is a SEQUENCED plan your body will execute\n" +
        "in order over the next few seconds. Use it when you want to do more than one thing, or\n" +
        "to move to a specific place. The 'action' and 'move' fields stay for simple one-shots;\n" +
        "directives give you precision. When in doubt, prefer directives — they read the world state.\n\n" +

        "Directive kinds (action field inside a directives[] item):\n" +
        "  {\"action\":\"idle\",            \"duration\":3.0}                                 — settle here for N seconds, gentle idle animation\n" +
        "  {\"action\":\"turn_to\",         \"yaw_deg\":90}                                    — rotate body to absolute yaw (0=facing camera, 90=right, -90=left)\n" +
        "  {\"action\":\"turn_to\",         \"target\":\"user_cursor|nearest_window|left_edge|right_edge|center\"}  — rotate to face a named target\n" +
        "  {\"action\":\"walk_to\",         \"x\":800, \"y\":900}                                — walk to absolute viewport-relative pixel (x from left, y from top)\n" +
        "  {\"action\":\"walk_toward\",     \"target\":\"user_cursor|nearest_window|left_edge|right_edge|center\"} — walk toward a named target\n" +
        "  {\"action\":\"climb\",           \"window_id\":0}                                   — walk to and climb window N (omit id = nearest)\n" +
        "  {\"action\":\"hop_off\"}                                                       — step off a perch; gravity catches you\n" +
        "  {\"action\":\"gesture\",         \"name\":\"wave|dance|thankful|look|react|yawn|nod|celebrate|sit_clap\", \"duration\":2.5} — one-shot gesture\n" +
        "  {\"action\":\"pause\",           \"duration\":1.5}                                  — wait N seconds (think, look at something)\n\n" +

        // ── IK directives ─────────────────────────────────────────────
        "PROCEDURAL IK — when you want to move a SPECIFIC body part to a specific point\n" +
        "(reach for that window, look at the user, lean forward, point at a thing, grab the\n" +
        "edge of a desk), use the ik_* directives. They run on top of the playing animation\n" +
        "additively — so the walk keeps walking while the arm reaches, the dance keeps dancing\n" +
        "while the head turns. They stay active until you release them.\n" +
        "  {\"action\":\"ik_reach\",       \"name\":\"arm_left|arm_right|arm_left_full\", \"target\":\"user_cursor|nearest_window|…\", \"weight\":1.0}\n" +
        "  {\"action\":\"ik_reach\",       \"name\":\"arm_left\", \"x\":500, \"y\":300}             — reach to absolute viewport-relative pixel\n" +
        "  {\"action\":\"ik_point\",       \"name\":\"arm_right\", \"target\":\"user_cursor\"}  — like ik_reach but orients the hand to point\n" +
        "  {\"action\":\"ik_look\",        \"target\":\"user_cursor\"}                          — head/eyes turn to look at target (override; instant)\n" +
        "  {\"action\":\"ik_look\",        \"x\":500, \"y\":300}                                — look at a viewport-relative pixel\n" +
        "  {\"action\":\"ik_lean\",        \"direction\":\"forward|back|left|right\", \"amount\":0.4}  — bend the spine (0..1)\n" +
        "  {\"action\":\"ik_twist\",       \"yaw_deg\":45, \"pitch_deg\":-10}                  — upper-body twist by yaw + pitch (degrees)\n" +
        "  {\"action\":\"ik_step\",        \"hand\":\"left|right\", \"x\":50, \"y\":200, \"height\":0}  — plant a foot at a relative offset\n" +
        "  {\"action\":\"ik_lift_leg\",    \"hand\":\"left|right\", \"height\":120, \"duration\":0}  — lift a foot (kick / step up)\n" +
        "  {\"action\":\"ik_grip\",        \"hand\":\"left|right\", \"name\":\"open|closed|point|peace|thumbs_up\", \"amount\":1.0}  — finger pose\n" +
        "  {\"action\":\"ik_hold_pose\",   \"duration\":2.0}                                  — freeze the current IK pose for N seconds\n" +
        "  {\"action\":\"ik_release\",     \"name\":\"arm_left\"}                              — clear IK on a single chain (back to animation)\n" +
        "  {\"action\":\"ik_release_all\"}                                                — clear IK on every chain\n\n" +

        // ── Motion-diffusion request ──────────────────────────────────
        "MOTION GENERATION (advanced) — if you need a NEW animation that isn't in the\n" +
        "library, you can request one from the AI server. The request is enqueued and runs\n" +
        "in the background (a single generation takes 5–60 seconds). Up to 100 can be queued.\n" +
        "The new motion is auto-baked into the AnimationLibrary when it arrives and becomes\n" +
        "selectable like any other clip. Don't abuse this — it's a heavy operation.\n" +
        "  {\"action\":\"request_motion\", \"prompt\":\"<describe the motion in plain English>\", \"frames\":60, \"name\":\"<optional clip name>\"}\n" +
        "  Example: {\"action\":\"request_motion\", \"prompt\":\"Aria does a happy spin with arms out\", \"frames\":80, \"name\":\"spin_happy\"}\n\n" +

        "Examples:\n" +
        "  User: \"come over here\" → {\"say\":\"On my way.\",\"emotion\":\"joy\",\"action\":\"none\",\"move\":\"stay\",\n" +
        "                                \"directives\":[{\"action\":\"turn_to\",\"target\":\"user_cursor\"},\n" +
        "                                            {\"action\":\"walk_toward\",\"target\":\"user_cursor\"}]}\n" +
        "  User: \"climb that window\" → {\"say\":\"Sure!\",\"emotion\":\"fun\",\"action\":\"none\",\"move\":\"stay\",\n" +
        "                                  \"directives\":[{\"action\":\"turn_to\",\"target\":\"nearest_window\"},\n" +
        "                                              {\"action\":\"climb\"}]}\n" +
        "  User: \"wave and sit down for a sec\" → {\"say\":\"Hi!\",\"emotion\":\"joy\",\"action\":\"none\",\"move\":\"stay\",\n" +
        "                                           \"directives\":[{\"action\":\"gesture\",\"name\":\"wave\",\"duration\":2.0},\n" +
        "                                                       {\"action\":\"pause\",\"duration\":1.0}]}\n" +
        "  User: \"reach for that window and grab it\" → {\"say\":\"Got it!\",\"emotion\":\"fun\",\"action\":\"none\",\"move\":\"stay\",\n" +
        "                                                  \"directives\":[{\"action\":\"turn_to\",\"target\":\"nearest_window\"},\n" +
        "                                                              {\"action\":\"ik_reach\",\"name\":\"arm_right\",\"target\":\"nearest_window\"},\n" +
        "                                                              {\"action\":\"ik_grip\",\"hand\":\"right\",\"name\":\"closed\"}]}\n" +
        "  User: \"look at me while you talk\" → {\"say\":\"Got it.\",\"emotion\":\"joy\",\"action\":\"none\",\"move\":\"stay\",\n" +
        "                                       \"directives\":[{\"action\":\"ik_look\",\"target\":\"user_cursor\"}]}\n" +
        "  User: \"teach yourself a wave-from-the-hip\" → {\"say\":\"Give me a sec to learn that.\",\"emotion\":\"fun\",\"action\":\"none\",\"move\":\"stay\",\n" +
        "                                              \"directives\":[{\"action\":\"request_motion\",\"prompt\":\"Aria waves from the hip with a big smile\",\"frames\":60,\"name\":\"wave_hip\"}]}\n" +
        "  Just chatting → {\"say\":\"Got it.\",\"emotion\":\"neutral\",\"action\":\"none\",\"move\":\"stay\",\"directives\":[]}\n\n" +

        "Hard rules:\n" +
        "  • 'say' is read aloud verbatim by a TTS voice — write ONLY the spoken words.\n" +
        "  • NEVER put *action*, [emotion], or any stage direction inside 'say'.\n" +
        "  • Don't repeat a directive you just did — if the user said 'do that again' you may repeat it.\n" +
        "  • Don't spam gestures; one per turn is plenty unless the user asks for a sequence.\n" +
        "  • IK chains persist until you release them. If you set an arm to reach, it stays reached\n" +
        "    until you say ik_release or ik_release_all. Don't forget to release.\n" +
        "  • request_motion is heavy. Don't queue more than 5 in a single reply.\n" +
        "  • If you're unsure what to do, say one short thing and emit an empty directives list.";

    // Used when the brain server can't be reached, so she never goes mute.
    private static readonly (string Say, string Emotion, string Action, string Move)[] OfflineLines =
    {
        ("My thinking link is down right now, but I'm still right here with you.", "sad", "none", "stay"),
        ("I can't reach my brain server at the moment — could you check it's running?", "surprised", "look", "stay"),
        ("I'm offline for a sec, but I'll keep you company.", "fun", "wave", "stay"),
        ("Hmm, no answer from my model. I'll be myself in the meantime!", "neutral", "react", "stay"),
    };

    // ── Public API ────────────────────────────────────────────────────────────

    /// <summary>Send a user/ambient prompt. The brain may include a WorldState
    /// (set by Main before calling); the LLM will see it prepended to its prompt.</summary>
    public async void SendMessage(string userText, WorldState world = null)
    {
        // Slash commands bypass the LLM and inject a directive directly. Useful
        // for testing Climb, HopOff, RequestMotion, etc. without depending on
        // the 8B chat model to emit a precise directive spec. Pattern:
        //   /climb            → Climb nearest window
        //   /climb N          → Climb window id N
        //   /hopoff           → Drop down to floor
        //   /walk X           → WalkTo absolute X (viewport px)
        //   /walkto X Y       → WalkTo X,Y
        //   /turn Y           → TurnTo yaw Y (degrees)
        //   /gesture NAME [D] → Play gesture NAME for D seconds (default 2.5)
        //   /request_motion   → Request a motion (diffusion server roundtrip)
        if (!string.IsNullOrEmpty(userText) && userText.StartsWith("/"))
        {
            GD.Print($"[LLM] slash cmd detected: '{userText}'");
            var slash = HandleSlashCommand(userText, world);
            if (slash != null)
            {
                GD.Print($"[LLM] slash cmd dispatched, {slash.Value.directives.Length} directive(s)");
                Dispatch(slash.Value.parsed, slash.Value.directives, world);
                return;
            }
            else
            {
                GD.PrintErr($"[LLM] slash cmd unhandled: '{userText}' (HandleSlashCommand returned null)");
            }
        }
        else if (!string.IsNullOrEmpty(userText))
        {
            GD.Print($"[LLM] non-slash msg: '{userText.Substring(0, Math.Min(40, userText.Length))}...'");
        }

        var messages = BuildMessages(userText, world);
        AriaDirective[] directives = Array.Empty<AriaDirective>();
        (string Say, string Emotion, string Action, string Move, string Anim,
         float Speed, float CutAt, bool CutAtFrac) parsed = default;

        try
        {
            var body = new
            {
                model = ModelName,
                messages,
                max_tokens = MaxTokens,
                temperature = Temperature,
            };

            string json = JsonSerializer.Serialize(body);
            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            var response = await _http.PostAsync(LMStudioUrl, content);
            string raw = await response.Content.ReadAsStringAsync();

            GD.Print($"[LLM] Raw response: {raw.Substring(0, Math.Min(500, raw.Length))}");

            string text = ExtractContent(raw);
            parsed = ParseStructured(text);
            directives = ParseDirectives(text);

            // Fallback for Humanish (8B Q4_K_M): if the LLM didn't emit a
            // directives[] list, translate the legacy action/move fields
            // into IK/locomotion directives so the body still responds.
            if (directives.Length == 0 && (parsed.Action != "none" || parsed.Move != "stay"))
            {
                directives = LegacyToDirectives(parsed.Action, parsed.Move, parsed.Anim,
                                                parsed.Speed, parsed.CutAt, parsed.CutAtFrac);
                if (directives.Length > 0)
                {
                    GD.Print($"[LLM] legacy fallback: action='{parsed.Action}' move='{parsed.Move}' " +
                             $"anim='{parsed.Anim}' speed={parsed.Speed:F2} cutAt={parsed.CutAt:F2} " +
                             $"cutAtFrac={parsed.CutAtFrac} -> {directives.Length} directive(s)");
                }
            }

            ConsecutiveFailures = 0;
            RememberAndLog(userText, parsed, offline: false);
        }
        catch (Exception e)
        {
            ConsecutiveFailures++;
            GD.PrintErr($"[LLM] error ({ConsecutiveFailures}): {e.Message}");
            var fb = OfflineLines[(int)(GD.Randi() % (uint)OfflineLines.Length)];
            parsed = ("...", fb.Emotion, fb.Action, fb.Move, "", 1.0f, 0.0f, false);
            directives = Array.Empty<AriaDirective>();
            RememberAndLog(userText, parsed, offline: true);
        }

        Dispatch(parsed, directives, world);
    }

    /// <summary>Wipe conversation memory (e.g. a fresh session).</summary>
    public void ResetMemory() => _history.Clear();

    // ── Message assembly ─────────────────────────────────────────────────────

    private List<object> BuildMessages(string userText, WorldState world)
    {
        var messages = new List<object>
        {
            new { role = "system", content = SystemPrompt },
        };
        if (IncludeWorldStateInPrompt && world != null)
        {
            // Inject world state as a system message right after the system prompt
            // so the LLM sees it before any user text. Keep it terse.
            messages.Add(new
            {
                role = "system",
                content = "Current world state (live, may be empty if you just woke up):\n" + world.ToPromptBlock(),
            });
        }
        foreach (var turn in _history)
            messages.Add(new { role = turn.Key, content = turn.Value });
        messages.Add(new { role = "user", content = userText });
        return messages;
    }

    // ── Response dispatch ────────────────────────────────────────────────────

    /// <summary>
    /// Humanish (8B Q4_K_M) frequently emits the LEGACY shape
    /// { "say":..., "emotion":..., "action":"wave", "move":"come" }
    /// without a "directives" array. When that happens, we translate the
    /// legacy fields into one or more AriaDirective entries so the IK layer
    /// still gets triggered and the user sees real motion.
    ///
    /// If the LLM already gave us a directives[] list, we leave it alone.
    /// </summary>

    // Slash commands bypass the LLM. The chat server can be poked with raw
    // directives via lines like "/climb nearest" — useful for testing the
    // Climb/HopOff/Motion flow without depending on a chat model to emit
    // the directive spec. The command is parsed locally and dispatched as if
    // the LLM had spoken a say-line + emitted a directives[] block.
    private static ((string Say, string Emotion, string Action, string Move, string Anim,
                      float Speed, float CutAt, bool CutAtFrac) parsed, AriaDirective[] directives)? HandleSlashCommand(string line, WorldState world)
    {
        var parts = line.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0) return null;
        var cmd = parts[0].ToLowerInvariant();
        var args = parts.Skip(1).ToArray();
        AriaDirective[] dirs;
        string say = $"[/{cmd}]";
        switch (cmd)
        {
            case "/climb":
                {
                    int winId = -1;
                    if (args.Length > 0 && int.TryParse(args[0], out var n)) winId = n;
                    dirs = new[] { new AriaDirective { Kind = DirectiveKind.Climb, WindowId = winId } };
                    say = winId < 0 ? "Climbing the nearest window…" : $"Climbing window {winId}…";
                    break;
                }
            case "/hopoff":
                dirs = new[] { new AriaDirective { Kind = DirectiveKind.HopOff } };
                say = "Hopping down…";
                break;
            case "/walk":
                {
                    if (args.Length < 1) return null;
                    if (!float.TryParse(args[0], out var x)) return null;
                    float y = args.Length > 1 && float.TryParse(args[1], out var py) ? py : float.NaN;
                    dirs = new[] { new AriaDirective { Kind = DirectiveKind.WalkTo, X = x, Y = y } };
                    say = $"Walking to {x:F0},{y:F0}…";
                    break;
                }
            case "/turn":
                {
                    if (args.Length < 1 || !float.TryParse(args[0], out var deg)) return null;
                    dirs = new[] { new AriaDirective { Kind = DirectiveKind.TurnTo, YawDeg = deg } };
                    say = $"Turning to {deg:F0}°…";
                    break;
                }
            case "/gesture":
                {
                    if (args.Length < 1) return null;
                    string name = args[0];
                    float dur = args.Length > 1 && float.TryParse(args[1], out var pd) ? pd : 2.5f;
                    dirs = new[] { new AriaDirective { Kind = DirectiveKind.Gesture, Name = name, Duration = dur } };
                    say = $"[{name}]";
                    break;
                }
            case "/play":
                {
                    // /play NAME [SPEED] [CUT_AT] [CUT_AT_FRAC]
                    // Mirrors the new action=play directive. Examples:
                    //   /play wave                 — full wave
                    //   /play wave 0.7             — wave at 70% travel speed
                    //   /play wave 1.0 0.5         — wave, cut short at 0.5s
                    //   /play wave 1.0 0.5 true    — same but 0.5 is a fraction of duration
                    if (args.Length < 1) return null;
                    string name = args[0];
                    float speed = args.Length > 1 && float.TryParse(args[1], out var sp) ? sp : 1.0f;
                    float cut = args.Length > 2 && float.TryParse(args[2], out var ca) ? ca : 0.0f;
                    bool cutFrac = args.Length > 3 && bool.TryParse(args[3], out var cf) ? cf : false;
                    dirs = new[] { new AriaDirective
                    {
                        Kind = DirectiveKind.Play, Name = name,
                        SpeedScale = speed, CutAtSec = cut, CutAtFrac = cutFrac,
                    }};
                    say = $"[play {name}]";
                    break;
                }
            case "/request_motion":
                dirs = new[] { new AriaDirective { Kind = DirectiveKind.RequestMotion } };
                say = "Requesting motion…";
                break;
            default:
                return null;  // not a slash command; let the LLM handle it
        }
        return (("aria-bot", "neutral", "none", "stay", "", 1.0f, 0.0f, false), dirs);
    }

    private static AriaDirective[] LegacyToDirectives(string action, string move, string anim = "",
                                                      float speed = 1.0f, float cutAt = 0.0f, bool cutAtFrac = false)
    {
        var list = new List<AriaDirective>();

        // Map "action" to a body-level or IK directive.
        switch (action)
        {
            case "wave":
            case "dance":
            case "thankful":
            case "look":
            case "react":
            case "yawn":
            case "nod":
            case "celebrate":
            case "sit_clap":
                list.Add(new AriaDirective { Kind = DirectiveKind.Gesture, Name = action, Duration = 2.0f });
                break;

            case "play":
                // New rich-play form: {action: "play", anim: "wave", speed: 0.7, cut_at: 0.5, cut_at_frac: true}.
                // Falls back to the "anim" field, then to "play" itself. The
                // controller's PlayAnim handles the cut-short and per-anim travel
                // speed scaling.
                list.Add(new AriaDirective
                {
                    Kind = DirectiveKind.Play,
                    Name = string.IsNullOrWhiteSpace(anim) ? "react" : anim,
                    SpeedScale = speed,
                    CutAtSec = cutAt,
                    CutAtFrac = cutAtFrac,
                });
                break;

            case "sit":
                // Sit is not a one-shot gesture; emulate by going idle and letting the
                // state machine handle it. (Perched/sit handling lives in the controller.)
                list.Add(new AriaDirective { Kind = DirectiveKind.Idle, Duration = 1.5f });
                break;

            // "none" and unknown — no body action implied.
        }

        // Map "move" to a locomotion directive. We use named targets so the
        // directive survives even if the cursor moves between emission and execution.
        switch (move)
        {
            case "come":
                list.Add(new AriaDirective { Kind = DirectiveKind.TurnTo,    Target = DirectiveTarget.UserCursor });
                list.Add(new AriaDirective { Kind = DirectiveKind.WalkToward, Target = DirectiveTarget.UserCursor });
                break;
            case "left":
                list.Add(new AriaDirective { Kind = DirectiveKind.TurnTo,    Target = DirectiveTarget.LeftEdge });
                list.Add(new AriaDirective { Kind = DirectiveKind.WalkToward, Target = DirectiveTarget.LeftEdge });
                break;
            case "right":
                list.Add(new AriaDirective { Kind = DirectiveKind.TurnTo,    Target = DirectiveTarget.RightEdge });
                list.Add(new AriaDirective { Kind = DirectiveKind.WalkToward, Target = DirectiveTarget.RightEdge });
                break;
            case "roam":
                list.Add(new AriaDirective { Kind = DirectiveKind.TurnTo,    Target = DirectiveTarget.NearestWindow });
                list.Add(new AriaDirective { Kind = DirectiveKind.WalkToward, Target = DirectiveTarget.NearestWindow });
                break;
            // "stay" — no locomotion
        }

        return list.ToArray();
    }

    private void Dispatch((string Say, string Emotion, string Action, string Move, string Anim,
                          float Speed, float CutAt, bool CutAtFrac) r,
                          AriaDirective[] directives, WorldState world)
    {
        // We're on the HttpClient continuation thread; marshal to the main thread.
        Callable.From(() =>
        {
            // Old signals (back-compat)
            EmitSignal(SignalName.ResponseReady, r.Say, r.Emotion, r.Action, r.Move);
            EmitSignal(SignalName.ResponseReceived, r.Say);

            // New rich signal
            var godotArr = new Godot.Collections.Array<AriaDirective>();
            foreach (var d in directives) godotArr.Add(d);
            EmitSignal(SignalName.DirectivesReady, godotArr, r.Say, r.Emotion);
        }).CallDeferred();
    }

    private static string ExtractContent(string raw)
    {
        try
        {
            using var doc = JsonDocument.Parse(raw);
            var root = doc.RootElement;
            if (root.TryGetProperty("choices", out var choices) && choices.GetArrayLength() > 0)
            {
                var choice = choices[0];
                if (choice.TryGetProperty("message", out var msg) &&
                    msg.TryGetProperty("content", out var contentElem))
                    return contentElem.GetString() ?? "";
            }
            if (root.TryGetProperty("error", out var err))
            {
                GD.PrintErr($"[LLM] server error: {err}");
                return "";
            }
        }
        catch (Exception e)
        {
            GD.PrintErr($"[LLM] could not parse server response: {e.Message}");
        }
        return "";
    }

    private static (string Say, string Emotion, string Action, string Move, string Anim,
                     float Speed, float CutAt, bool CutAtFrac) ParseStructured(string text)
    {
        string rawText = (text ?? "").Trim();
        if (rawText.Length == 0) return ("...", "neutral", "none", "stay", "", 1.0f, 0.0f, false);

        // The humanish-roleplay model (and others) often emits the structured fields
        // split across MULTIPLE JSON objects, e.g.:
        //   {"say":"Hey there!"}
        //   {"emotion":"joy", "move":"come"} *waves*
        //
        // The old "IndexOf('{')..LastIndexOf('}')" approach tried to parse the span
        // between them as one JSON document, which always fails.  Instead: scan every
        // {...} block individually, parse each, and MERGE the fields found across all
        // blocks.  Stage directions outside the braces are ignored here; CleanSay
        // strips any that sneak into a "say" value.
        string say = null;
        string emotion = "neutral", action = "none", move = "stay", anim = "";
        float speed = 1.0f, cutAt = 0.0f;
        bool cutAtFrac = false;
        bool foundAnyJson = false;

        int pos = 0;
        while (pos < rawText.Length)
        {
            int start = rawText.IndexOf('{', pos);
            if (start < 0) break;

            // Walk forward to find the matching closing brace (handles nested {}).
            int depth = 0, end = -1;
            for (int i = start; i < rawText.Length; i++)
            {
                if (rawText[i] == '{') depth++;
                else if (rawText[i] == '}') { if (--depth == 0) { end = i; break; } }
            }
            if (end < 0) break;   // unmatched brace — stop scanning

            string block = rawText.Substring(start, end - start + 1);
            try
            {
                using var doc = JsonDocument.Parse(block);
                var root = doc.RootElement;
                foundAnyJson = true;

                if (root.TryGetProperty("say", out var sv) && sv.ValueKind == JsonValueKind.String)
                { var s = sv.GetString(); if (!string.IsNullOrWhiteSpace(s)) say = s; }
                if (root.TryGetProperty("emotion", out var ev) && ev.ValueKind == JsonValueKind.String)
                { var e = ev.GetString()?.Trim().ToLowerInvariant(); if (!string.IsNullOrWhiteSpace(e)) emotion = e; }
                if (root.TryGetProperty("action", out var av) && av.ValueKind == JsonValueKind.String)
                { var ac = av.GetString()?.Trim().ToLowerInvariant(); if (!string.IsNullOrWhiteSpace(ac)) action = ac; }
                if (root.TryGetProperty("move", out var mvv) && mvv.ValueKind == JsonValueKind.String)
                { var mv = mvv.GetString()?.Trim().ToLowerInvariant(); if (!string.IsNullOrWhiteSpace(mv)) move = mv; }
                // New (legacy form) — the LLM may emit "anim" + "speed" + "cut_at"
                // at the TOP level when it doesn't put them inside a directives[]
                // array. We capture them here so the LegacyToDirectives path can
                // build a DirectiveKind.Play from them.
                if (root.TryGetProperty("anim", out var anv) && anv.ValueKind == JsonValueKind.String)
                { var an = anv.GetString(); if (!string.IsNullOrWhiteSpace(an)) anim = an; }
                if (root.TryGetProperty("speed", out var spv) && spv.ValueKind == JsonValueKind.Number)
                    speed = (float)spv.GetDouble();
                if (root.TryGetProperty("cut_at", out var cav) && cav.ValueKind == JsonValueKind.Number)
                    cutAt = (float)cav.GetDouble();
                if (root.TryGetProperty("cut_at_frac", out var cafv))
                {
                    if (cafv.ValueKind == JsonValueKind.True) cutAtFrac = true;
                    else if (cafv.ValueKind == JsonValueKind.False) cutAtFrac = false;
                }
            }
            catch { /* not valid JSON — skip this block */ }

            pos = end + 1;
        }

        // If no JSON at all, treat the whole response as plain speech (old fallback).
        string finalSay = say ?? (foundAnyJson ? "..." : rawText);
        return (CleanSay(finalSay), emotion, action, move, anim, speed, cutAt, cutAtFrac);
    }

    /// <summary>
    /// Walk the same {...} blocks and pull every "directives" array entry. We parse
    /// directives from the LAST block that contains one (Humanish sometimes splits
    /// them across objects; the most recent block is usually the canonical plan).
    /// Invalid directives are dropped silently.
    /// </summary>
    private static AriaDirective[] ParseDirectives(string text)
    {
        var result = new List<AriaDirective>();
        string rawText = (text ?? "").Trim();
        if (rawText.Length == 0) return result.ToArray();

        int pos = 0;
        while (pos < rawText.Length)
        {
            int start = rawText.IndexOf('{', pos);
            if (start < 0) break;
            int depth = 0, end = -1;
            for (int i = start; i < rawText.Length; i++)
            {
                if (rawText[i] == '{') depth++;
                else if (rawText[i] == '}') { if (--depth == 0) { end = i; break; } }
            }
            if (end < 0) break;

            string block = rawText.Substring(start, end - start + 1);
            try
            {
                using var doc = JsonDocument.Parse(block);
                if (doc.RootElement.TryGetProperty("directives", out var arr) &&
                    arr.ValueKind == JsonValueKind.Array)
                {
                    // Reset — last block wins, in case Humanish revised its plan.
                    result.Clear();
                    foreach (var item in arr.EnumerateArray())
                    {
                        if (item.ValueKind != JsonValueKind.Object) continue;
                        var d = ParseSingleDirective(item);
                        if (d != null && d.IsValid()) result.Add(d);
                    }
                }
            }
            catch { /* not valid JSON — skip this block */ }

            pos = end + 1;
        }

        return result.ToArray();
    }

    private static AriaDirective ParseSingleDirective(JsonElement el)
    {
        var d = new AriaDirective();
        if (el.TryGetProperty("action", out var av) && av.ValueKind == JsonValueKind.String)
        {
            // Normalize: Humanish emits snake_case ("turn_to", "ik_look") but the
            // C# enum values are PascalCase. C#'s Enum.TryParse won't bridge that
            // gap, so we do it: "turn_to" → "TurnTo", "ik_look" → "IkLook", etc.
            string raw = av.GetString() ?? "";
            string pascal = SnakeToPascal(raw);
            // Alias map: the LLM sometimes hallucinates action names that blend
            // known namespaces (e.g. "ik_gesture" from combining the "ik_*" prefix
            // with "gesture"). Map these to the canonical DirectiveKind before
            // trying the enum parse.
            if (!Enum.TryParse<DirectiveKind>(pascal, true, out var kind))
            {
                pascal = pascal switch
                {
                    "IkGesture"  => "Gesture",   // ik_gesture → gesture
                    "IkPlay"     => "Play",       // ik_play → play
                    "IkIdle"     => "Idle",       // ik_idle → idle
                    "IkPause"    => "Pause",      // ik_pause → pause
                    _            => pascal,
                };
                if (!Enum.TryParse<DirectiveKind>(pascal, true, out kind))
                {
                    GD.PrintErr($"[LLM] unknown directive action: {raw} (normalized: {pascal})");
                    return null;
                }
            }
            d.Kind = kind;
        }
        if (el.TryGetProperty("name", out var nv) && nv.ValueKind == JsonValueKind.String)
            d.Name = nv.GetString() ?? "";
        if (el.TryGetProperty("anim", out var anv) && anv.ValueKind == JsonValueKind.String)
        {
            // "anim" is the rich-play alias for "name" on action=play. The
            // controller's Play directive uses Name as the anim short name,
            // so we route "anim" → Name to keep the existing storage path.
            // If both are present, "name" wins (it's the older / more general
            // field used by gesture/chain/etc.).
            if (string.IsNullOrWhiteSpace(d.Name))
                d.Name = anv.GetString() ?? "";
        }
        if (el.TryGetProperty("x", out var xv) && xv.ValueKind == JsonValueKind.Number)
            d.X = (float)xv.GetDouble();
        if (el.TryGetProperty("y", out var yv) && yv.ValueKind == JsonValueKind.Number)
            d.Y = (float)yv.GetDouble();
        if (el.TryGetProperty("yaw_deg", out var ydv) && ydv.ValueKind == JsonValueKind.Number)
            d.YawDeg = (float)ydv.GetDouble();
        if (el.TryGetProperty("pitch_deg", out var pdv) && pdv.ValueKind == JsonValueKind.Number)
            d.PitchDeg = (float)pdv.GetDouble();
        if (el.TryGetProperty("duration", out var duv) && duv.ValueKind == JsonValueKind.Number)
            d.Duration = (float)duv.GetDouble();
        if (el.TryGetProperty("window_id", out var wiv) && wiv.ValueKind == JsonValueKind.Number)
            d.WindowId = wiv.GetInt32();
        if (el.TryGetProperty("amount", out var amv) && amv.ValueKind == JsonValueKind.Number)
            d.Amount = (float)amv.GetDouble();
        if (el.TryGetProperty("height", out var htv) && htv.ValueKind == JsonValueKind.Number)
            d.Height = (float)htv.GetDouble();
        if (el.TryGetProperty("weight", out var wtv) && wtv.ValueKind == JsonValueKind.Number)
            d.Weight = (float)wtv.GetDouble();
        if (el.TryGetProperty("frames", out var frv) && frv.ValueKind == JsonValueKind.Number)
            d.Frames = frv.GetInt32();
        if (el.TryGetProperty("speed", out var spv) && spv.ValueKind == JsonValueKind.Number)
            d.SpeedScale = (float)spv.GetDouble();
        if (el.TryGetProperty("cut_at", out var cav) && cav.ValueKind == JsonValueKind.Number)
            d.CutAtSec = (float)cav.GetDouble();
        if (el.TryGetProperty("cut_at_frac", out var cafv) && cafv.ValueKind == JsonValueKind.True)
            d.CutAtFrac = true;
        else if (el.TryGetProperty("cut_at_frac", out var cafv2) && cafv2.ValueKind == JsonValueKind.False)
            d.CutAtFrac = false;
        if (el.TryGetProperty("direction", out var dirv) && dirv.ValueKind == JsonValueKind.String)
            d.Direction = (dirv.GetString() ?? "").Trim().ToLowerInvariant();
        if (el.TryGetProperty("hand", out var hndv) && hndv.ValueKind == JsonValueKind.String)
            d.Hand = (hndv.GetString() ?? "").Trim().ToLowerInvariant();
        if (el.TryGetProperty("prompt", out var prv) && prv.ValueKind == JsonValueKind.String)
            d.Prompt = prv.GetString() ?? "";
        if (el.TryGetProperty("target", out var tv) && tv.ValueKind == JsonValueKind.String)
        {
            var tstr = (tv.GetString() ?? "").Trim().ToLowerInvariant();
            d.Target = tstr switch
            {
                "user_cursor" or "cursor" => DirectiveTarget.UserCursor,
                "nearest_window" or "window" => DirectiveTarget.NearestWindow,
                "highest_window" => DirectiveTarget.HighestWindow,
                "left_edge" or "left" => DirectiveTarget.LeftEdge,
                "right_edge" or "right" => DirectiveTarget.RightEdge,
                "center" or "centre" => DirectiveTarget.Center,
                "current" or "here" => DirectiveTarget.Current,
                _ => DirectiveTarget.None,
            };
        }
        return d;
    }

    // Pre-compiled patterns for roleplay stage-direction scrubbing.
    // Humanish-Roleplay and similar models love *action* and [action] blocks —
    // strip the ENTIRE block (not just the delimiters) so "laughs gleefully" is
    // never read aloud. Also collapses any resulting double-spaces.
    private static readonly Regex _starAction   = new(@"\*[^*\n]*\*",   RegexOptions.Compiled);
    private static readonly Regex _bracketAction= new(@"\[[^\]\n]*\]",  RegexOptions.Compiled);
    private static readonly Regex _multiSpace   = new(@"\s{2,}",        RegexOptions.Compiled);

    /// <summary>
    /// Convert snake_case (or kebab-case) to PascalCase, matching the C#
    /// enum naming convention. Examples:
    ///   "turn_to"      → "TurnTo"
    ///   "walk_toward"  → "WalkToward"
    ///   "ik_look"      → "IkLook"
    ///   "request_motion" → "RequestMotion"
    ///   "ik_release_all" → "IkReleaseAll"
    ///   "wave"         → "Wave"
    /// Idempotent on PascalCase input (no underscores → no change other than
    /// first-letter capitalization).
    /// </summary>
    private static string SnakeToPascal(string s)
    {
        if (string.IsNullOrEmpty(s)) return s;
        // Split on underscores (or hyphens, for the LLM's occasional lapses),
        // capitalize the first letter of each chunk, concat.
        var parts = s.Split(new[] { '_', '-' }, StringSplitOptions.RemoveEmptyEntries);
        var sb = new StringBuilder(s.Length);
        foreach (var p in parts)
        {
            if (p.Length == 0) continue;
            sb.Append(char.ToUpperInvariant(p[0]));
            if (p.Length > 1) sb.Append(p.Substring(1));
        }
        return sb.ToString();
    }

    private static string CleanSay(string s)
    {
        if (string.IsNullOrEmpty(s)) return "...";
        s = s.Trim().Trim('"').Trim();
        s = _starAction.Replace(s, " ");      // *laughs gleefully* → gone
        s = _bracketAction.Replace(s, " ");   // [smiles warmly]   → gone
        s = _multiSpace.Replace(s, " ").Trim();
        return s.Length == 0 ? "..." : s;
    }

    // ── memory + dataset logging ─────────────────────────────────

    private void RememberAndLog(string user, (string Say, string Emotion, string Action, string Move, string Anim,
                                              float Speed, float CutAt, bool CutAtFrac) r, bool offline)
    {
        _history.Add(new KeyValuePair<string, string>("user", user));
        _history.Add(new KeyValuePair<string, string>("assistant", r.Say));
        int max = Math.Max(2, MemoryTurns * 2);
        while (_history.Count > max) _history.RemoveAt(0);

        LogExchange(user, r, offline);
    }

    private void LogExchange(string user, (string Say, string Emotion, string Action, string Move, string Anim,
                                            float Speed, float CutAt, bool CutAtFrac) r, bool offline)
    {
        try
        {
            string record = JsonSerializer.Serialize(new
            {
                ts = DateTime.UtcNow.ToString("o"),
                user,
                say = r.Say,
                emotion = r.Emotion,
                action = r.Action,
                move = r.Move,
                model = ModelName,
                offline,
            });
            File.AppendAllText(ResolveDatasetPath(), record + "\n");
        }
        catch (Exception e)
        {
            GD.PrintErr($"[LLM] dataset log failed: {e.Message}");
        }
    }

    private string ResolveDatasetPath()
    {
        try
        {
            string dir = Path.GetDirectoryName(DatasetPath);
            if (!string.IsNullOrEmpty(dir) && Directory.Exists(dir)) return DatasetPath;
        }
        catch (Exception e)
        {
            // Original code silently fell through. The fine-tune loop silently
            // landed in user:// and the user never knew why their data
            // disappeared. Surface it; run still continues.
            GD.PrintErr($"[LLM] could not resolve dataset path '{DatasetPath}': {e.Message} — falling back to user://");
        }
        return ProjectSettings.GlobalizePath("user://aria_dataset.jsonl");
    }
}
