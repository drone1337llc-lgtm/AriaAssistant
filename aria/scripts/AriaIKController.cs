using Godot;
using System;
using System.Collections.Generic;
using System.Numerics;
using Aria;
using WorldVec3 = System.Numerics.Vector3;
using GodotVec3 = Godot.Vector3;
using GodotQuat = Godot.Quaternion;

namespace Aria
{
    /// <summary>
    /// Drives a single named IK chain on Aria's skeleton. Caches the bone indices
    /// and per-segment rest lengths at construction so per-frame solves are cheap.
    ///
    /// Blend modes:
    ///   • Override:   the IK rotation REPLACES the animation-driven rotation.
    ///                  Use for head look-at, finger presets, and any case where
    ///                  the animation's contribution to that bone should be ignored.
    ///   • Additive:   the IK rotation's delta from rest is ADDED to the
    ///                  animation-driven rotation. Use for arms while she walks —
    ///                  the walk keeps swinging the legs, the IK pulls the hand
    ///                  toward the LLM's chosen target.
    /// </summary>
    public sealed class AriaIKChainDriver
    {
        public string Name { get; }
        public string[] BoneNames { get; }
        public int[] BoneIdx { get; }
        public float[] RestLengths { get; }     // segment length (parent→child) in world units at rest pose
        public WorldVec3[] RestDirs { get; }    // segment direction at rest pose (unit), in parent-bone local space
        public bool AnchorRoot { get; set; } = true;
        public float Weight { get; set; } = 1f;   // 0..1, multiplies the IK rotation contribution

        public AriaIKChainDriver(string name, string[] boneNames, int[] boneIdx,
                                 float[] restLengths, WorldVec3[] restDirs)
        {
            Name = name;
            BoneNames = boneNames;
            BoneIdx = boneIdx;
            RestLengths = restLengths;
            RestDirs = restDirs;
        }

        public bool IsValid => BoneIdx != null && BoneIdx.Length > 0 && BoneIdx[0] >= 0;
    }

    /// <summary>
    /// Applies IK to Aria's Skeleton3D. One instance per CharacterController.
    /// Holds a dictionary of named chains; the LLM asks for a chain by name
    /// ("arm_left", "head", "spine", …) and a target, and SolveAndApply does the rest.
    ///
    /// Usage from a directive:
    ///   var ctrl = ikController;
    ///   ctrl.SolveAndApply("arm_left", targetWorldPos, blendMode: Additive, weight: 1f);
    /// Then every frame the controller writes the IK rotation delta into the skeleton
    /// AFTER the animation has run, so animation + IK compose without conflict.
    /// </summary>
    public partial class AriaIKController : Node
    {
        public enum BlendMode { Override, Additive }

        /// <summary>One per chain currently being driven by IK. Cleared on IkRelease.</summary>
        public class ActiveChain
        {
            public AriaIKChainDriver Driver;
            public WorldVec3 Target;
            public WorldVec3? PoleHint;
            public BlendMode Mode;
            public float Weight;
            public float TimeLeft;   // for IkHoldPose; -1 = hold until released
        }

        private readonly Dictionary<string, ActiveChain> _active = new();
        private readonly Dictionary<string, AriaIKChainDriver> _drivers = new();
        private Skeleton3D _skel;
        private Node3D _root;     // the Aria root (skeleton is somewhere under here)

        public IReadOnlyDictionary<string, ActiveChain> Active => _active;

        public void Setup(Skeleton3D skeleton, Node3D rootNode)
        {
            _skel = skeleton;
            _root = rootNode;
            if (_skel == null)
            {
                GD.PrintErr("[IK] Setup: skeleton is null");
                return;
            }
            // Build drivers for every chain in the catalogue
            foreach (var name in AriaIKChains.AllNames)
                BuildDriver(name);
            GD.Print($"[IK] Initialized {_drivers.Count} chain drivers on skeleton '{_skel.GetPath()}' ({_skel.GetBoneCount()} bones)");
        }

