"""Parse a Godot 4 binary .scn file to extract node tree + animation info.
Godot 4 .scn format: starts with 'GDSC' magic, version, then a binary structure
with text strings.

Alternative: use Godot itself via headless mode. But that's overkill for this.
"""
import struct
from pathlib import Path

# Let's use a different approach: convert FBX to glTF using a free online tool?
# No, we need local. Let me just use the .import file + the assumption that
# the bone names follow the J_Bip_* standard (which we've already verified).

# Actually, the cleanest approach: have Godot do the import for us, and use
# Godot's runtime to do the bone-name remap. We don't need to parse FBX
# ourselves - we can just instance each imported FBX in the scene and use
# the AnimationPlayer's bone paths to map.

# But for now, the simplest verification: just check that the bone names in
# the FBX match Ariamodel.glb's bone names exactly.
# We already saw the FBX has J_Bip_C_Hips, J_Bip_L_UpperArm, etc.
# And Ariamodel.glb has J_Bip_C_Hips, J_Bip_L_UpperArm, etc.
# So names match - we're good.

# What we need: the Animation curves (keyframe data) for each bone.
# For that we need to parse the FBX AnimationStack / AnimationLayer / AnimationCurveNode structure.
#
# OR: we can do the merge entirely in Godot 4. Have Godot import the FBX,
# and use a C# script in Godot to extract the animation curves and copy
# them into a single AnimationLibrary.
#
# This is actually the SIMPLEST approach. Let me write a Godot C# tool script
# that does the merge at runtime/editor-time.

# But the user wanted a single Aria.glb they can drop into the project.
# So the cleanest path is:
# 1. Use a proper FBX-to-glTF converter (FBX2glTF, open source, ~10MB exe)
# 2. Parse the resulting glTF in Python (we know how to do this)
# 3. Merge into Aria.glb
#
# Let me check if FBX2glTF is available, or download it.

# Actually - since the bones match Aria's J_Bip_* exactly, and the user
# said the animations were made for Aria directly, the simplest possible
# approach is:
#
# Take the imported Aria.glb (from Ariamodel.glb) and merge the FBX animations
# by parsing the FBX files. The bones are the same. The skin weights are the
# same. The rest pose is the same. So the only thing different is the animation
# curves.

# Let me parse the FBX properly this time. The header is exactly 27 bytes.
# After that come top-level nodes: FBXHeaderExtension, GlobalSettings,
# Documents, References, Definitions, Objects, Connections.
# Each top-level node has: end_offset (uint32), num_props (uint32), prop_list_len (uint32), name_len (uint32), name.

print('Use a proper FBX library instead of a hand-rolled parser.')
print('Will install pyfbx-i42 or similar.')
