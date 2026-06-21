using System;
using System.Collections.Generic;
using System.Numerics;

namespace Aria
{
    /// <summary>
    /// Pure-math FABRIK (Forward And Backward Reaching Inverse Kinematics) solver.
    /// No engine dependencies — takes a list of joint world positions and a target,
    /// returns a new list of joint positions that place the end-effector at (or
    /// as close as possible to) the target while preserving every segment length.
    ///
    /// Reference: Aristidou & Lasenby, "FABRIK: A fast, iterative solver for the
    /// Inverse Kinematics problem" (2011). The two-pass forward-and-backward
    /// algorithm converges in 1–20 iterations for typical humanoid chains.
    ///
    /// Coordinate convention: the joints array is [root, mid..., tip], each joint
    /// is its WORLD position. The caller converts from / to Godot's bone-rotation
    /// representation at the boundary (see AriaIKController).
    /// </summary>
    public static class FabrikSolver
    {
        public const int DefaultMaxIterations = 12;
        public const float DefaultTolerance = 0.001f;

        /// <summary>
        /// Solve a chain so its tip reaches `target`. Joints are modified in place.
        /// Returns the number of iterations actually run, or -1 if the target is
        /// unreachable (longer than the chain's total length — we clamp gracefully).
        /// </summary>
        /// <param name="joints">J-by-3 world positions; joints[0] is the root (anchored),
        /// joints[^1] is the tip (tries to reach target). Mutated in place.</param>
        /// <param name="lengths">J-1 segment lengths (one per bone, root→tip).</param>
        /// <param name="target">World position the tip should reach.</param>
        /// <param name="poleHint">A point that the mid-joints should bias toward
        /// (e.g. the shoulder/elbow plane). Pass null to use the existing bend direction.</param>
        /// <param name="maxIter">Max iterations before giving up.</param>
        /// <param name="tolerance">Stop if the tip is within this distance of target (m).</param>
        /// <param name="anchorRoot">If true (default), joints[0] is pinned to its starting
        /// position. Set false to also move the root (e.g. for a free chain in the air).</param>
        public static int Solve(
            List<Vector3> joints,
            float[] lengths,
            Vector3 target,
            Vector3? poleHint = null,
            int maxIter = DefaultMaxIterations,
            float tolerance = DefaultTolerance,
            bool anchorRoot = true)
        {
            if (joints == null || joints.Count < 2 || lengths == null) return 0;
            if (lengths.Length != joints.Count - 1)
                throw new ArgumentException($"lengths.Length ({lengths.Length}) must equal joints.Count-1 ({joints.Count - 1})");

            float totalLength = 0f;
            for (int i = 0; i < lengths.Length; i++) totalLength += lengths[i];
            float rootToTarget = Vector3.Distance(joints[0], target);

            // If the target is unreachable, point the chain straight at it from the root.
            if (rootToTarget >= totalLength)
            {
                Vector3 dir = Vector3.Normalize(target - joints[0]);
                for (int i = 1; i < joints.Count; i++)
                    joints[i] = joints[i - 1] + dir * lengths[i - 1];
                return -1;
            }

            Vector3 root = joints[0];
            for (int iter = 0; iter < maxIter; iter++)
            {
                // ── Forward (tip-to-root): place tip at target, walk back ──
                joints[^1] = target;
                for (int i = joints.Count - 2; i >= 0; i--)
                {
                    Vector3 dir = Vector3.Normalize(joints[i] - joints[i + 1]);
                    joints[i] = joints[i + 1] + dir * lengths[i];
                }

                // ── Backward (root-to-tip): pin root, walk forward to target ──
                if (anchorRoot) joints[0] = root;
                for (int i = 1; i < joints.Count; i++)
                {
                    Vector3 dir = Vector3.Normalize(joints[i] - joints[i - 1]);
                    joints[i] = joints[i - 1] + dir * lengths[i - 1];
                }

                // ── Pole hint: nudge mid-joints to keep them on a consistent side ──
                if (poleHint.HasValue && joints.Count > 2)
                {
                    ApplyPoleHint(joints, root, poleHint.Value, anchorRoot);
                }

                // Convergence check
                if (Vector3.Distance(joints[^1], target) < tolerance) return iter + 1;
            }
            return maxIter;
        }

        /// <summary>
        /// Project each mid-joint onto the plane defined by (root, target, poleHint)
        /// at its current distance from root. This is a simple pole-correction
        /// (not the full CCD "elbow on plane" version, but cheap and stable for
        /// humanoid arms where the elbow/shoulder/hand plane is well-defined).
        /// </summary>
        private static void ApplyPoleHint(List<Vector3> joints, Vector3 root, Vector3 pole, bool anchorRoot)
        {
            // Plane normal: from root through pole (perpendicular to the root→target line is fine too)
            Vector3 chainDir = Vector3.Normalize(joints[^1] - root);
            Vector3 poleDir = Vector3.Normalize(pole - root);
            Vector3 planeNormal = Vector3.Normalize(Vector3.Cross(chainDir, poleDir));
            if (planeNormal.LengthSquared() < 1e-6f) return;   // collinear — no plane to project to

            // For each non-root, non-tip joint, project its position onto the plane
            // that contains (root, joint's-current-position, pole), so the joint stays
            // on the same side of the chain as the pole.
            for (int i = 1; i < joints.Count - 1; i++)
            {
                Vector3 j = joints[i];
                // Distance from j to the plane (root, poleDir as normal, but tilted to chain axis)
                // Simpler: rotate the joint's offset-from-root around the chain axis
                // until it aligns with the pole's offset-from-root.
                Vector3 fromRoot = j - root;
                float along = Vector3.Dot(fromRoot, chainDir);
                Vector3 perp = fromRoot - chainDir * along;
                Vector3 targetPerp = pole - root - chainDir * Vector3.Dot(pole - root, chainDir);
                if (targetPerp.LengthSquared() < 1e-6f) continue;
                targetPerp = Vector3.Normalize(targetPerp) * perp.Length();
                joints[i] = root + chainDir * along + targetPerp;
            }
        }

