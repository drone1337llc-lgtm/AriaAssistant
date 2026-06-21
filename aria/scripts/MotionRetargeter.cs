using Godot;
using System;
using System.Collections.Generic;
using System.Text.Json;
using Aria;
using WorldVec3 = System.Numerics.Vector3;
using GodotVec3 = Godot.Vector3;

namespace Aria
{
    /// <summary>
    /// Retargets raw SMPL-22-joint motion data (one frame at a time) onto
    /// Aria's Mixamo skeleton using the same FABRIK chain configuration
    /// the live IK controller uses. Produces a per-bone rotation timeline
    /// that AnimationPlayer can play as a clip.
    ///
    /// The Python motion server now ships raw `joints` arrays (root-relative
    /// SMPL positions) instead of pre-baked rotations. The Godot client
    /// runs this retargeter on each frame's joint set, then writes the
    /// resulting per-bone rotations into a Godot.Animation. This produces
    /// much more faithful motions on Aria's specific body proportions
    /// than the rotation-from-rest-direction fallback.
    /// </summary>
    public static class MotionRetargeter
    {
        // SMPL joint index → Mixamo bone name. Same table the Python server
        // uses; mirrored here so we can resolve chain roots from joint idx.
        public static readonly string[] SmplToMixamo = {
            null,                   // 0  pelvis (root — used to translate the whole character, not a bone rotation)
            "J_Bip_L_UpperLeg",     // 1
            "J_Bip_R_UpperLeg",     // 2
            "J_Bip_C_Spine",         // 3
            "J_Bip_L_LowerLeg",     // 4
            "J_Bip_R_LowerLeg",     // 5
            "J_Bip_C_Chest",         // 6
            "J_Bip_L_Foot",          // 7
            "J_Bip_R_Foot",          // 8
            "J_Bip_C_UpperChest",    // 9
            "J_Bip_L_ToeBase",       // 10
            "J_Bip_R_ToeBase",       // 11
            "J_Bip_C_Neck",          // 12
            "J_Bip_L_Shoulder",      // 13
            "J_Bip_R_Shoulder",      // 14
            "J_Bip_C_Head",          // 15
            "J_Bip_L_UpperArm",      // 16
            "J_Bip_R_UpperArm",      // 17
            "J_Bip_L_LowerArm",      // 18
            "J_Bip_R_LowerArm",      // 19
            "J_Bip_L_Hand",          // 20
            "J_Bip_R_Hand",          // 21
        };

        public static readonly int[] SmplParents = { -1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19 };

        // IK chains to retarget, expressed as ordered lists of SMPL joint indices
        // (root first, tip last). Each chain gets a FABRIK solve per frame.
        private static readonly int[][] Chains = {
            new[] { 0, 3, 6, 9, 12, 15 },     // spine → neck → head
            new[] { 13, 16, 18, 20 },         // L shoulder → upper → lower → hand
            new[] { 14, 17, 19, 21 },         // R shoulder → upper → lower → hand
            new[] { 1, 4, 7, 10 },            // L upper leg → lower → foot → toe
            new[] { 2, 5, 8, 11 },            // R upper leg → lower → foot → toe
        };

