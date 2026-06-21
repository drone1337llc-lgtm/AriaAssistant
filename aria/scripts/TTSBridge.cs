using Godot;
using System;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
// Godot also defines a Godot.HttpClient; alias so bare HttpClient is unambiguous.
using HttpClient = System.Net.Http.HttpClient;

/// <summary>
/// Gives Aria a voice. Sends her spoken line to a local Coqui XTTS-v2 server,
/// receives a WAV, and plays it through an AudioStreamPlayer. Emits
/// SpeechStarted / SpeechFinished so the face can flap her mouth in time.
///
/// Two server contracts are supported (set in the Inspector):
///   • GET  (default) — Coqui's bundled `tts-server`:
///       GET {TtsUrl}?text=...&speaker_id=...&language_id=...
///       Start it with:  python -m TTS.server.server \
///           --model_name tts_models/multilingual/multi-dataset/xtts_v2
///       (defaults to http://127.0.0.1:5002/api/tts)
///   • POST (UseJsonPost = true) — for a custom XTTS wrapper that accepts JSON:
///       POST {TtsUrl}  body: {"text": "...", "speaker": "...", "language": "..."}
///       returning audio/wav bytes.
///
/// Everything is wrapped so a missing/most-likely-not-running server never
/// breaks the app — it just logs and Aria stays silent until it's up.
/// </summary>
public partial class TTSBridge : Node
{
    [Export] public bool Enabled = true;
    [Export] public string TtsUrl = "http://127.0.0.1:5003/tts"; // Jessica XTTS server (via bridge tunnel -> PC2:5003)
    [Export] public bool UseJsonPost = false;
    [Export] public string Speaker = "Ana Florence";   // XTTS built-in speaker, or your cloned voice id
    [Export] public string Language = "en";
    [Export(PropertyHint.Range, "0,1,0.01")] public float Volume = 1.0f;

    // Spoken-only pronunciation fixes. The text sent to the voice model is rewritten
    // by these (whole-word, case-insensitive); the on-screen bubble keeps the original
    // spelling. Tune by ear in the Inspector. Default corrects her name: the model read
    // "Aria" as "air-ria", so we feed it "Arria" to get "arr-ree-a".
    [Export] public Godot.Collections.Dictionary<string, string> PronunciationMap = new()
    {
        { "Aria", "Arria" },
    };

    [Signal] public delegate void SpeechStartedEventHandler();
    [Signal] public delegate void SpeechFinishedEventHandler();