        /// <summary>
        /// Two-bone analytical solver (single elbow). Fast and exact for chains of
        /// exactly 2 segments (e.g. upper-arm + lower-arm, upper-leg + lower-leg).
        /// `target` is the tip position; `hint` is the desired elbow direction
        /// (e.g. backward-up for a relaxed arm, forward for reaching forward).
        /// </summary>
        public static bool SolveTwoBone(
            ref Vector3 root, ref Vector3 mid, ref Vector3 tip,
            Vector3 target, Vector3 hint, float upperLen, float lowerLen)
        {
            float rootToTarget = Vector3.Distance(root, target);
            float maxReach = upperLen + lowerLen;
            float minReach = Math.Abs(upperLen - lowerLen);

            // Clamp target inside the reachable shell
            if (rootToTarget > maxReach)
            {
                Vector3 dir = Vector3.Normalize(target - root);
                target = root + dir * (maxReach - 0.0001f);
                rootToTarget = maxReach - 0.0001f;
            }
            else if (rootToTarget < minReach)
            {
                if (rootToTarget < 1e-5f)
                {
                    // Degenerate — push the elbow straight up in the hint direction
                    mid = root + Vector3.Normalize(hint - root) * upperLen;
                    tip = mid + Vector3.Normalize(hint - root) * lowerLen;
                    return false;
                }
                Vector3 dir = Vector3.Normalize(target - root);
                target = root + dir * (minReach + 0.0001f);
                rootToTarget = minReach + 0.0001f;
            }

            // Law of cosines: angle at the root between root→target and root→mid
            float cosRoot = (upperLen * upperLen + rootToTarget * rootToTarget - lowerLen * lowerLen)
                          / (2f * upperLen * rootToTarget);
            cosRoot = Math.Clamp(cosRoot, -1f, 1f);
            float rootAngle = MathF.Acos(cosRoot);

            // Build the elbow plane: (root, target, hint) — if hint is on the
            // root→target line, default to "up" so we still get a valid plane.
            Vector3 toTarget = Vector3.Normalize(target - root);
            Vector3 toHint = hint - root;
            Vector3 perp = Vector3.Cross(toTarget, toHint);
            if (perp.LengthSquared() < 1e-6f)
            {
                // hint collinear with chain — pick a perpendicular to break the degeneracy
                perp = Math.Abs(toTarget.Y) < 0.99f
                    ? Vector3.Cross(toTarget, Vector3.UnitY)
                    : Vector3.Cross(toTarget, Vector3.UnitX);
            }
            Vector3 bendDir = Vector3.Normalize(perp);
            // Make sure the bend is on the hint's side
            if (Vector3.Dot(bendDir, toHint) < 0) bendDir = -bendDir;

            // Place mid at the right angle
            Vector3 toMid = toTarget * MathF.Cos(rootAngle) + bendDir * MathF.Sin(rootAngle);
            mid = root + toMid * upperLen;
            // Tip = mid + (target - mid).Normalized * lowerLen  (close to target, exact by construction)
            tip = mid + Vector3.Normalize(target - mid) * lowerLen;
            return true;
        }

        /// <summary>
        /// Compute the per-rotation needed to point one bone (parent→child) along
        /// a target direction in WORLD space. Used by the controller to convert
        /// the solved joint positions back into Godot bone rotations.
        /// </summary>
        public static Quaternion RotationFromTo(Vector3 from, Vector3 to, Quaternion parentRot)
        {
            Vector3 dir = Vector3.Normalize(to - from);
            Vector3 localDir = Vector3.Transform(Vector3.UnitY, Quaternion.Inverse(parentRot));
            return QuaternionFromTo(localDir, dir);
        }

        public static Quaternion QuaternionFromTo(Vector3 from, Vector3 to)
        {
            float d = Vector3.Dot(from, to);
            if (d >= 0.99999f) return Quaternion.Identity;
            if (d <= -0.99999f)
            {
                // 180° — pick any perpendicular axis
                Vector3 axis = Math.Abs(from.X) < 0.9f ? Vector3.UnitX : Vector3.UnitY;
                Vector3 perp = Vector3.Normalize(Vector3.Cross(from, axis));
                return Quaternion.CreateFromAxisAngle(perp, MathF.PI);
            }
            Vector3 cross = Vector3.Cross(from, to);
            var q = new Quaternion(cross.X, cross.Y, cross.Z, 1f + d);
            return Quaternion.Normalize(q);
        }
    }
}
