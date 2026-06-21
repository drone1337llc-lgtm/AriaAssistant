using Godot;
using System;
using System.Collections.Generic;

/// <summary>
/// Drives Aria's face via VRoid/VRM blend shapes. Layers three things per frame:
///   1. EMOTION — held expression eased in smoothly.
///   2. BLINK   — auto-timer blink so she isn't glassy-eyed.
///   3. MOUTH   — talking flap while TTS audio is playing.
///
/// Key design: emotions are driven by COMPONENT sub-shapes (Fcl_BRW_* + Fcl_EYE_*)
/// rather than the Fcl_ALL_* composites. VRoid's ALL composites include mouth-open
/// weight — using them held the mouth open even when she wasn't talking.
/// Component shapes affect only brows and eyes, so the mouth stays closed until
/// StartTalking() is called. Falls back to ALL composites at 50% if component
/// shapes don't exist on the model.
/// </summary>
public partial class ExpressionController : Node
{
    [Export] public float EmotionLerp = 6f;
    [Export] public float BlinkMinInterval = 3.5f;
    [Export] public float BlinkMaxInterval = 7.5f;
    [Export] public float BlinkDuration = 0.45f;   // full open→closed→open, eased; deliberately slow
    [Export] public float MouthLevel = 0.7f;
    [Export] public float MouthSpeed = 11f;

    private readonly Dictionary<string, List<(MeshInstance3D Mesh, int Index)>> _shapes = new();
    private readonly Dictionary<string, float> _applied = new();
    private readonly Dictionary<string, float> _emotion = new();

    // Component sub-shapes: brow + eye only (zero mouth contribution)
    private string _slotBrwJoy, _slotEyeJoy;
    private string _slotBrwFun, _slotEyeFun;
    private string _slotBrwAngry, _slotEyeAngry;
    private string _slotBrwSorrow, _slotEyeSorrow;
    private string _slotBrwSurprised, _slotEyeSurprised;

    // ALL composites — fallback only (used at reduced weight to soften mouth drive)
    private string _slotJoy, _slotFun, _slotAngry, _slotSorrow, _slotSurprised;

    // Utility slots
    private string _slotBlink, _slotMouth;

    private float _blinkTimer, _nextBlink, _blinkPhase = -1f;
    private bool _talking;
    private float _talkPhase;
    private bool _ready;

    public string CurrentEmotion { get; private set; } = "neutral";

    public void Setup(Node ariaRoot)
    {
        _shapes.Clear();
        if (ariaRoot != null) Discover(ariaRoot);

        if (_shapes.Count == 0)
        {
            GD.PrintErr("[Expr] No blend shapes found — facial expressions disabled.");
            return;
        }

        // Component sub-shapes (preferred: no mouth drive)
        _slotBrwJoy       = Resolve("Fcl_BRW_Happy", "Fcl_BRW_Fun");
        _slotEyeJoy       = Resolve("Fcl_EYE_Joy", "Fcl_EYE_Happy");
        _slotBrwFun       = Resolve("Fcl_BRW_Fun", "Fcl_BRW_Happy");
        _slotEyeFun       = Resolve("Fcl_EYE_Fun", "Fcl_EYE_Happy");
        _slotBrwAngry     = Resolve("Fcl_BRW_Angry");
        _slotEyeAngry     = Resolve("Fcl_EYE_Angry");
        _slotBrwSorrow    = Resolve("Fcl_BRW_Sorrow");
        _slotEyeSorrow    = Resolve("Fcl_EYE_Sorrow");
        _slotBrwSurprised = Resolve("Fcl_BRW_Surprised");
        _slotEyeSurprised = Resolve("Fcl_EYE_Surprised");

        // ALL composites — fallback if component shapes don't exist
        _slotJoy       = Resolve("Fcl_ALL_Joy", "happy", "joy", "Fcl_ALL_Fun");
        _slotFun       = Resolve("Fcl_ALL_Fun", "relaxed", "fun", "smile", "Fcl_ALL_Joy");
        _slotAngry     = Resolve("Fcl_ALL_Angry", "angry", "mad");
        _slotSorrow    = Resolve("Fcl_ALL_Sorrow", "sad", "sorrow");
        _slotSurprised = Resolve("Fcl_ALL_Surprised", "surprised", "surprise");

        _slotBlink = Resolve("Fcl_EYE_Close", "blink", "Fcl_EYE_Close_L", "eyesClosed");
        _slotMouth = Resolve("Fcl_MTH_A", "aa", "Fcl_MTH_O", "mouth_open", "Fcl_MTH_E");

        _nextBlink = (float)GD.RandRange(BlinkMinInterval, BlinkMaxInterval);
        _ready = true;

        GD.Print($"[Expr] {_shapes.Count} blend shapes. Component slots → " +
                 $"brwJoy={_slotBrwJoy ?? "—"}, eyeJoy={_slotEyeJoy ?? "—"}, " +
                 $"brwFun={_slotBrwFun ?? "—"}, eyeFun={_slotEyeFun ?? "—"}, " +
                 $"brwAngry={_slotBrwAngry ?? "—"}, brwSorrow={_slotBrwSorrow ?? "—"}, " +
                 $"brwSurprised={_slotBrwSurprised ?? "—"}, blink={_slotBlink ?? "—"}, mouth={_slotMouth ?? "—"}");
        GD.Print($"[Expr] All names: [{string.Join(", ", _shapes.Keys)}]");
    }

