using Godot;
using System;
using System.Collections.Generic;

/// <summary>
/// Builds an AnimationLibrary at scene-start by RETARGETING animations from
/// imported Mixamo FBX files (in res://ani/) onto Aria's skeleton.
///
/// The FBX and Aria share bone NAMES (J_Bip_*), but NOT rest poses: the FBX
/// skeleton keeps Mixamo's rotated rest orientations (plus a ~-90°X correction
/// on its Armature node), while Aria's VRM skeleton is normalized (identity
/// rest rotations, Y-up). Copying quaternion keys 1:1 therefore plays back
/// lying down / twisted. Instead we bake: pose the source skeleton at fixed
/// time steps, read each bone's WORLD orientation (including the Armature
/// correction), and convert that into Aria's bone-local space.
/// </summary>
public partial class AnimationBuilder : Node
{
    // Short controller names -> FBX file path
    [Export] public Godot.Collections.Dictionary<string, string> AnimSources = new();

    [Export] public NodePath AriaPath { get; set; } = new("../CharacterController/Aria");

    private const float BakeFps = 30f;

    public void Build()
    {
        var aria = GetNodeOrNull<Node3D>(AriaPath);
        if (aria == null)
        {
            GD.PrintErr($"[AnimBuilder] Could not find Aria at {AriaPath}");
            return;
        }

        // The target skeleton must exist in the imported model.
        var tgtSkel = FindSkeleton(aria);
        if (tgtSkel == null)
        {
            GD.PrintErr("[AnimBuilder] No Skeleton3D found under Aria");
            return;
        }
        GD.Print($"[AnimBuilder] Target skeleton: {tgtSkel.GetPath()} ({tgtSkel.GetBoneCount()} bones)");

        // A VRoid/VRM export ships no animation clips, so Godot creates no
        // AnimationPlayer. Use the one the model brought (if any); otherwise make our
        // own so the baked library has somewhere to live. Anchor its root at Aria so
        // the bone-track paths below resolve regardless of how deep the player sits.
        var animPlayer = FindAnimationPlayer(aria);
        if (animPlayer == null)
        {
            animPlayer = new AnimationPlayer { Name = "AnimationPlayer" };
            aria.AddChild(animPlayer);
            GD.Print("[AnimBuilder] No AnimationPlayer in the imported model — created one under Aria.");
        }
        animPlayer.RootNode = animPlayer.GetPathTo(aria);

        // Path from the AnimationPlayer's root (Aria) down to the skeleton — computed,
        // not hardcoded, so it works whatever the export named the nodes
        // (e.g. "Armature/Skeleton3D" or "Armature/GeneralSkeleton").
        string skelSubPath = aria.GetPathTo(tgtSkel).ToString();

        // Get or create the "" (default) library
        AnimationLibrary lib;
        if (animPlayer.HasAnimationLibrary(""))
        {
            lib = animPlayer.GetAnimationLibrary("");
            foreach (var name in lib.GetAnimationList())
                lib.RemoveAnimation(name);
        }
        else
        {
            lib = new AnimationLibrary();
            animPlayer.AddAnimationLibrary("", lib);
        }

        int added = 0, skipped = 0;
        foreach (var kvp in AnimSources)
        {
            if (BakeRetargeted(kvp.Key, kvp.Value, tgtSkel, skelSubPath, lib)) added++;
            else skipped++;
        }

        GD.Print($"[AnimBuilder] Done. {added} animations baked, {skipped} skipped.");
    }

