using System.Collections.Generic;

namespace Aria
{
    /// <summary>
    /// Catalogue of the kinematic chains we can drive on Aria's Mixamo skeleton.
    /// Each chain is an ORDERED list of bone names (root first, tip last).
    /// Bone names are the standard Mixamo "J_Bip_*" set used by both
    /// Ariaversion4.glb and the FBX animations built by AnimationBuilder.
    ///
    /// Why ordered lists (not graph traversal)? Mixamo's humanoid skeleton is a
    /// tree, but every interesting chain is a linear path from a parent to a
    /// descendant. Hardcoding the path is faster than runtime traversal and
    /// avoids ambiguity when the skeleton has multiple "valid" routes (e.g. the
    /// spine could go Hips→Spine OR Hips→Spine→UpperChest depending on the model).
    /// </summary>
    public static class AriaIKChains
    {
        // ── Body ─────────────────────────────────────────────────────────
        public static readonly string[] SpineChain = {
            "J_Bip_C_Hips", "J_Bip_C_Spine", "J_Bip_C_Chest", "J_Bip_C_UpperChest", "J_Bip_C_Neck", "J_Bip_C_Head"
        };
        // Spine "torso only" — useful for lean/twist without tilting the head
        public static readonly string[] TorsoChain = {
            "J_Bip_C_Hips", "J_Bip_C_Spine", "J_Bip_C_Chest", "J_Bip_C_UpperChest"
        };
        // Head/eyes chain — a 2-bone analytical chain for fast look-at
        public static readonly string[] HeadChain = {
            "J_Bip_C_UpperChest", "J_Bip_C_Neck", "J_Bip_C_Head"
        };

        // ── Arms ─────────────────────────────────────────────────────────
        public static readonly string[] LeftArmChain = {
            "J_Bip_L_Shoulder", "J_Bip_L_UpperArm", "J_Bip_L_LowerArm", "J_Bip_L_Hand"
        };
        public static readonly string[] RightArmChain = {
            "J_Bip_R_Shoulder", "J_Bip_R_UpperArm", "J_Bip_R_LowerArm", "J_Bip_R_Hand"
        };
        // Full arm including fingers tip — for grab/point at a precise world point
        public static readonly string[] LeftArmFullChain = {
            "J_Bip_L_Shoulder", "J_Bip_L_UpperArm", "J_Bip_L_LowerArm", "J_Bip_L_Hand",
            "J_Bip_L_Index1", "J_Bip_L_Index2", "J_Bip_L_Index3"
        };

        // ── Legs ─────────────────────────────────────────────────────────
        public static readonly string[] LeftLegChain = {
            "J_Bip_L_UpperLeg", "J_Bip_L_LowerLeg", "J_Bip_L_Foot", "J_Bip_L_ToeBase"
        };
        public static readonly string[] RightLegChain = {
            "J_Bip_R_UpperLeg", "J_Bip_R_LowerLeg", "J_Bip_R_Foot", "J_Bip_R_ToeBase"
        };

        // ── Fingers (10 chains; one per finger, root→tip) ────────────────
        public static readonly string[] ThumbL = { "J_Bip_L_Thumb1", "J_Bip_L_Thumb2", "J_Bip_L_Thumb3" };
        public static readonly string[] ThumbR = { "J_Bip_R_Thumb1", "J_Bip_R_Thumb2", "J_Bip_R_Thumb3" };
        public static readonly string[] IndexL = { "J_Bip_L_Index1", "J_Bip_L_Index2", "J_Bip_L_Index3" };
        public static readonly string[] IndexR = { "J_Bip_R_Index1", "J_Bip_R_Index2", "J_Bip_R_Index3" };
        public static readonly string[] MiddleL = { "J_Bip_L_Middle1", "J_Bip_L_Middle2", "J_Bip_L_Middle3" };
        public static readonly string[] MiddleR = { "J_Bip_R_Middle1", "J_Bip_R_Middle2", "J_Bip_R_Middle3" };
        public static readonly string[] RingL = { "J_Bip_L_Ring1", "J_Bip_L_Ring2", "J_Bip_L_Ring3" };
        public static readonly string[] RingR = { "J_Bip_R_Ring1", "J_Bip_R_Ring2", "J_Bip_R_Ring3" };
        public static readonly string[] LittleL = { "J_Bip_L_Little1", "J_Bip_L_Little2", "J_Bip_L_Little3" };
        public static readonly string[] LittleR = { "J_Bip_R_Little1", "J_Bip_R_Little2", "J_Bip_R_Little3" };

        /// <summary>Look up a chain by name (case-insensitive, accepts aliases).
        /// Returns null if the name is unknown.</summary>
        public static string[] Resolve(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            switch (name.Trim().ToLowerInvariant())
            {
                case "spine": case "body": case "full_spine": return SpineChain;
                case "torso": case "upper_body": return TorsoChain;
                case "head": case "neck": case "look": return HeadChain;
                case "arm_left": case "left_arm": case "l_arm": return LeftArmChain;
                case "arm_right": case "right_arm": case "r_arm": return RightArmChain;
                case "arm_left_full": case "left_arm_full": case "l_arm_full": return LeftArmFullChain;
                case "leg_left": case "left_leg": case "l_leg": return LeftLegChain;
                case "leg_right": case "right_leg": case "r_leg": return RightLegChain;
                case "thumb_l": case "thumb_left": return ThumbL;
                case "thumb_r": case "thumb_right": return ThumbR;
                case "index_l": case "index_left": return IndexL;
                case "index_r": case "index_right": return IndexR;
                case "middle_l": case "middle_left": return MiddleL;
                case "middle_r": case "middle_right": return MiddleR;
                case "ring_l": case "ring_left": return RingL;
                case "ring_r": case "ring_right": return RingR;
                case "pinky_l": case "little_l": case "pinky_left": return LittleL;
                case "pinky_r": case "little_r": case "pinky_right": return LittleR;
                default: return null;
            }
        }

        /// <summary>All chain names — for the LLM system prompt so it knows the vocabulary.</summary>
        public static readonly string[] AllNames = {
            "spine", "torso", "head",
            "arm_left", "arm_right", "arm_left_full",
            "leg_left", "leg_right",
            "thumb_l", "thumb_r", "index_l", "index_r", "middle_l", "middle_r", "ring_l", "ring_r", "pinky_l", "pinky_r"
        };
    }
}
