"""Find the armpit issue in v6 Sarah.

Hypothesis: when you did the rig, the shirt mesh and the arm mesh have
overlapping/duplicate geometry at the shoulder, but the arm mesh's
shoulder verts are 100% weighted to LeftShoulder bone, while the shirt
shoulder verts are weighted to Spine. When the arm raises, the shirt
verts don't follow, leaving a gap that the rig 'stretches' to close.

This script:
  1. Loads the v6 base GLB
  2. Looks at vertex positions in the shoulder Y range
  3. For verts in that range, looks at their JOINTS_0 weighting
  4. Tells us: is the shirt-vs-arm split happening in skin weights?
"""
from pygltflib import GLTF2
from pathlib import Path
import numpy as np
from collections import Counter

V6 = Path(r"C:\Users\Tench\Documents\AI Learning\astro_assistant\Meshy_AI_Female_Character_Rigg_biped version 6\Meshy_AI_Female_Character_Rigg_biped\Meshy_AI_Female_Character_Rigg_biped_Character_output.glb")

gltf = GLTF2().load(str(V6))

# Simpler approach: use trimesh for positions, then look at gltf skin via raw gltf parsing
import trimesh
scene = trimesh.load(str(V6), force='scene')
main = list(scene.geometry.values())[0]
v = main.vertices
print(f"Loaded {len(v)} verts")

# Get raw skin data from glb
import struct
with open(str(V6), 'rb') as f:
    data = f.read()
json_len = struct.unpack('<I', data[12:16])[0]
json_text = data[20:20+json_len].decode('utf-8')
import json as j
gltf_json = j.loads(json_text)

# Find accessor for JOINTS_0
prim_attrs = gltf_json['meshes'][0]['primitives'][0]['attributes']
joints_acc_idx = prim_attrs['JOINTS_0']
weights_acc_idx = prim_attrs['WEIGHTS_0']

acc_joints = gltf_json['accessors'][joints_acc_idx]
acc_weights = gltf_json['accessors'][weights_acc_idx]
print(f"\nJoints accessor: count={acc_joints['count']}, compType={acc_joints['componentType']}, type={acc_joints['type']}")
print(f"Weights accessor: count={acc_weights['count']}, compType={acc_weights['componentType']}, type={acc_weights['type']}")

# Get buffer view for joints
bv_joints = gltf_json['bufferViews'][acc_joints['bufferView']]
bv_weights = gltf_json['bufferViews'][acc_weights['bufferView']]

# Find BIN chunk offset
bin_offset_in_glb = 12 + 8 + json_len + 8  # skip JSON header + chunk header + BIN chunk header
joints_start = bin_offset_in_glb + bv_joints['byteOffset'] + acc_joints.get('byteOffset', 0)
weights_start = bin_offset_in_glb + bv_weights['byteOffset'] + acc_weights.get('byteOffset', 0)

# Joints are VEC4 of unsigned short (5123) or byte (5121)
joints_comp_size = 2 if acc_joints['componentType'] == 5123 else 1
joints_dtype = np.uint16 if acc_joints['componentType'] == 5123 else np.uint8
joints_raw = data[joints_start:joints_start + acc_joints['count'] * 4 * joints_comp_size]
joints_arr = np.frombuffer(joints_raw, dtype=joints_dtype).reshape(-1, 4)

weights_raw = data[weights_start:weights_start + acc_weights['count'] * 4 * 4]  # float32 VEC4
weights_arr = np.frombuffer(weights_raw, dtype=np.float32).reshape(-1, 4)

print(f"\nJoints array shape: {joints_arr.shape}")
print(f"Weights array shape: {weights_arr.shape}")

# Build joint name lookup
joint_names = ['Hips', 'Spine', 'Spine01', 'Spine02', 'neck', 'Head', 'head_end', 'headfront',
               'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand',
               'RightShoulder', 'RightArm', 'RightForeArm', 'RightHand',
               'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase',
               'RightUpLeg', 'RightLeg', 'RightFoot', 'RightToeBase']
# Actually, joints list is the order: index 0 = Hips, 1 = LeftUpLeg, etc.
# Let me build the right map
joint_node_indices = gltf.skins[0].joints
joint_name_map = {}
for ji in joint_node_indices:
    n = gltf.nodes[ji]
    joint_name_map[ji] = n.name
print(f"\nJoint index -> name map:")
for k, v_n in sorted(joint_name_map.items()):
    print(f"  joint[{k}] = {v_n}")

# OK now let's look at the shoulder region
# Find verts in shoulder Y range
print(f"\n--- Shoulder region analysis ---")
y_min, y_max = 1.10, 1.40  # approximate shoulder band
shoulder_verts = np.where((v[:,1] >= y_min) & (v[:,1] <= y_max))[0]
print(f"Verts in Y range [{y_min}, {y_max}]: {len(shoulder_verts)}")

# For each shoulder vert, what's its dominant joint?
dominant_joints = []
for vi in shoulder_verts:
    if weights_arr[vi].sum() < 0.01:
        dominant_joints.append('UNWEIGHTED')
        continue
    # Pick the joint with the highest weight
    top = np.argmax(weights_arr[vi])
    j_idx = joints_arr[vi][top]
    dominant_joints.append(joint_name_map.get(int(j_idx), f'joint{j_idx}'))

counts = Counter(dominant_joints)
print(f"\nDominant joint distribution in shoulder region:")
for j_name, c in counts.most_common():
    print(f"  {j_name}: {c} verts")

# Key check: do we have BOTH Spine-dominant AND LeftShoulder-dominant verts in the same Y range?
spine_verts = [vi for vi in shoulder_verts
               if 'Spine' in joint_name_map.get(int(joints_arr[vi][np.argmax(weights_arr[vi])]), '')]
shoulder_joint_verts = [vi for vi in shoulder_verts
                        if 'Shoulder' in joint_name_map.get(int(joints_arr[vi][np.argmax(weights_arr[vi])]), '')]
arm_joint_verts = [vi for vi in shoulder_verts
                   if 'Arm' in joint_name_map.get(int(joints_arr[vi][np.argmax(weights_arr[vi])]), '') or
                      'ForeArm' in joint_name_map.get(int(joints_arr[vi][np.argmax(weights_arr[vi])]), '') or
                      'Hand' in joint_name_map.get(int(joints_arr[vi][np.argmax(weights_arr[vi])]), '')]
print(f"\n--- Verdict ---")
print(f"  Spine-dominant verts in shoulder region:   {len(spine_verts)}")
print(f"  Shoulder-dominant verts in shoulder region: {len(shoulder_joint_verts)}")
print(f"  Arm/ForeArm/Hand-dominant verts in shoulder: {len(arm_joint_verts)}")
print(f"\nIf we see Spine and Shoulder/Arm verts in the same Y range,")
print(f"the shirt and arm meshes are competing for the same space.")
print(f"That's the source of the armpit stretching.")