        private void BuildDriver(string chainName)
        {
            var bones = AriaIKChains.Resolve(chainName);
            if (bones == null) return;
            int[] idx = new int[bones.Length];
            float[] lens = new float[bones.Length - 1];
            WorldVec3[] dirs = new WorldVec3[bones.Length - 1];
            for (int i = 0; i < bones.Length; i++)
            {
                idx[i] = _skel.FindBone(bones[i]);
                if (idx[i] < 0)
                {
                    GD.PrintErr($"[IK] chain '{chainName}': bone '{bones[i]}' not found");
                    return;
                }
            }
            // Compute rest-pose segment lengths and directions in parent-bone-local space
            for (int i = 0; i < bones.Length - 1; i++)
            {
                int parentIdx = idx[i];
                int childIdx = idx[i + 1];
                var pRest = _skel.GetBoneGlobalRest(parentIdx).Origin;
                var cRest = _skel.GetBoneGlobalRest(childIdx).Origin;
                var segWorld = cRest - pRest;
                lens[i] = segWorld.Length();
                // Convert world dir to parent-local dir
                var parentRestInv = _skel.GetBoneGlobalRest(parentIdx).AffineInverse();
                var segLocal = parentRestInv.Basis * segWorld;
                dirs[i] = new WorldVec3(segLocal.X, segLocal.Y, segLocal.Z);
                if (dirs[i].LengthSquared() > 1e-10f) dirs[i] = WorldVec3.Normalize(dirs[i]);
            }
            var driver = new AriaIKChainDriver(chainName, bones, idx, lens, dirs);
            _drivers[chainName] = driver;
        }

        // ── Public API (called by directives) ───────────────────────────

        /// <summary>Solve a chain so its tip reaches target. Replaces any prior
        /// active binding for that chain. Target is in WORLD space (Godot.Vector3).</summary>
        public void SolveAndApply(string chainName, GodotVec3 target, GodotVec3? poleHint = null,
                                  BlendMode mode = BlendMode.Additive, float weight = 1f,
                                  float holdSeconds = -1f)
        {
            if (!_drivers.TryGetValue(chainName, out var driver) || driver == null || !driver.IsValid)
            {
                GD.PrintErr($"[IK] chain '{chainName}' unknown or invalid");
                return;
            }
            _active[chainName] = new ActiveChain
            {
                Driver = driver,
                Target = new WorldVec3(target.X, target.Y, target.Z),
                PoleHint = poleHint.HasValue ? new WorldVec3(poleHint.Value.X, poleHint.Value.Y, poleHint.Value.Z) : (WorldVec3?)null,
                Mode = mode,
                Weight = Mathf.Clamp(weight, 0f, 1f),
                TimeLeft = holdSeconds,
            };
        }

        /// <summary>Release a single chain back to animation-driven motion.</summary>
        public void Release(string chainName)
        {
            _active.Remove(chainName);
        }

        /// <summary>Release every active chain. Called on IkReleaseAll directive.</summary>
        public void ReleaseAll() => _active.Clear();

        // ── Per-frame: apply IK on top of animation ─────────────────────

        /// <summary>Call once per frame from CharacterController._Process, AFTER
        /// the animation has run. Walks every active chain, runs FABRIK, and
        /// writes the resulting rotations into the Skeleton3D.</summary>
        public void Update(double delta)
        {
            if (_skel == null || _active.Count == 0) return;

            // We mutate bones in chain order. Important: we need the CURRENT
            // (animation-driven) global pose for the first bone, then derive
            // child positions from there. After we write the new local rotation
            // for bone i, the global pose of bone i+1 is also updated — but we
            // work in world space using a fresh read of the global pose at each
            // step. This avoids stale-state bugs that plague naive chain solvers.

            foreach (var (name, ac) in _active)
            {
                if (ac.TimeLeft > 0f)
                {
                    ac.TimeLeft -= (float)delta;
                    if (ac.TimeLeft <= 0f) { _active.Remove(name); continue; }
                }
                ApplyOneChain(ac);
            }
        }

