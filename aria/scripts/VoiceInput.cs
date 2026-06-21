using Godot;
using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;

/// <summary>
/// Streaming voice client for Aria. Connects to the brain's `WS /voice-stream`
/// and gives her a fast, interruptible spoken conversation:
///
///   • PUSH-TO-TALK (a mouse side-button): press = barge-in (stop her talking) +
///     start capturing the mic; release = send the turn. Same button starts a new
///     thought or interrupts her — exactly one control.
///   • Mic is captured via an AudioEffectCapture bus, downsampled to 16 kHz PCM16,
///     and streamed up only while the button is held (so a Bluetooth headset never
///     gets stuck in the low-quality mic profile).
///   • Aria's reply streams back as raw PCM16 @ 24 kHz and is played through an
///     AudioStreamGenerator the instant the first chunk arrives — she starts
///     speaking ~one sentence after you let go, not after the whole reply.
///
/// Wire protocol (matches brain/server.py /voice-stream):
///   client → brain : {"type":"ptt_down"} · &lt;binary PCM16 16k&gt; · {"type":"ptt_up"}
///   brain  → client: {"type":"cancel"|"transcript"|"sentence"|"done", ...} · &lt;binary PCM16 24k&gt;
///
/// NOTE: this is the one piece that needs in-editor testing — audio bus setup,
/// resampling, and the WebSocket frame handling can't be verified outside Godot.
/// The most likely tuning spots are flagged with TODO.
/// </summary>
public partial class VoiceInput : Node
{
    [Export] public bool Enabled = true;
    // Brain voice WS — through the bridge tunnel this is the local mapped port.
    [Export] public string BrainWsUrl = "ws://127.0.0.1:8770/voice-stream";
    // Which mouse side-button is push-to-talk. Godot maps thumb buttons to
    // Xbutton1 (usually "back") and Xbutton2 ("forward").
    [Export] public MouseButton PttButton = MouseButton.Xbutton1;
    [Export] public string MicBus = "AriaRecord";
    [Export] public int MicSendRate = 16000;     // what the brain's STT expects
    [Export] public int PlaybackRate = 24000;    // what the TTS server emits

    // Optional: her existing batch-TTS voice (directive/text-chat speech). We stop
    // it on PTT so streamed voice and batch voice never talk over each other.
    [Export] public NodePath TtsBridgePath;

    [Signal] public delegate void TranscriptEventHandler(string text);   // what the user said
    [Signal] public delegate void AriaSentenceEventHandler(string text); // a line she's speaking

    private WebSocketPeer _ws;
    private bool _wsOpen;

    // Mic capture
    private AudioStreamPlayer _micPlayer;
    private AudioEffectCapture _capture;
    private double _micMixRate = 44100.0;
    private double _resampPhase;                 // fractional read position for downsampling

    // Playback (generator)
    private AudioStreamPlayer _outPlayer;
    private AudioStreamGeneratorPlayback _genPlayback;
    private readonly Queue<float> _outSamples = new();  // decoded 24k mono samples awaiting push
    private int _pcmCarry = -1;                          // odd leftover byte across binary frames

    private bool _capturing;
    private Node _ttsBridge;

    public override void _Ready()
    {
        if (!Enabled) { SetProcess(false); SetProcessInput(false); return; }

        SetupMicBus();
        SetupPlayback();
        ConnectWs();

        if (TtsBridgePath != null && !TtsBridgePath.IsEmpty)
            _ttsBridge = GetNodeOrNull(TtsBridgePath);

        GD.Print($"[Voice] streaming client ready. PTT={PttButton}, ws={BrainWsUrl}");
    }

    // ── Setup ──────────────────────────────────────────────────────────────

