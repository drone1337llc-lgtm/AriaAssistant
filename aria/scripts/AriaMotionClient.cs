using Godot;
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using System.Net.Http;
using System.Text;
using Aria;
// Godot also defines a Godot.HttpClient; alias so bare HttpClient is unambiguous.
using HttpClient = System.Net.Http.HttpClient;

namespace Aria
{
    /// <summary>
    /// Client for the FloodDiffusion motion-generation server on the AI PC.
    /// The brain (LLMBridge) issues RequestMotion directives; this client
    /// posts them to the server, polls for completion, and bakes the result
    /// into the AnimationLibrary when it arrives.
    ///
    /// Constraints (per the user's spec):
    ///   • Server runs ONE generation at a time (single-job). Additional
    ///     requests are queued server-side.
    ///   • Queue cap: 100 requests. Reject further requests with a clear error.
    ///   • Generations are kicked off by the LLM on demand (the LLM writes a
    ///     RequestMotion directive with a text prompt).
    ///   • The directive itself completes as soon as the request is enqueued;
    ///     the actual motion arrives later (async). When it does, this client
    ///     builds a new Animation, adds it to the library under a stable name,
    ///     and emits a signal so the world state can advertise the new motion.
    ///
    /// Wire protocol: HTTP (POST to enqueue, GET to poll, GET to fetch a
    /// finished animation). WebSocket optional for low-latency notification
    /// but the HTTP polling path is the primary contract.
    /// </summary>
    public partial class AriaMotionClient : Node
    {
        [Export] public string ServerUrl = "http://127.0.0.1:8766/motion"; // via bridge tunnel -> PC2:8766
        [Export] public int MaxQueueDepth = 100;
        [Export] public float PollIntervalSec = 2f;
        [Export] public string AuthToken = "";   // optional shared secret

        [Signal] public delegate void MotionEnqueuedEventHandler(string requestId, string prompt, int position);
        [Signal] public delegate void MotionReadyEventHandler(string requestId, string animName, string prompt);
        [Signal] public delegate void MotionFailedEventHandler(string requestId, string prompt, string error);
        [Signal] public delegate void QueueStatusChangedEventHandler(int queueDepth, int capacity);

        private static readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(30) };
        private readonly Dictionary<string, PendingRequest> _pending = new();
        private float _pollTimer = 0f;
        private int _localQueueDepth = 0;
        public int LocalQueueDepth => _localQueueDepth;

        private class PendingRequest
        {
            public string RequestId;
            public string Prompt;
            public string SuggestedName;   // if the LLM provided one (d.Name)
            public int Frames;
            public float EnqueueTime;
            #pragma warning disable CS0649   // PollAttempts is informational; reserved for backoff tuning
            public int PollAttempts;
            #pragma warning restore CS0649
        }

        public override void _Ready()
        {
            // Begin polling on a timer so we react to completions
            SetProcess(true);
        }

        public override void _Process(double delta)
        {
            _pollTimer += (float)delta;
            if (_pollTimer < PollIntervalSec) return;
            _pollTimer = 0f;
            if (_pending.Count == 0) return;
            // Fire-and-forget poll
            _ = PollAll();
        }

        /// <summary>Enqueue a motion-generation request. The actual generation
        /// happens server-side; this returns immediately with the request ID.
        /// If the queue is full, returns null and emits MotionFailed.</summary>
        public string RequestMotion(string prompt, int frames = 60, string suggestedName = "")
        {
            if (string.IsNullOrWhiteSpace(prompt))
            {
                EmitSignal(SignalName.MotionFailed, "", prompt, "empty prompt");
                return null;
            }
            if (_localQueueDepth >= MaxQueueDepth)
            {
                EmitSignal(SignalName.MotionFailed, "", prompt,
                    $"queue full ({_localQueueDepth}/{MaxQueueDepth}) — request rejected");
                GD.PrintErr($"[Motion] Queue full ({_localQueueDepth}/{MaxQueueDepth}) — rejected prompt: '{prompt}'");
                return null;
            }
            // Fire-and-forget POST
            _ = EnqueueAsync(prompt, frames, suggestedName);
            // Optimistically bump depth; we'll reconcile on the poll/ack
            _localQueueDepth++;
            EmitSignal(SignalName.QueueStatusChanged, _localQueueDepth, MaxQueueDepth);
            return "";   // real ID arrives async
        }