        /// <summary>
        /// Retarget a single frame's SMPL joints (root-relative) into a set
        /// of per-bone rotation deltas. Caller writes these to Animation tracks.
        /// </summary>
        public static Dictionary<string, Quaternion> RetargetFrame(
            Skeleton3D skeleton,
            Node3D ariaRoot,
            WorldVec3[] smplJointsRootLocal)
        {
            var result = new Dictionary<string, Quaternion>();
            if (skeleton == null || ariaRoot == null) return result;

            // Aria's world position + a small offset to place the motion at her feet.
            // We use the current world X/Z and zero Y (the AnimationPlayer will
            // move the character; the motion is the body shape, not the locomotion).
            var ariaWorld = ariaRoot.GlobalPosition;
            var rootWorld = new GodotVec3(ariaWorld.X, ariaWorld.Y, ariaWorld.Z);

            // Build world-space SMPL joint positions by adding aria's root
            // to each root-relative joint. Y is kept from SMPL (so the head
            // is up, etc.).
            var smplWorld = new GodotVec3[smplJointsRootLocal.Length];
            for (int i = 0; i < smplJointsRootLocal.Length; i++)
            {
                var j = smplJointsRootLocal[i];
                smplWorld[i] = new GodotVec3(
                    rootWorld.X + j.X,
                    rootWorld.Y + j.Y,
                    rootWorld.Z + j.Z);
            }

            // For each chain, run FABRIK on Aria's bones to reach the
            // corresponding SMPL joint positions.
            foreach (var chain in Chains)
            {
                string tipBone = SmplToMixamo[chain[chain.Length - 1]];
                if (string.IsNullOrEmpty(tipBone)) continue;
                int tipIdx = skeleton.FindBone(tipBone);
                if (tipIdx < 0) continue;

                // Read current joint positions of Aria's chain
                var chainBones = new int[chain.Length];
                bool allFound = true;
                for (int i = 0; i < chain.Length; i++)
                {
                    string mix = SmplToMixamo[chain[i]];
                    if (string.IsNullOrEmpty(mix)) { allFound = false; break; }
                    chainBones[i] = skeleton.FindBone(mix);
                    if (chainBones[i] < 0) { allFound = false; break; }
                }
                if (!allFound) continue;

                // Read Aria's current joint world positions
                var joints = new List<WorldVec3>(chainBones.Length);
                for (int i = 0; i < chainBones.Length; i++)
                {
                    var o = skeleton.GetBoneGlobalPose(chainBones[i]).Origin;
                    joints.Add(new WorldVec3(o.X, o.Y, o.Z));
                }

                // Compute per-segment rest lengths from the FIRST frame (rest pose)
                var lengths = new float[chainBones.Length - 1];
                for (int i = 0; i < lengths.Length; i++)
                {
                    lengths[i] = WorldVec3.Distance(joints[i], joints[i + 1]);
                    if (lengths[i] < 1e-4f) lengths[i] = 0.1f;   // avoid div-by-zero
                }

                // Target = SMPL tip in world space
                var smplTip = smplWorld[chain[chain.Length - 1]];
                var target = new WorldVec3(smplTip.X, smplTip.Y, smplTip.Z);

                // Solve
                FabrikSolver.Solve(joints, lengths, target, poleHint: null, anchorRoot: false);

                // For each bone, compute the rotation that points (joints[i+1] - joints[i])
                // along the bone's rest direction. Apply as an OVERRIDE on the
                // animation (motion clips replace the rest pose entirely).
                for (int i = 0; i < chainBones.Length - 1; i++)
                {
                    int bone = chainBones[i];
                    var newDir = joints[i + 1] - joints[i];
                    if (newDir.LengthSquared() < 1e-8f) continue;
                    newDir = WorldVec3.Normalize(newDir);

                    var restGlobal = skeleton.GetBoneGlobalRest(bone);
                    var restDir = new WorldVec3(restGlobal.Basis.Y.X, restGlobal.Basis.Y.Y, restGlobal.Basis.Y.Z);
                    if (restDir.LengthSquared() < 1e-8f) continue;
                    restDir = WorldVec3.Normalize(restDir);

                    var newGodotDir = new GodotVec3(newDir.X, newDir.Y, newDir.Z);
                    var restGodotDir = new GodotVec3(restDir.X, restDir.Y, restDir.Z);
                    var worldRot = FromToQuaternion(restGodotDir, newGodotDir);

                    // Convert world rotation to local by undoing parent global
                    Godot.Transform3D parentGlobal;
                    if (i == 0)
                    {
                        int parentBone = skeleton.GetBoneParent(bone);
                        parentGlobal = parentBone >= 0
                            ? skeleton.GetBoneGlobalPose(parentBone)
                            : skeleton.GlobalTransform;
                    }
                    else
                    {
                        parentGlobal = skeleton.GetBoneGlobalPose(chainBones[i - 1]);
                    }
                    var newLocal = parentGlobal.AffineInverse().Basis * new Godot.Basis(worldRot);
                    string boneName = SmplToMixamo[chain[i]];
                    result[boneName] = new Godot.Quaternion(newLocal.Orthonormalized());
                }
                // Tip bone: identity (it's the end of the chain, the FABRIK
                // positions are implicit in the chain's rotations)
            }

            return result;
        }

        private static Godot.Quaternion FromToQuaternion(GodotVec3 from, GodotVec3 to)
        {
            float d = from.Dot(to);
            if (d >= 0.99999f) return Godot.Quaternion.Identity;
            if (d <= -0.99999f)
            {
                GodotVec3 axis = Mathf.Abs(from.X) < 0.9f ? GodotVec3.Right : GodotVec3.Up;
                return new Godot.Quaternion(axis.Normalized(), Mathf.Pi);
            }
            var cross = from.Cross(to);
            return new Godot.Quaternion(cross.X, cross.Y, cross.Z, 1f + d).Normalized();
        }
    }
}