    private void SetupMicBus()
    {
        int bus = AudioServer.GetBusIndex(MicBus);
        if (bus == -1)
        {
            AudioServer.AddBus();
            bus = AudioServer.BusCount - 1;
            AudioServer.SetBusName(bus, MicBus);
            AudioServer.AddBusEffect(bus, new AudioEffectCapture());
            AudioServer.SetBusMute(bus, true);   // capture the signal, don't echo it to speakers
        }
        _capture = AudioServer.GetBusEffect(bus, 0) as AudioEffectCapture;
        _micMixRate = AudioServer.GetMixRate();

        _micPlayer = new AudioStreamPlayer { Stream = new AudioStreamMicrophone(), Bus = MicBus };
        AddChild(_micPlayer);
        _micPlayer.Play();   // mic runs continuously; we only READ the buffer while capturing
        if (_capture == null)
            GD.PrintErr("[Voice] mic capture effect missing — mic input won't work");
    }

    private void SetupPlayback()
    {
        var gen = new AudioStreamGenerator { MixRate = PlaybackRate, BufferLength = 0.5f };
        _outPlayer = new AudioStreamPlayer { Stream = gen };
        AddChild(_outPlayer);
        _outPlayer.Play();
        _genPlayback = _outPlayer.GetStreamPlayback() as AudioStreamGeneratorPlayback;
        if (_genPlayback == null)
            GD.PrintErr("[Voice] could not get generator playback — Aria's streamed voice won't play");
    }

    private void ConnectWs()
    {
        _ws = new WebSocketPeer();
        Error err = _ws.ConnectToUrl(BrainWsUrl);
        if (err != Error.Ok)
            GD.PrintErr($"[Voice] ws connect failed: {err}");
    }

    // ── Input: push-to-talk ─────────────────────────────────────────────────

    public override void _Input(InputEvent ev)
    {
        if (!Enabled) return;
        if (ev is InputEventMouseButton mb && mb.ButtonIndex == PttButton)
        {
            if (mb.Pressed) OnPttDown();
            else OnPttUp();
        }
    }

    private void OnPttDown()
    {
        // Barge-in: stop whatever she's saying right now, locally and on the server.
        StopPlayback();
        (_ttsBridge as dynamic)?.Stop();   // also halt batch-TTS if it's mid-line
        SendJson("{\"type\":\"ptt_down\"}");
        // Flush any stale mic frames so the turn starts clean.
        if (_capture != null) _capture.ClearBuffer();
        _resampPhase = 0;
        _capturing = true;
        GD.Print("[Voice] PTT down — listening");
    }

    private void OnPttUp()
    {
        if (!_capturing) return;
        _capturing = false;
        SendJson("{\"type\":\"ptt_up\"}");
        GD.Print("[Voice] PTT up — sent");
    }

    // ── Per-frame pump ───────────────────────────────────────────────────────

    public override void _Process(double delta)
    {
        if (!Enabled || _ws == null) return;
        _ws.Poll();
        var st = _ws.GetReadyState();
        if (st == WebSocketPeer.State.Open)
        {
            if (!_wsOpen) { _wsOpen = true; GD.Print("[Voice] ws open"); }
            DrainIncoming();
            if (_capturing) PumpMicUp();
        }
        else if (st == WebSocketPeer.State.Closed)
        {
            if (_wsOpen) GD.Print("[Voice] ws closed — reconnecting");
            _wsOpen = false;
            ConnectWs();           // best-effort auto-reconnect
        }
        FeedPlayback();
    }

