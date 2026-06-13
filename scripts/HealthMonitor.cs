using Godot;
using System;
using System.IO;

/// <summary>
/// Aria's self-watch. Runtime "self-healing" can't mean rewriting her own code
/// while she runs — but it CAN mean continuously checking that her core
/// invariants hold and recovering from the failure modes we know about:
///
///   • she drifted off-screen or to a NaN position   → teleport back to the floor
///   • her AnimationPlayer has no clips               → log (import/retarget broke)
///   • her animation stalled (not playing)           → nudge her back to Idle
///   • her LLM brain is unreachable                   → note it (LLMBridge already
///                                                       falls back to offline lines)
///
/// Every anomaly + recovery is appended to a health log. That log (plus the
/// conversation dataset LLMBridge writes) is the substrate for the *deeper*
/// self-improvement loop: a daily background agent reads these files and
/// proposes real code/parameter fixes. See docs/ARIA_AI_SETUP.md.
/// </summary>
public partial class HealthMonitor : Node
{
    [Export] public float CheckInterval = 4f;
    [Export] public string HealthLogPath = @"C:\Users\Tench\Documents\AI Learning\aria_health.log";
    [Export] public bool ReactOnRecover = true;   // let her visibly "notice" a glitch

    private CharacterController _char;
    private AnimationPlayer _anim;
    private LLMBridge _llm;
    private Node3D _aria;

    private float _t;
    private int _animStuckChecks;
    private bool _warnedNoAnims;
    private int _lastLlmFailures;

    public void Setup(CharacterController c, AnimationPlayer anim, LLMBridge llm, Node3D aria)
    {
        _char = c; _anim = anim; _llm = llm; _aria = aria;
        Log("startup", "HealthMonitor online.");
    }

    public override void _Process(double delta)
    {
        _t += (float)delta;
        if (_t < CheckInterval) return;
        _t = 0f;
        try { RunChecks(); }
        catch (Exception e) { GD.PrintErr($"[Health] check error: {e.Message}"); }
    }

    private void RunChecks()
    {
        // 1) Position sanity — recover from off-screen / NaN drift.
        if (_char != null && _char.NeedsRecovery())
        {
            _char.RecoverToFloor();
            Log("recover", "Feet off-screen or NaN → reset to desktop floor.");
            if (ReactOnRecover) _char.PlayGesture("look", 2f);
        }

        // 2) Animation library present?
        if (_anim != null && !_warnedNoAnims)
        {
            bool any = false;
            foreach (var libName in _anim.GetAnimationLibraryList())
            {
                var lib = _anim.GetAnimationLibrary(libName);
                if (lib != null && lib.GetAnimationList().Count > 0) { any = true; break; }
            }
            if (!any)
            {
                _warnedNoAnims = true;
                Log("error", "AnimationPlayer has no clips — FBX retarget/import likely failed (check AnimationBuilder log).");
            }
        }

        // 3) Animation actually advancing?
        if (_anim != null)
        {
            if (!_anim.IsPlaying())
            {
                _animStuckChecks++;
                if (_animStuckChecks >= 2)
                {
                    _animStuckChecks = 0;
                    _char?.Nudge();
                    Log("recover", "AnimationPlayer idle for two checks → nudged back to Idle.");
                }
            }
            else _animStuckChecks = 0;
        }

        // 4) LLM brain reachability (LLMBridge handles the actual fallback).
        if (_llm != null && _llm.ConsecutiveFailures != _lastLlmFailures)
        {
            _lastLlmFailures = _llm.ConsecutiveFailures;
            if (_llm.ConsecutiveFailures > 0)
                Log("warn", $"LLM unreachable (consecutive failures={_llm.ConsecutiveFailures}); using offline lines.");
            else
                Log("info", "LLM reachable again.");
        }
    }

    private void Log(string kind, string message)
    {
        string line = $"{DateTime.UtcNow:o}\t{kind}\t{message}";
        GD.Print($"[Health] {kind}: {message}");
        try
        {
            string path = ResolvePath();
            File.AppendAllText(path, line + "\n");
        }
        catch (Exception e)
        {
            GD.PrintErr($"[Health] could not write health log: {e.Message}");
        }
    }

    private string ResolvePath()
    {
        try
        {
            string dir = Path.GetDirectoryName(HealthLogPath);
            if (!string.IsNullOrEmpty(dir) && Directory.Exists(dir)) return HealthLogPath;
        }
        catch { /* fall through */ }
        return ProjectSettings.GlobalizePath("user://aria_health.log");
    }
}
