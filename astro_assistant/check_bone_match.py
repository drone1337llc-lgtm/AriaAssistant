"""Diagnostic: dump all bone names in Aria and all bone names referenced in the FBX tracks."""
import re
from pathlib import Path

# Read the imported Aria scene's structure
aria_glb = Path(r'C:\Users\Tench\Documents\AriaCompanion\Aria.glb')
data = aria_glb.read_bytes()
strings = re.findall(rb'[A-Za-z_][A-Za-z0-9_]{2,40}', data)
unique = sorted(set(s.decode('ascii', errors='replace') for s in strings))

# Aria's actual bone names (from the inspection earlier)
aria_bones = {
    'J_Bip_C_Hips', 'J_Bip_C_Spine', 'J_Bip_C_Chest', 'J_Bip_C_UpperChest',
    'J_Bip_C_Neck', 'J_Bip_C_Head', 'J_Bip_L_Shoulder', 'J_Bip_L_UpperArm',
    'J_Bip_L_LowerArm', 'J_Bip_L_Hand', 'J_Bip_L_Index1', 'J_Bip_L_Index2', 'J_Bip_L_Index3',
    'J_Bip_L_Little1', 'J_Bip_L_Little2', 'J_Bip_L_Little3',
    'J_Bip_L_Middle1', 'J_Bip_L_Middle2', 'J_Bip_L_Middle3',
    'J_Bip_L_Ring1', 'J_Bip_L_Ring2', 'J_Bip_L_Ring3',
    'J_Bip_L_Thumb1', 'J_Bip_L_Thumb2', 'J_Bip_L_Thumb3',
    'J_Bip_L_UpperLeg', 'J_Bip_L_LowerLeg', 'J_Bip_L_Foot', 'J_Bip_L_ToeBase',
    'J_Bip_R_Shoulder', 'J_Bip_R_UpperArm', 'J_Bip_R_LowerArm', 'J_Bip_R_Hand',
    'J_Bip_R_Index1', 'J_Bip_R_Index2', 'J_Bip_R_Index3',
    'J_Bip_R_Little1', 'J_Bip_R_Little2', 'J_Bip_R_Little3',
    'J_Bip_R_Middle1', 'J_Bip_R_Middle2', 'J_Bip_R_Middle3',
    'J_Bip_R_Ring1', 'J_Bip_R_Ring2', 'J_Bip_R_Ring3',
    'J_Bip_R_Thumb1', 'J_Bip_R_Thumb2', 'J_Bip_R_Thumb3',
    'J_Bip_R_UpperLeg', 'J_Bip_R_LowerLeg', 'J_Bip_R_Foot', 'J_Bip_R_ToeBase',
}
print(f'Aria bones (from earlier inspection): {len(aria_bones)}')

# Now look at what the FBX Idle.fbx has as track target bones
# The FBX is binary so we need to look for any string that looks like a bone name
fbx = Path(r'C:\Users\Tench\Documents\AriaCompanion\ani\Idle.fbx')
fbx_data = fbx.read_bytes()
# Extract strings
fbx_strings = re.findall(rb'[A-Za-z_][A-Za-z0-9_]{2,40}', fbx_data)
fbx_unique = sorted(set(s.decode('ascii', errors='replace') for s in fbx_strings))

# Find J_Bip_ matches in FBX
fbx_j_bip = [s for s in fbx_unique if 'J_Bip_' in s]
print(f'\nFBX Idle.fbx bone-like names with J_Bip_: {len(fbx_j_bip)}')
for b in fbx_j_bip:
    print(f'  {b}')

# Find what tracks are in the imported FBX scene (after Godot import)
# The .scn file in .godot/imported/ has the track paths
import_dir = Path(r'C:\Users\Tench\Documents\AriaCompanion\.godot\imported')
idle_scn = import_dir / 'Idle.fbx-ee6d7cd180889f1831b1d2c6b8032162.scn'
if idle_scn.exists():
    # Read first 5MB looking for track paths
    scn_data = idle_scn.read_bytes()
    # Look for 'path' attribute values in the .tscn-like text portion
    # Actually .scn is binary. Let's look for likely bone names in the binary
    scn_strings = re.findall(rb'[A-Za-z_][A-Za-z0-9_/]{2,80}', scn_data)
    scn_unique = sorted(set(s.decode('ascii', errors='replace') for s in scn_strings))
    # Filter for things that look like NodePaths with J_Bip_
    paths = [s for s in scn_unique if 'J_Bip_' in s]
    print(f'\nImported Idle scene has {len(paths)} J_Bip_-containing strings:')
    for p in paths[:80]:
        print(f'  {p}')

# Cross-check: what bones does Aria have but the FBX does NOT?
aria_only = aria_bones - set(fbx_j_bip)
fbx_only = set(fbx_j_bip) - aria_bones
print(f'\nIn Aria but not in FBX: {len(aria_only)}')
for b in sorted(aria_only)[:20]:
    print(f'  {b}')
print(f'\nIn FBX but not in Aria: {len(fbx_only)}')
for b in sorted(fbx_only)[:20]:
    print(f'  {b}')
