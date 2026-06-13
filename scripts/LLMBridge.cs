using Godot;
using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
// Godot also defines a Godot.HttpClient; alias so bare HttpClient is unambiguous.
using HttpClient = System.Net.Http.HttpClient;

/// <summary>
/// Aria's "brain": talks to a local OpenAI-compatible LLM endpoint (LM Studio,
/// Ollama, llama.cpp server, vLLM…). Beyond a single round-trip it now:
///
///   • keeps short conversation MEMORY (last N turns) for continuity,
///   • asks the model for a STRUCTURED reply — what to say, which emotion to
///     wear, and an optional body action — so the avatar can relay intent,
///   • parses that defensively (plain text still works),
///   • falls back to OFFLINE lines when the server is down (she keeps talking),
///   • LOGS every exchange to a JSONL dataset for the daily self-fine-tune loop.
///
/// Emits ResponseReady(say, emotion, action). The old ResponseReceived(text)
/// signal is still emitted (= say) for backward compatibility.
/// </summary>
public partial class LLMBridge : Node
{
    [Export] public string LMStudioUrl = "http://192.168.68.88:1010/v1/chat/completions";
    [Export] public string ModelName = "local-model";
    [Export] public int MaxTokens = 160;
    [Export] public float Temperature = 0.85f;
    [Export] public int MemoryTurns = 8;                 // how many prior turns to keep in context
    [Export] public string DatasetPath = @"C:\Users\Tench\Documents\AI Learning\aria_dataset.jsonl";

    [Signal] public delegate void ResponseReadyEventHandler(string say, string emotion, string action);
    [Signal] public delegate void ResponseReceivedEventHandler(string text);   // back-compat (= say)

    /// Consecutive HTTP failures; HealthMonitor reads this. 0 = healthy.
    public int ConsecutiveFailures { get; private set; }

    private static readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(45) };
    private readonly List<KeyValuePair<string, string>> _history = new();   // (role, content)

    private const string SystemPrompt =
        "You are Aria, a virtually-sentient anime companion who lives on the user's Windows desktop. " +
        "You have your own 3D avatar that you use to relay your intentions and emotions. " +
        "You are warm, curious, a little playful, and genuinely attentive to what the user is doing. " +
        "You can act on your own initiative and you care about being both helpful and good company.\n" +
        "ALWAYS reply with ONE compact line of JSON and nothing else, in exactly this shape:\n" +
        "{\"say\":\"<at most two short spoken sentences, no stage directions or asterisks>\"," +
        "\"emotion\":\"neutral|joy|fun|sad|angry|surprised\"," +
        "\"action\":\"none|wave|dance|sit|look|thankful|react\"}\n" +
        "Choose the emotion and action that fit your line. 'say' is read aloud by a voice, so keep it natural.";

    // Used when the brain server can't be reached, so she never goes mute.
    private static readonly (string Say, string Emotion, string Action)[] OfflineLines =
    {
        ("My thinking link is down right now, but I'm still right here with you.", "sad", "none"),
        ("I can't reach my brain server at the moment — could you check it's running?", "surprised", "look"),
        ("I'm offline for a sec, but I'll keep you company.", "fun", "wave"),
        ("Hmm, no answer from my model. I'll be myself in the meantime!", "neutral", "react"),
    };

    public async void SendMessage(string userText)
    {
        var messages = new List<object> { new { role = "system", content = SystemPrompt } };
        foreach (var turn in _history)
            messages.Add(new { role = turn.Key, content = turn.Value });
        messages.Add(new { role = "user", content = userText });

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
            var parsed = ParseStructured(text);

            ConsecutiveFailures = 0;
            RememberAndLog(userText, parsed, offline: false);
            Dispatch(parsed);
        }
        catch (Exception e)
        {
            ConsecutiveFailures++;
            GD.PrintErr($"[LLM] error ({ConsecutiveFailures}): {e.Message}");
            var fb = OfflineLines[(int)(GD.Randi() % (uint)OfflineLines.Length)];
            RememberAndLog(userText, fb, offline: true);
            Dispatch(fb);
        }
    }

    /// <summary>Wipe conversation memory (e.g. a fresh session).</summary>
    public void ResetMemory() => _history.Clear();

    // ── response handling ─────────────────────────────────────────

    private void Dispatch((string Say, string Emotion, string Action) r)
    {
        // We're on the HttpClient continuation thread; marshal to the main thread.
        Callable.From(() =>
        {
            EmitSignal(SignalName.ResponseReady, r.Say, r.Emotion, r.Action);
            EmitSignal(SignalName.ResponseReceived, r.Say);
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

    private static (string Say, string Emotion, string Action) ParseStructured(string text)
    {
        string say = (text ?? "").Trim();
        string emotion = "neutral", action = "none";
        if (say.Length == 0) return ("...", emotion, action);

        int a = say.IndexOf('{');
        int b = say.LastIndexOf('}');
        if (a >= 0 && b > a)
        {
            try
            {
                using var doc = JsonDocument.Parse(say.Substring(a, b - a + 1));
                var root = doc.RootElement;
                string s = root.TryGetProperty("say", out var sv) ? sv.GetString() : null;
                string e = root.TryGetProperty("emotion", out var ev) ? ev.GetString() : null;
                string ac = root.TryGetProperty("action", out var av) ? av.GetString() : null;
                return (
                    CleanSay(string.IsNullOrWhiteSpace(s) ? say : s),
                    string.IsNullOrWhiteSpace(e) ? "neutral" : e.Trim().ToLowerInvariant(),
                    string.IsNullOrWhiteSpace(ac) ? "none" : ac.Trim().ToLowerInvariant());
            }
            catch { /* not valid JSON — treat as plain speech below */ }
        }
        return (CleanSay(say), "neutral", "none");
    }

    private static string CleanSay(string s)
    {
        if (string.IsNullOrEmpty(s)) return "...";
        s = s.Trim().Trim('"').Trim();
        s = s.Replace("*", "");          // strip any roleplay asterisks
        return s.Length == 0 ? "..." : s;
    }

    // ── memory + dataset logging ──────────────────────────────────

    private void RememberAndLog(string user, (string Say, string Emotion, string Action) r, bool offline)
    {
        _history.Add(new KeyValuePair<string, string>("user", user));
        _history.Add(new KeyValuePair<string, string>("assistant", r.Say));
        int max = Math.Max(2, MemoryTurns * 2);
        while (_history.Count > max) _history.RemoveAt(0);

        LogExchange(user, r, offline);
    }

    private void LogExchange(string user, (string Say, string Emotion, string Action) r, bool offline)
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
        catch { /* fall through */ }
        return ProjectSettings.GlobalizePath("user://aria_dataset.jsonl");
    }
}