    /// <summary>
    /// Load one FBX, sample its first animation at BakeFps, and write a new
    /// animation whose rotation keys are expressed in Aria's bone-local space.
    /// Returns true on success.
    /// </summary>
    private bool BakeRetargeted(string shortName, string fbxPath, Skeleton3D tgtSkel, string skelSubPath, AnimationLibrary lib)
    {
        var scene = ResourceLoader.Load<PackedScene>(fbxPath);
        if (scene == null)
        {
            GD.PrintErr($"[AnimBuilder] Could not load scene: {fbxPath}");
            return false;
        }

        var temp = scene.Instantiate();
        try
        {
            var srcPlayer = FindAnimationPlayer(temp);
            var srcSkel = FindSkeleton(temp);
            if (srcPlayer == null || srcSkel == null)
            {
                GD.PrintErr($"[AnimBuilder] {fbxPath}: missing AnimationPlayer or Skeleton3D");
                return false;
            }

            var srcLibs = srcPlayer.GetAnimationLibraryList();
            if (srcLibs.Count == 0)
            {
                GD.PrintErr($"[AnimBuilder] No animation libraries in {fbxPath}");
                return false;
            }
            var srcLib = srcPlayer.GetAnimationLibrary(srcLibs[0]);
            var srcNames = srcLib.GetAnimationList();
            if (srcNames.Count == 0)
            {
                GD.PrintErr($"[AnimBuilder] No animations in {fbxPath}");
                return false;
            }
            var srcAnim = srcLib.GetAnimation(srcNames[0]);

            // Catalog the source rotation tracks: armature correction + bones
            int armTrack = -1;
            var boneTracks = new List<(int Track, int SrcBone, int TgtBone, string Name)>();
            for (int i = 0; i < srcAnim.GetTrackCount(); i++)
            {
                if (srcAnim.TrackGetType(i) != Animation.TrackType.Rotation3D) continue;
                string name = LastSegment(srcAnim.TrackGetPath(i));
                if (name == "Armature") { armTrack = i; continue; }
                if (IsSecondaryOrCollider(name)) continue;
                int s = srcSkel.FindBone(name);
                int g = tgtSkel.FindBone(name);
                if (s < 0 || g < 0) continue;
                boneTracks.Add((i, s, g, name));
            }

            if (boneTracks.Count == 0)
            {
                GD.PrintErr($"[AnimBuilder] {fbxPath}: no bone rotation tracks matched Aria's skeleton");
                return false;
            }

            var anim = new Animation
            {
                Length = srcAnim.Length,
                LoopMode = Animation.LoopModeEnum.Linear,
                Step = 1f / BakeFps,
            };

            // One rotation track per mapped bone, addressed from the
            // AnimationPlayer's root (root_node ".." == Aria)
            var tgtTrackOf = new Dictionary<int, int>();
            foreach (var bt in boneTracks)
            {
                int tr = anim.AddTrack(Animation.TrackType.Rotation3D);
                anim.TrackSetPath(tr, $"{skelSubPath}:{bt.Name}");
                tgtTrackOf[bt.TgtBone] = tr;
            }

            // Source skeleton structure, read once: parents, rest rotations,
            // and which track (if any) animates each source bone. We do the
            // forward-kinematics chain ourselves rather than posing the
            // Skeleton3D — engine-side pose updates on a non-rendered skeleton
            // proved unreliable (we silently got rest poses back).
            int srcCount = srcSkel.GetBoneCount();
            var srcParent = new int[srcCount];
            var srcRest = new Quaternion[srcCount];
            var srcTrackOfBone = new int[srcCount];
            for (int b = 0; b < srcCount; b++)
            {
                srcParent[b] = srcSkel.GetBoneParent(b);
                srcRest[b] = srcSkel.GetBoneRest(b).Basis.GetRotationQuaternion().Normalized();
                srcTrackOfBone[b] = -1;
            }
            foreach (var bt in boneTracks)
                srcTrackOfBone[bt.SrcBone] = bt.Track;

            int boneCount = tgtSkel.GetBoneCount();
            var srcGlobal = new Quaternion[srcCount];
            var srcGlobalOfTgt = new Quaternion[boneCount];
            var animatedTgt = new bool[boneCount];
            var world = new Quaternion[boneCount];

            // Bake in the model's NATIVE orientation — facing (camera vs. side
            // profile) is handled at runtime by CharacterController's body yaw,
            // not frozen into the clip.
            float dt = 1f / BakeFps;
            for (float time = 0f; time <= srcAnim.Length + dt * 0.5f; time += dt)
            {
                float t = Math.Min(time, srcAnim.Length);

                // World correction the FBX scene applies on its Armature node
                Quaternion qArm = armTrack >= 0
                    ? srcAnim.RotationTrackInterpolate(armTrack, t).Normalized()
                    : Quaternion.Identity;

                // Forward kinematics through the source skeleton: local rotation
                // is the sampled key where a track exists, the rest rotation
                // otherwise. Bones are ordered parents-first in imports.
                for (int b = 0; b < srcCount; b++)
                {
                    Quaternion local = srcTrackOfBone[b] >= 0
                        ? srcAnim.RotationTrackInterpolate(srcTrackOfBone[b], t).Normalized()
                        : srcRest[b];
                    int p = srcParent[b];
                    srcGlobal[b] = (p < 0 ? local : srcGlobal[p] * local).Normalized();
                }

                Array.Clear(animatedTgt, 0, boneCount);
                foreach (var bt in boneTracks)
                {
                    srcGlobalOfTgt[bt.TgtBone] = (qArm * srcGlobal[bt.SrcBone]).Normalized();
                    animatedTgt[bt.TgtBone] = true;
                }

                // Convert world orientations into Aria's bone-local space,
                // walking parents-first (imported skeletons are ordered that way)
                for (int b = 0; b < boneCount; b++)
                {
                    int p = tgtSkel.GetBoneParent(b);
                    Quaternion gp = p < 0 ? Quaternion.Identity : world[p];
                    if (animatedTgt[b])
                    {
                        Quaternion gb = srcGlobalOfTgt[b];
                        Quaternion local = (gp.Inverse() * gb).Normalized();
                        anim.RotationTrackInsertKey(tgtTrackOf[b], t, local);
                        world[b] = gb;
                    }
                    else
                    {
                        // Untracked bones (hair, skirt, colliders) follow their rest
                        world[b] = (gp * tgtSkel.GetBoneRest(b).Basis.GetRotationQuaternion()).Normalized();
                    }
                }
            }

            if (lib.HasAnimation(shortName))
                lib.RemoveAnimation(shortName);
            lib.AddAnimation(shortName, anim);

            GD.Print($"[AnimBuilder] Baked '{shortName}' ({anim.Length:F2}s, {boneTracks.Count} bones, armatureFix={(armTrack >= 0 ? "yes" : "no")}) from {System.IO.Path.GetFileName(fbxPath)}");
            return true;
        }
        finally
        {
            // Never entered the tree, so free immediately
            temp.Free();
        }
    }