        private async Task EnqueueAsync(string prompt, int frames, string suggestedName)
        {
            try
            {
                var payload = new
                {
                    prompt,
                    frames = frames > 0 ? frames : 60,
                    suggested_name = suggestedName ?? "",
                };
                string json = JsonSerializer.Serialize(payload);
                using var content = new StringContent(json, Encoding.UTF8, "application/json");
                if (!string.IsNullOrEmpty(AuthToken))
                    _http.DefaultRequestHeaders.Authorization =
                        new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", AuthToken);
                var resp = await _http.PostAsync(ServerUrl, content);
                var body = await resp.Content.ReadAsStringAsync();
                if (!resp.IsSuccessStatusCode)
                {
                    _localQueueDepth = Math.Max(0, _localQueueDepth - 1);
                    EmitSignal(SignalName.MotionFailed, "", prompt, $"HTTP {resp.StatusCode}: {body}");
                    return;
                }
                using var doc = JsonDocument.Parse(body);
                var root = doc.RootElement;
                string reqId = root.TryGetProperty("id", out var id) ? id.GetString() ?? "" : "";
                int queuePos = root.TryGetProperty("position", out var pos) ? pos.GetInt32() : -1;
                if (string.IsNullOrEmpty(reqId))
                {
                    _localQueueDepth = Math.Max(0, _localQueueDepth - 1);
                    EmitSignal(SignalName.MotionFailed, "", prompt, "server returned no id");
                    return;
                }
                _pending[reqId] = new PendingRequest
                {
                    RequestId = reqId,
                    Prompt = prompt,
                    SuggestedName = suggestedName,
                    Frames = frames,
                    EnqueueTime = (float)Time.GetTicksMsec() / 1000f,
                };
                EmitSignal(SignalName.MotionEnqueued, reqId, prompt, queuePos);
                GD.Print($"[Motion] enqueued '{prompt}' (id={reqId}, pos={queuePos})");
            }
            catch (Exception e)
            {
                _localQueueDepth = Math.Max(0, _localQueueDepth - 1);
                EmitSignal(SignalName.MotionFailed, "", prompt, e.Message);
                GD.PrintErr($"[Motion] enqueue failed: {e.Message}");
            }
        }

        private async Task PollAll()
        {
            if (_pending.Count == 0) return;
            try
            {
                var ids = new List<string>(_pending.Keys);
                var payload = new { ids };
                string json = JsonSerializer.Serialize(payload);
                using var content = new StringContent(json, Encoding.UTF8, "application/json");
                var resp = await _http.PostAsync(ServerUrl + "/status", content);
                var body = await resp.Content.ReadAsStringAsync();
                if (!resp.IsSuccessStatusCode) return;
                using var doc = JsonDocument.Parse(body);
                if (!doc.RootElement.TryGetProperty("results", out var results)) return;
                foreach (var entry in results.EnumerateArray())
                {
                    string id = entry.TryGetProperty("id", out var i) ? i.GetString() ?? "" : "";
                    if (string.IsNullOrEmpty(id) || !_pending.ContainsKey(id)) continue;
                    string status = entry.TryGetProperty("status", out var s) ? s.GetString() ?? "pending" : "pending";
                    if (status == "done")
                    {
                        // Fetch the animation data
                        var animUrl = entry.TryGetProperty("animation_url", out var u) ? u.GetString() ?? "" : "";
                        string animName = entry.TryGetProperty("animation_name", out var n) ? n.GetString() ?? id : id;
                        if (!string.IsNullOrEmpty(animUrl))
                        {
                            _ = FetchAndInstallAnimation(id, animUrl, animName);
                        }
                        _pending.Remove(id);
                        _localQueueDepth = Math.Max(0, _localQueueDepth - 1);
                        EmitSignal(SignalName.QueueStatusChanged, _localQueueDepth, MaxQueueDepth);
                    }
                    else if (status == "failed")
                    {
                        string err = entry.TryGetProperty("error", out var e) ? e.GetString() ?? "unknown" : "unknown";
                        // Capture the original prompt BEFORE removing from the
                        // pending dict so the MotionFailed signal carries it.
                        // (The previous version read from _pending after
                        // _pending.Remove, which always returned "" — silent
                        // failure: the consumer never knew which prompt
                        // failed.)
                        string failedPrompt = "";
                        if (_pending.TryGetValue(id, out var pr)) failedPrompt = pr.Prompt;
                        _pending.Remove(id);
                        _localQueueDepth = Math.Max(0, _localQueueDepth - 1);
                        EmitSignal(SignalName.MotionFailed, id, failedPrompt, err);
                        EmitSignal(SignalName.QueueStatusChanged, _localQueueDepth, MaxQueueDepth);
                    }
                    // "pending" or "running" — leave in _pending
                }
            }
            catch (Exception e)
            {
                GD.PrintErr($"[Motion] poll failed: {e.Message}");
            }
        }