    private static readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(60) };
    private AudioStreamPlayer _player;

    public override void _Ready()
    {
        _player = new AudioStreamPlayer { VolumeDb = Mathf.LinearToDb(Mathf.Clamp(Volume, 0.0001f, 1f)) };
        AddChild(_player);
        _player.Finished += () => EmitSignal(SignalName.SpeechFinished);
    }

    /// <summary>Speak a line. Safe to call from anywhere; no-op if disabled/empty.</summary>
    public async void Speak(string text)
    {
        if (!Enabled || string.IsNullOrWhiteSpace(text))
        {
            FinishDeferred();
            return;
        }

        string spoken = ApplyPronunciation(text);
        try
        {
            byte[] bytes = UseJsonPost ? await PostAsync(spoken) : await GetAsync(spoken);
            Callable.From(() => PlayWavBytes(bytes)).CallDeferred();
        }
        catch (Exception e)
        {
            GD.PrintErr($"[TTS] synthesis failed ({e.Message}). Is the Coqui server running at {TtsUrl}?");
            FinishDeferred();
        }
    }

    public void Stop()
    {
        if (_player != null && _player.Playing) _player.Stop();
    }

    /// <summary>Rewrite spoken text per PronunciationMap (whole-word, case-insensitive).</summary>
    private string ApplyPronunciation(string text)
    {
        if (string.IsNullOrEmpty(text)) return text;
        // Strip *action*/emote cues (e.g. "*grins*", "*leans in*") so TTS speaks
        // only the words, not the stage directions. Done before the map so it
        // always applies, even when PronunciationMap is empty.
        text = System.Text.RegularExpressions.Regex.Replace(text, @"\*[^*]*\*", " ");
        text = System.Text.RegularExpressions.Regex.Replace(text, @"\s+", " ").Trim();
        if (PronunciationMap == null || PronunciationMap.Count == 0)
            return text;
        foreach (var kv in PronunciationMap)
        {
            if (string.IsNullOrEmpty(kv.Key)) continue;
            string replacement = kv.Value;   // captured per-iteration; MatchEvaluator avoids $-substitution
            text = System.Text.RegularExpressions.Regex.Replace(
                text,
                $@"\b{System.Text.RegularExpressions.Regex.Escape(kv.Key)}\b",
                _ => replacement,
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        }
        return text;
    }

    private async Task<byte[]> GetAsync(string text)
    {
        var sb = new StringBuilder(TtsUrl);
        sb.Append("?text=").Append(Uri.EscapeDataString(text));
        if (!string.IsNullOrEmpty(Speaker))  sb.Append("&speaker_id=").Append(Uri.EscapeDataString(Speaker));
        if (!string.IsNullOrEmpty(Language)) sb.Append("&language_id=").Append(Uri.EscapeDataString(Language));
        return await _http.GetByteArrayAsync(sb.ToString());
    }

    private async Task<byte[]> PostAsync(string text)
    {
        string body = System.Text.Json.JsonSerializer.Serialize(new
        {
            text,
            speaker = Speaker,
            language = Language,
        });
        using var content = new StringContent(body, Encoding.UTF8, "application/json");
        var resp = await _http.PostAsync(TtsUrl, content);
        return await resp.Content.ReadAsByteArrayAsync();
    }

    // Runs on the main thread (scheduled via Callable.CallDeferred).
    private void PlayWavBytes(byte[] data)
    {
        var stream = WavToStream(data);
        if (stream == null)
        {
            GD.PrintErr("[TTS] could not decode WAV response (expected 8/16-bit PCM RIFF).");
            EmitSignal(SignalName.SpeechFinished);
            return;
        }
        _player.Stream = stream;
        _player.Play();
        EmitSignal(SignalName.SpeechStarted);
    }

    private void FinishDeferred() => Callable.From(() => EmitSignal(SignalName.SpeechFinished)).CallDeferred();

    /// <summary>Decode a PCM RIFF/WAVE byte buffer into an AudioStreamWav.</summary>
    private static AudioStreamWav WavToStream(byte[] b)
    {
        if (b == null || b.Length < 44) return null;
        if (Ascii(b, 0, 4) != "RIFF" || Ascii(b, 8, 4) != "WAVE") return null;

        int sampleRate = 24000, channels = 1, bits = 16;
        byte[] pcm = null;

        int pos = 12;
        while (pos + 8 <= b.Length)
        {
            string id = Ascii(b, pos, 4);
            uint size = BitConverter.ToUInt32(b, pos + 4);
            int body = pos + 8;
            if (body > b.Length) break;

            if (id == "fmt " && body + 16 <= b.Length)
            {
                channels   = BitConverter.ToUInt16(b, body + 2);
                sampleRate = (int)BitConverter.ToUInt32(b, body + 4);
                bits       = BitConverter.ToUInt16(b, body + 14);
            }
            else if (id == "data")
            {
                int len = (int)Math.Min(size, (uint)(b.Length - body));
                if (len <= 0) return null;
                pcm = new byte[len];
                Array.Copy(b, body, pcm, 0, len);
            }

            // chunks are word-aligned (pad to even length)
            long next = (long)body + size + (size % 2 == 1 ? 1 : 0);
            if (next <= pos) break;
            pos = (int)next;
        }

        if (pcm == null) return null;

        return new AudioStreamWav
        {
            Format   = bits == 8 ? AudioStreamWav.FormatEnum.Format8Bits : AudioStreamWav.FormatEnum.Format16Bits,
            MixRate  = sampleRate,
            Stereo   = channels == 2,
            LoopMode = AudioStreamWav.LoopModeEnum.Disabled,
            Data     = pcm,
        };
    }

    private static string Ascii(byte[] b, int off, int len) =>
        Encoding.ASCII.GetString(b, off, Math.Min(len, b.Length - off));
}