    private string LastSegment(NodePath path)
    {
        var s = path.ToString();
        int lastSlash = s.LastIndexOf('/');
        string last = lastSlash >= 0 ? s.Substring(lastSlash + 1) : s;
        // Strip "Skeleton3D:" prefix that Godot 4 adds to bone names in imported FBX scenes
        int colon = last.IndexOf(':');
        if (colon >= 0)
            last = last.Substring(colon + 1);
        return last;
    }

    private bool IsSecondaryOrCollider(string name)
    {
        return name.EndsWith("Collider") ||
               name.EndsWith("_end") ||
               name.EndsWith("_end_01") ||
               name.EndsWith("_end_01_end") ||
               name.StartsWith("J_Sec_") ||
               name.StartsWith("J_Adj_");
    }

    private AnimationPlayer FindAnimationPlayer(Node root)
    {
        if (root is AnimationPlayer ap) return ap;
        foreach (var child in root.GetChildren())
        {
            var found = FindAnimationPlayer(child);
            if (found != null) return found;
        }
        return null;
    }

    private Skeleton3D FindSkeleton(Node root)
    {
        if (root is Skeleton3D sk) return sk;
        foreach (var child in root.GetChildren())
        {
            var found = FindSkeleton(child);
            if (found != null) return found;
        }
        return null;
    }
}