        private void ApplyOneChain(ActiveChain ac)
        {
            var d = ac.Driver;
            int n = d.BoneIdx.Length;
            // 1) Read current global positions of all chain joints
            var joints = new List<WorldVec3>(n);
            var parentWorlds = new Godot.Transform3D[n];
            for (int i = 0; i < n; i++)
            {
                parentWorlds[i] = _skel.GetBoneGlobalPose(d.BoneIdx[i]);
                var o = parentWorlds[i].Origin;
                joints.Add(new WorldVec3(o.X, o.Y, o.Z));
            }

            // 2) Solve FABRIK — tip tries to reach ac.Target
            FabrikSolver.Solve(joints, d.RestLengths, ac.Target, ac.PoleHint,
                              anchorRoot: d.AnchorRoot);

            // 3) For each bone i, compute the new local rotation that moves
            //    parentWorlds[i].Origin → joints[i] (preserving parent rotation).
            //    Then BLEND with the animation-driven rotation per the blend mode.
            for (int i = 0; i < n; i++)
            {
                int bone = d.BoneIdx[i];
                if (bone < 0) continue;

                // The new global rotation: make the bone's tail point at the new joint pos
                int childBone = (i + 1 < n) ? d.BoneIdx[i + 1] : -1;
                GodotVec3 toTail;
                if (childBone >= 0)
                {
                    // Tail of bone i is the head of bone i+1
                    var j = joints[i + 1];
                    toTail = new GodotVec3(j.X, j.Y, j.Z);
                }
                else
                {
                    // Tip of the chain — preserve original direction
                    var dir = _skel.GetBoneGlobalPose(bone).Basis.Y.Normalized();
                    var j = joints[i];
                    toTail = new GodotVec3(j.X, j.Y, j.Z) + dir;
                }

                var j0 = joints[i];
                GodotVec3 origin = new GodotVec3(j0.X, j0.Y, j0.Z);

                // New global rotation: align the rest Y axis (default bone direction)
                // with (newTail - origin).
                var restGlobal = _skel.GetBoneGlobalRest(bone);
                var restDir = restGlobal.Basis.Y.Normalized();   // bone's "outward" axis at rest
                var newDir = (toTail - origin).Normalized();
                if (newDir.LengthSquared() < 1e-6f) continue;

                // Compute delta rotation: rotation that takes restDir -> newDir, in world
                var worldRot = FromTo(restDir, newDir);
                // Convert to local: undo the parent's world rotation
                Godot.Transform3D parentGlobal;
                if (i == 0)
                {
                    // Root of chain — parent is the bone's actual parent in the skeleton
                    int parentBone = _skel.GetBoneParent(bone);
                    parentGlobal = parentBone >= 0
                        ? _skel.GetBoneGlobalPose(parentBone)
                        : _skel.GlobalTransform;
                }
                else
                {
                    parentGlobal = _skel.GetBoneGlobalPose(d.BoneIdx[i - 1]);
                }
                var newLocal = parentGlobal.AffineInverse().Basis * new Godot.Basis(worldRot);
                GodotQuat newLocalQuat = new GodotQuat(newLocal.Orthonormalized());

                // Blend with the animation's current pose
                var currentLocal = _skel.GetBonePoseRotation(bone);
                var restLocal = _skel.GetBoneRest(bone).Basis.GetRotationQuaternion();
                if (ac.Mode == BlendMode.Override)
                {
                    // IK fully replaces the animation rotation; weight blends
                    // toward the current (animation) pose.
                    _skel.SetBonePoseRotation(bone, newLocalQuat.Slerp(currentLocal, 1f - ac.Weight));
                }
                else // Additive
                {
                    // Compute IK delta FROM CURRENT animation pose TO the IK pose
                    // (in local space). This delta represents the *offset to apply
                    // on top of the current animation*, not the offset from rest.
                    //
                    // The old formula used `restLocal.Inverse() * newLocalQuat` as
                    // the delta, which represents "rest -> IK" instead of "current
                    // -> IK". For a bone whose animation has it bent away from
                    // rest (spine, arms, head all bend in idle), that delta can
                    // compound across multiple apply frames and rotate the chain
                    // past 180° — which is what makes Aria flip upside-down
                    // after several `ik_lean forward` directives.
                    //
                    // Correct: delta = current * (current^-1 * newLocalQuat), i.e.
                    // the rotation that takes the current pose to the IK pose.
                    // We then slerp from identity (no offset) to that delta,
                    // weighted, and apply on top of current.
                    var ikDelta = currentLocal.Inverse() * newLocalQuat;
                    var combined = currentLocal * GodotQuat.Identity.Slerp(ikDelta, ac.Weight);
                    _skel.SetBonePoseRotation(bone, combined.Normalized());
                }
            }
        }

        private static Godot.Quaternion FromTo(Godot.Vector3 from, Godot.Vector3 to)
        {
            float d = from.Dot(to);
            if (d >= 0.99999f) return GodotQuat.Identity;
            if (d <= -0.99999f)
            {
                Godot.Vector3 axis = Mathf.Abs(from.X) < 0.9f ? Godot.Vector3.Right : Godot.Vector3.Up;
                return new GodotQuat(axis.Normalized(), Mathf.Pi);
            }
            var cross = from.Cross(to);
            return new GodotQuat(cross.X, cross.Y, cross.Z, 1f + d).Normalized();
        }
    }
}