        private async Task FetchAndInstallAnimation(string id, string url, string animName)
        {
            try
            {
                var resp = await _http.GetAsync(url);
                var body = await resp.Content.ReadAsStringAsync();
                if (!resp.IsSuccessStatusCode)
                {
                    EmitSignal(SignalName.MotionFailed, id, "", $"fetch HTTP {resp.StatusCode}");
                    return;
                }
                // Parse the JSON animation payload
                using var doc = JsonDocument.Parse(body);
                var root = doc.RootElement;
                string name = root.TryGetProperty("name", out var n) ? n.GetString() ?? animName : animName;
                int frames = root.TryGetProperty("frames", out var f) ? f.GetInt32() : 0;
                int fps = root.TryGetProperty("fps", out var fp) ? fp.GetInt32() : 30;
                float length = (float)frames / Mathf.Max(1, fps);
                string format = root.TryGetProperty("format", out var fmt) ? fmt.GetString() ?? "rotations" : "rotations";

                // Find the AnimationPlayer + Skeleton3D before we generate any tracks
                var player = GetTree()?.Root?.FindChild("AnimationPlayer", true, false) as AnimationPlayer;
                if (player == null)
                {
                    GD.PrintErr("[Motion] no AnimationPlayer found in scene — cannot install motion");
                    EmitSignal(SignalName.MotionFailed, id, "", "no AnimationPlayer");
                    return;
                }
                var playerParent = player.GetParent() as Node;
                var skel = FindSkeletonInNode(playerParent);
                if (skel == null)
                {
                    GD.PrintErr("[Motion] no Skeleton3D under AnimationPlayer — cannot retarget");
                    EmitSignal(SignalName.MotionFailed, id, "", "no skeleton");
                    return;
                }
                var ariaRoot = playerParent as Node3D;

                // Build the animation
                var anim = new Animation { Length = length, LoopMode = Animation.LoopModeEnum.None };
                int tracksAdded = 0;

                if (format == "joints+rotations" && root.TryGetProperty("joints", out var jointsEl) && jointsEl.ValueKind == JsonValueKind.Array)
                {
                    // ── IK retarget path: raw SMPL joint positions, run FABRIK per frame ──
                    tracksAdded = InstallFromJoints(anim, jointsEl, skel, ariaRoot, fps, name);
                }
                else if (root.TryGetProperty("bones", out var bonesEl) && bonesEl.ValueKind == JsonValueKind.Array)
                {
                    // ── Legacy rotation path: per-bone quaternions from the server ──
                    tracksAdded = InstallFromBones(anim, bonesEl, skel, fps);
                }
                else
                {
                    EmitSignal(SignalName.MotionFailed, id, "", "no joints or bones in animation payload");
                    return;
                }

                // Add to library
                var lib = player.GetAnimationLibrary("");
                if (lib == null)
                {
                    lib = new AnimationLibrary();
                    player.AddAnimationLibrary("", lib);
                }
                if (lib.HasAnimation(name)) lib.RemoveAnimation(name);
                lib.AddAnimation(name, anim);
                EmitSignal(SignalName.MotionReady, id, name, $"frames={frames} bones={tracksAdded} format={format}");
                GD.Print($"[Motion] installed '{name}' ({frames} frames @ {fps} fps, {tracksAdded} bone tracks, format={format})");
            }
            catch (Exception e)
            {
                EmitSignal(SignalName.MotionFailed, id, "", e.Message);
                GD.PrintErr($"[Motion] install failed: {e.Message}");
            }
        }