    public void SetEmotion(string emotion)
    {
        _emotion.Clear();
        string e = (emotion ?? "neutral").Trim().ToLowerInvariant();
        CurrentEmotion = e;

        string brw = null, eye = null, allSlot = null;
        switch (e)
        {
            case "joy" or "happy" or "excited" or "cheerful":
                brw = _slotBrwJoy; eye = _slotEyeJoy; allSlot = _slotJoy; break;
            case "fun" or "playful" or "relaxed" or "smile" or "amused":
                brw = _slotBrwFun; eye = _slotEyeFun; allSlot = _slotFun; break;
            case "angry" or "mad" or "annoyed" or "frustrated":
                brw = _slotBrwAngry; eye = _slotEyeAngry; allSlot = _slotAngry; break;
            case "sad" or "sorrow" or "sorry" or "down":
                brw = _slotBrwSorrow; eye = _slotEyeSorrow; allSlot = _slotSorrow; break;
            case "surprised" or "surprise" or "shock" or "shocked" or "curious":
                brw = _slotBrwSurprised; eye = _slotEyeSurprised; allSlot = _slotSurprised; break;
        }

        if (brw != null || eye != null)
        {
            if (brw != null) _emotion[brw] = 1.0f;
            if (eye != null) _emotion[eye] = 1.0f;
        }
        else if (allSlot != null)
        {
            // Only ALL composite available — use at 50% to soften its mouth contribution
            _emotion[allSlot] = 0.5f;
        }
        // neutral → _emotion stays empty; all shapes lerp back to 0
    }

    public void StartTalking() { _talking = true; }
    public void StopTalking()  { _talking = false; _talkPhase = 0f; }

    public override void _Process(double delta)
    {
        if (!_ready) return;
        float d = (float)delta;

        // blink
        float blinkVal = 0f;
        _blinkTimer += d;
        if (_blinkPhase < 0f && _blinkTimer >= _nextBlink)
        {
            _blinkPhase = 0f;
            GD.Print($"[Expr] blink (after {_blinkTimer:F1}s idle, dur {BlinkDuration:F2}s)");
        }
        if (_blinkPhase >= 0f)
        {
            _blinkPhase += d / Math.Max(0.02f, BlinkDuration);
            float tri = _blinkPhase < 0.5f ? _blinkPhase * 2f : 1f - (_blinkPhase - 0.5f) * 2f;
            blinkVal = tri * tri * (3f - 2f * tri);   // ease so the lid glides, not snaps
            blinkVal = Mathf.Clamp(blinkVal, 0f, 1f);
            if (_blinkPhase >= 1f)
            {
                _blinkPhase = -1f;
                _blinkTimer = 0f;
                _nextBlink = (float)GD.RandRange(BlinkMinInterval, BlinkMaxInterval);
            }
        }

        // mouth flap while speaking
        float mouthVal = 0f;
        if (_talking)
        {
            _talkPhase += d * MouthSpeed;
            mouthVal = (0.5f + 0.5f * Mathf.Sin(_talkPhase)) * MouthLevel;
        }

        // compose & apply
        foreach (var kv in _shapes)
        {
            string key = kv.Key;
            float target = _emotion.TryGetValue(key, out var ev) ? ev : 0f;
            bool snappy = false;
            if (_slotBlink != null && key == _slotBlink) { target = Math.Max(target, blinkVal); snappy = true; }
            if (_slotMouth != null && key == _slotMouth) { target = Math.Max(target, mouthVal); snappy = true; }

            float cur = _applied.TryGetValue(key, out var cv) ? cv : 0f;
            float nv = snappy ? target : Mathf.Lerp(cur, target, Mathf.Clamp(EmotionLerp * d, 0f, 1f));
            _applied[key] = nv;
            foreach (var s in kv.Value) s.Mesh.SetBlendShapeValue(s.Index, nv);
        }
    }

    private void Discover(Node n)
    {
        if (n is MeshInstance3D mi && mi.Mesh is ArrayMesh arr)
        {
            int count = mi.GetBlendShapeCount();
            for (int i = 0; i < count; i++)
            {
                string key = arr.GetBlendShapeName(i).ToString().ToLowerInvariant();
                if (!_shapes.TryGetValue(key, out var list)) { list = new(); _shapes[key] = list; }
                list.Add((mi, i));
            }
        }
        foreach (var child in n.GetChildren()) Discover(child);
    }

    private string Resolve(params string[] candidates)
    {
        foreach (var c in candidates)
        {
            string k = c.ToLowerInvariant();
            if (_shapes.ContainsKey(k)) return k;
        }
        return null;
    }
}