    /// <summary>Read mic frames, downmix to mono, resample mix-rate → 16 kHz,
    /// pack to PCM16, and stream up while PTT is held.</summary>
    private void PumpMicUp()
    {
        if (_capture == null) return;
        int avail = _capture.GetFramesAvailable();
        if (avail <= 0) return;
        Vector2[] frames = _capture.GetBuffer(avail);

        double step = _micMixRate / MicSendRate;   // input samples per output sample (e.g. ~2.756)
        var outBytes = new List<byte>(avail);
        // Linear resample across this buffer. _resampPhase carries the fractional
        // read position between frames so we don't click at buffer boundaries.
        while (_resampPhase < frames.Length)
        {
            int i = (int)_resampPhase;
            float a = (frames[i].X + frames[i].Y) * 0.5f;
            float b = (i + 1 < frames.Length) ? (frames[i + 1].X + frames[i + 1].Y) * 0.5f : a;
            float frac = (float)(_resampPhase - i);
            float s = Mathf.Clamp(a + (b - a) * frac, -1f, 1f);
            short v = (short)(s * 32767f);
            outBytes.Add((byte)(v & 0xFF));
            outBytes.Add((byte)((v >> 8) & 0xFF));
            _resampPhase += step;
        }
        _resampPhase -= frames.Length;   // keep the fractional remainder for next buffer
        if (outBytes.Count > 0)
            _ws.Send(outBytes.ToArray());
    }

    /// <summary>Handle incoming WS packets: JSON control vs binary audio.</summary>
    private void DrainIncoming()
    {
        while (_ws.GetAvailablePacketCount() > 0)
        {
            byte[] pkt = _ws.GetPacket();
            if (_ws.WasStringPacket())
                HandleControl(Encoding.UTF8.GetString(pkt));
            else
                EnqueueAudio(pkt);
        }
    }

    private void HandleControl(string json)
    {
        string type;
        try
        {
            using var doc = JsonDocument.Parse(json);
            type = doc.RootElement.TryGetProperty("type", out var t) ? t.GetString() : null;
            switch (type)
            {
                case "cancel":
                    StopPlayback();
                    break;
                case "transcript":
                    EmitSignal(SignalName.Transcript, GetStr(doc, "text"));
                    break;
                case "sentence":
                    EmitSignal(SignalName.AriaSentence, GetStr(doc, "text"));
                    break;
                case "done":
                    // turn complete; nothing required (audio plays out of the queue)
                    break;
            }
        }
        catch (Exception e) { GD.PrintErr($"[Voice] bad control msg: {e.Message}"); }
    }

    private static string GetStr(JsonDocument doc, string key) =>
        doc.RootElement.TryGetProperty(key, out var v) ? (v.GetString() ?? "") : "";

    /// <summary>Decode incoming PCM16 (mono, 24 kHz) into float samples queued for the generator.</summary>
    private void EnqueueAudio(byte[] pcm)
    {
        int i = 0;
        // Stitch an odd byte left over from the previous packet.
        if (_pcmCarry >= 0 && pcm.Length > 0)
        {
            short v = (short)(_pcmCarry | (pcm[0] << 8));
            _outSamples.Enqueue(v / 32768f);
            i = 1;
            _pcmCarry = -1;
        }
        for (; i + 1 < pcm.Length; i += 2)
        {
            short v = (short)(pcm[i] | (pcm[i + 1] << 8));
            _outSamples.Enqueue(v / 32768f);
        }
        _pcmCarry = (i < pcm.Length) ? pcm[i] : -1;   // stash trailing odd byte
    }

    /// <summary>Push queued samples into the generator as space frees up.</summary>
    private void FeedPlayback()
    {
        if (_genPlayback == null) return;
        int canPush = _genPlayback.GetFramesAvailable();
        if (canPush <= 0 || _outSamples.Count == 0) return;
        int n = Math.Min(canPush, _outSamples.Count);
        var frames = new Vector2[n];
        for (int k = 0; k < n; k++)
        {
            float s = _outSamples.Dequeue();
            frames[k] = new Vector2(s, s);   // mono → both channels
        }
        _genPlayback.PushBuffer(frames);
    }

    private void StopPlayback()
    {
        _outSamples.Clear();
        _pcmCarry = -1;
        _genPlayback?.ClearBuffer();
    }

    private void SendJson(string json)
    {
        if (_ws != null && _ws.GetReadyState() == WebSocketPeer.State.Open)
            _ws.SendText(json);
    }

    public override void _ExitTree()
    {
        try { _ws?.Close(); } catch { }
    }
}