        // ── New IK retarget path: raw joints → FABRIK → bone rotations ──
        private int InstallFromJoints(Animation anim, JsonElement jointsEl, Skeleton3D skel, Node3D ariaRoot, int fps, string animName)
        {
            // jointsEl is an array of frames; each frame is an array of 22 [x,y,z] positions
            int frames = jointsEl.GetArrayLength();
            // Per-bone rotation timelines (one entry per bone that gets rotated)
            var timelines = new Dictionary<string, List<Quaternion>>();
            int tracksAdded = 0;

            // Run the retargeter frame by frame. We need a single read of
            // Aria's rest pose to seed lengths. For multi-frame consistency
            // we restore the skeleton to rest between frames so the chain
            // lengths are stable.
            // 1) Snapshot the skeleton's rest pose
            var restPoses = new Godot.Transform3D[skel.GetBoneCount()];
            for (int i = 0; i < restPoses.Length; i++)
                restPoses[i] = skel.GetBoneGlobalRest(i);

            for (int f = 0; f < frames; f++)
            {
                var frameEl = jointsEl[f];
                if (frameEl.ValueKind != JsonValueKind.Array || frameEl.GetArrayLength() != 22) continue;
                // Reset skeleton to rest (so chain lengths are constant)
                for (int i = 0; i < restPoses.Length; i++)
                    skel.SetBoneGlobalPose(i, restPoses[i]);

                var smplJoints = new System.Numerics.Vector3[22];
                for (int j = 0; j < 22; j++)
                {
                    var je = frameEl[j];
                    if (je.ValueKind != JsonValueKind.Array || je.GetArrayLength() != 3) continue;
                    smplJoints[j] = new System.Numerics.Vector3(
                        (float)je[0].GetDouble(),
                        (float)je[1].GetDouble(),
                        (float)je[2].GetDouble());
                }

                var perBone = MotionRetargeter.RetargetFrame(skel, ariaRoot, smplJoints);
                foreach (var kv in perBone)
                {
                    if (!timelines.ContainsKey(kv.Key)) timelines[kv.Key] = new List<Quaternion>();
                    timelines[kv.Key].Add(kv.Value);
                }
            }

            // Restore rest one more time so the AnimationPlayer picks up the
            // fresh motion cleanly (the rest pose is its default state)
            for (int i = 0; i < restPoses.Length; i++)
                skel.SetBoneGlobalPose(i, restPoses[i]);

            // Write tracks
            var skelPath = skel.GetPath();
            foreach (var kv in timelines)
            {
                int trackIdx = anim.AddTrack(Animation.TrackType.Rotation3D);
                anim.TrackSetPath(trackIdx, new NodePath($"{skelPath}:{kv.Key}"));
                int frameCount = kv.Value.Count;
                for (int f = 0; f < frameCount; f++)
                {
                    var q = kv.Value[f];
                    anim.TrackSetKeyValue(trackIdx, f, new Quaternion(q.X, q.Y, q.Z, q.W));
                    anim.TrackSetKeyTime(trackIdx, f, (double)f / fps);
                }
                tracksAdded++;
            }
            return tracksAdded;
        }

        // ── Legacy rotation path: per-bone quaternions from the server ──
        private int InstallFromBones(Animation anim, JsonElement bonesEl, Skeleton3D skel, int fps)
        {
            int tracksAdded = 0;
            foreach (var boneEl in bonesEl.EnumerateArray())
            {
                string boneName = boneEl.TryGetProperty("name", out var bname) ? bname.GetString() ?? "" : "";
                if (string.IsNullOrEmpty(boneName)) continue;
                if (skel.FindBone(boneName) < 0) continue;
                var skelPath = skel.GetPath();
                int trackIdx = anim.AddTrack(Animation.TrackType.Rotation3D);
                anim.TrackSetPath(trackIdx, new NodePath($"{skelPath}:{boneName}"));
                if (boneEl.TryGetProperty("rotations", out var rots) && rots.ValueKind == JsonValueKind.Array)
                {
                    int fIdx = 0;
                    foreach (var rot in rots.EnumerateArray())
                    {
                        if (rot.ValueKind != JsonValueKind.Array || rot.GetArrayLength() != 4) continue;
                        float w = (float)rot[0].GetDouble();
                        float x = (float)rot[1].GetDouble();
                        float y = (float)rot[2].GetDouble();
                        float z = (float)rot[3].GetDouble();
                        anim.TrackSetKeyValue(trackIdx, fIdx, new Quaternion(x, y, z, w));
                        anim.TrackSetKeyTime(trackIdx, fIdx, (float)fIdx / fps);
                        fIdx++;
                    }
                }
                tracksAdded++;
            }
            return tracksAdded;
        }

        // Find the first Skeleton3D under a node
        private static Skeleton3D FindSkeletonInNode(Node n)
        {
            if (n is Skeleton3D sk) return sk;
            foreach (var c in n.GetChildren())
            {
                var found = FindSkeletonInNode(c);
                if (found != null) return found;
            }
            return null;
        }

        // Walk the node tree under `n` to find the first Skeleton3D, then look
        // up a bone by name. Returns -1 if not found.
        private int FindBoneInNode(Node n, string boneName)
        {
            if (n is Skeleton3D skel && skel.FindBone(boneName) >= 0)
                return skel.FindBone(boneName);
            foreach (var c in n.GetChildren())
            {
                int r = FindBoneInNode(c, boneName);
                if (r >= 0) return r;
            }
            return -1;
        }
    }
}
