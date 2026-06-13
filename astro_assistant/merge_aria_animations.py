"""Merge multiple Aria animation GLBs into a single GLB with multiple named animations.

Bug fix: this version tracks which bufferViews are newly added, so at the end
we can correctly shift their byteOffset to account for the base bin being
prepended to the combined BIN chunk.
"""
import struct
import json
import numpy as np
from pathlib import Path
from pygltflib import GLTF2

# ── Configuration ──────────────────────────────────────────────────
BASE_FILE = Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Character_output.glb')
OUTPUT_FILE = Path(r'C:\Users\Tench\Documents\AriaCompanion\Aria.glb')

ANIM_SOURCES = {
    'idle':        Path(r'C:\Users\Tench\Desktop\AriaPartThreeAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Sit_Cross_Legged_withSkin.glb'),
    'walk':        Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Walking_withSkin.glb'),
    'climb':       Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_climbing_up_wall_withSkin.glb'),
    'fall':        Path(r'C:\Users\Tench\Desktop\AriaPartTwoAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Fall2_withSkin.glb'),
    'surprised':   Path(r'C:\Users\Tench\Desktop\AriaPartTwoAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Hop_with_Arms_Raised_withSkin.glb'),
    'react':       Path(r'C:\Users\Tench\Desktop\AriaPartFourAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Wave_for_Help_4_withSkin.glb'),
}

EXTRA_ANIMS = {
    'sit_doze':    Path(r'C:\Users\Tench\Desktop\AriaPartThreeAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Sit_and_Doze_Off_withSkin.glb'),
    'running':     Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Running_withSkin.glb'),
    'walking_w':   Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Walking_Woman_withSkin.glb'),
    'excited_walk':Path(r'C:\Users\Tench\Desktop\AriaPartTwoAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Excited_Walk_F_withSkin.glb'),
    'climb_down':  Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_climbing_down_wall_withSkin.glb'),
    'climb_left':  Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Climb_Left_with_Both_Limbs_inplace_withSkin.glb'),
    'fall_long':   Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Fall4_withSkin.glb'),
    'jump':        Path(r'C:\Users\Tench\Desktop\AriaPartTwoAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Jumping_Down_withSkin.glb'),
    'leap':        Path(r'C:\Users\Tench\Desktop\AriaPartTwoAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Leap_of_Faith_withSkin.glb'),
    'talk_passion':Path(r'C:\Users\Tench\Desktop\AriaPartFourAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Talk_Passionately_withSkin.glb'),
    'talk_hip':    Path(r'C:\Users\Tench\Desktop\AriaPartFourAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Talk_with_Left_Hand_on_Hip_withSkin.glb'),
    'talk_raised': Path(r'C:\Users\Tench\Desktop\AriaPartFourAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Talk_with_Left_Hand_Raised_withSkin.glb'),
    'walk_turn':   Path(r'C:\Users\Tench\Desktop\AriaPartFourAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Walk_Turn_Right_Female_withSkin.glb'),
    'you_groove':  Path(r'C:\Users\Tench\Desktop\AriaPartFourAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_You_Groove_withSkin.glb'),
    'chair_sit':   Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Chair_Sit_Idle_F_withSkin.glb'),
    'sit_to_stand':Path(r'C:\Users\Tench\Desktop\AriaPartThreeAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Sit_to_Stand_Transition_F_withSkin.glb'),
    'swim_idle':   Path(r'C:\Users\Tench\Desktop\AriaPartThreeAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Swim_Idle_withSkin.glb'),
    'swim_fwd':    Path(r'C:\Users\Tench\Desktop\AriaPartThreeAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Swim_Forward_withSkin.glb'),
    'dive':        Path(r'C:\Users\Tench\Desktop\AriaPartOneAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Dive_Down_and_Land_2_withSkin.glb'),
    'mirror':      Path(r'C:\Users\Tench\Desktop\AriaPartThreeAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Mirror_Viewing_withSkin.glb'),
    'walk_to_sit': Path(r'C:\Users\Tench\Desktop\AriaPartFourAnimations\Meshy_AI_biped\Meshy_AI_biped_Animation_Walk_to_Sit_withSkin.glb'),
}


def read_glb(path: Path):
    """Read a GLB file, return (json_dict, binary_blob)."""
    with open(path, 'rb') as f:
        data = f.read()
    magic = data[:4]
    if magic != b'glTF':
        raise ValueError(f'{path} is not a GLB')
    version, length = struct.unpack('<II', data[4:12])
    json_len, json_type = struct.unpack('<II', data[12:20])
    if json_type != 0x4E4F534A:
        raise ValueError(f'{path} first chunk is not JSON')
    json_text = data[20:20+json_len].decode('utf-8')
    json_dict = json.loads(json_text)
    bin_offset = 20 + json_len
    bin_len, bin_type = struct.unpack('<II', data[bin_offset:bin_offset+8])
    if bin_type != 0x004E4942:
        raise ValueError(f'{path} second chunk is not BIN')
    bin_blob = data[bin_offset+8:bin_offset+8+bin_len]
    return json_dict, bin_blob


def read_glb_bytes_safe(path: Path):
    """Alias for read_glb."""
    return read_glb(path)


def write_glb(out_path: Path, json_dict: dict, bin_blob: bytes):
    """Write a GLB file from a json dict and a binary blob."""
    json_text = json.dumps(json_dict, separators=(',', ':')).encode('utf-8')
    while len(json_text) % 4 != 0:
        json_text += b' '
    bin_padded = bin_blob
    while len(bin_padded) % 4 != 0:
        bin_padded += b'\x00'
    json_chunk_header = struct.pack('<II', len(json_text), 0x4E4F534A)
    bin_chunk_header = struct.pack('<II', len(bin_padded), 0x004E4942)
    total_length = 12 + 8 + len(json_text) + 8 + len(bin_padded)
    glb_header = struct.pack('<III', 0x46546C67, 2, total_length)
    with open(out_path, 'wb') as f:
        f.write(glb_header)
        f.write(json_chunk_header)
        f.write(json_text)
        f.write(bin_chunk_header)
        f.write(bin_padded)
    print(f'Wrote {out_path} ({out_path.stat().st_size / 1024 / 1024:.2f} MB)')


def main():
    print('=== Reading canonical Aria base ===')
    base_json, base_bin = read_glb_bytes_safe(BASE_FILE)
    print(f'  base: {len(base_json["nodes"])} nodes, {len(base_json["meshes"])} meshes, '
          f'buffer {len(base_bin)} bytes')

    # Track new bufferView indices so we can shift their offsets at the end
    new_bv_indices = set()
    appended_data = bytearray()  # only the NEW data, will be appended after base_bin

    def append_bv_data(raw: bytes) -> int:
        """Append raw bytes to appended_data, return offset in appended_data."""
        # Pad to 4-byte boundary
        while len(appended_data) % 4 != 0:
            appended_data.append(0)
        offset = len(appended_data)
        appended_data.extend(raw)
        return offset

    new_animations = []

    def add_animation(src_path: Path, new_name: str):
        nonlocal new_bv_indices
        print(f'\n  [{new_name}] <- {src_path.name}')
        src_json, src_bin = read_glb_bytes_safe(src_path)

        if not src_json.get('animations'):
            print(f'    !! no animations in source, skipping')
            return
        src_anim = src_json['animations'][0]
        n_ch = len(src_anim.get('channels', []))
        n_samp = len(src_anim.get('samplers', []))
        print(f'    source: {n_ch} channels, {n_samp} samplers, name="{src_anim.get("name")}"')

        # Node remap by name
        src_node_names = [n.get('name', '') for n in src_json.get('nodes', [])]
        base_node_names = [n.get('name', '') for n in base_json.get('nodes', [])]
        node_remap = {}
        for src_i, n in enumerate(src_json.get('nodes', [])):
            src_name = n.get('name', '')
            if src_name in base_node_names:
                node_remap[src_i] = base_node_names.index(src_name)
            else:
                if src_i < len(base_json.get('nodes', [])):
                    node_remap[src_i] = src_i

        # Find all unique accessor indices used
        used_accs = set()
        for s in src_anim.get('samplers', []):
            used_accs.add(s['input'])
            used_accs.add(s['output'])

        # Copy each used accessor: create new bufferView + accessor
        acc_remap = {}
        for src_acc_i in used_accs:
            src_acc = src_json['accessors'][src_acc_i]
            src_bv_i = src_acc['bufferView']
            src_bv = src_json['bufferViews'][src_bv_i]

            src_offset = src_bv.get('byteOffset', 0) + src_acc.get('byteOffset', 0)
            acc_count = src_acc['count']
            comp_size = {
                5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4
            }[src_acc['componentType']]
            elem_size = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[src_acc['type']]
            acc_byte_len = acc_count * comp_size * elem_size
            raw = src_bin[src_offset:src_offset+acc_byte_len]

            # Append data to the appended bin, get the offset (within appended_data)
            new_bv_offset = append_bv_data(raw)

            # Create new bufferView
            new_bv_i = len(base_json.setdefault('bufferViews', []))
            new_bv = {
                'buffer': 0,
                'byteOffset': new_bv_offset,  # temporarily, will be shifted later
                'byteLength': acc_byte_len,
                'target': 34962,
            }
            base_json['bufferViews'].append(new_bv)
            new_bv_indices.add(new_bv_i)

            # Create new accessor
            new_acc_i = len(base_json.setdefault('accessors', []))
            new_acc = {
                'bufferView': new_bv_i,
                'byteOffset': 0,
                'componentType': src_acc['componentType'],
                'count': acc_count,
                'type': src_acc['type'],
            }
            if 'min' in src_acc:
                new_acc['min'] = src_acc['min']
            if 'max' in src_acc:
                new_acc['max'] = src_acc['max']
            if 'normalized' in src_acc:
                new_acc['normalized'] = src_acc['normalized']
            base_json['accessors'].append(new_acc)
            acc_remap[src_acc_i] = new_acc_i

        # Build new channels and samplers
        new_channels = []
        new_samplers = []
        samp_remap = {}
        for src_samp_i, src_samp in enumerate(src_anim.get('samplers', [])):
            new_samp = {
                'input': acc_remap[src_samp['input']],
                'output': acc_remap[src_samp['output']],
            }
            if 'interpolation' in src_samp:
                new_samp['interpolation'] = src_samp['interpolation']
            new_samp_i = len(new_samplers)
            new_samplers.append(new_samp)
            samp_remap[src_samp_i] = new_samp_i

        for src_ch in src_anim.get('channels', []):
            src_target = src_ch['target']
            src_node = src_target.get('node', 0)
            new_node = node_remap.get(src_node, src_node)
            new_ch = {
                'sampler': samp_remap[src_ch['sampler']],
                'target': {
                    'node': new_node,
                    'path': src_target.get('path', 'translation'),
                },
            }
            new_channels.append(new_ch)

        new_anim = {
            'name': new_name,
            'channels': new_channels,
            'samplers': new_samplers,
        }
        new_animations.append(new_anim)
        print(f'    added: {len(new_channels)} channels, {len(new_samplers)} samplers')

    # Process the controller-required animations
    print('\n=== Adding controller-required animations ===')
    for name, src in ANIM_SOURCES.items():
        if src.exists():
            add_animation(src, name)
        else:
            print(f'  [{name}] source not found: {src}')

    # Process the extras
    print('\n=== Adding extra animations ===')
    for name, src in EXTRA_ANIMS.items():
        if src.exists() and src not in [s for s in ANIM_SOURCES.values()]:
            add_animation(src, name)

    # Replace the base's animations with the new set
    base_json['animations'] = new_animations

    # NOW the critical fix: shift new bufferView byteOffsets by base_bin length
    # so they point into the combined bin (which will be base_bin + appended_data)
    base_bin_len = len(base_bin)
    print(f'\n=== Shifting {len(new_bv_indices)} new bufferView offsets by {base_bin_len} ===')
    for bv_i in new_bv_indices:
        bv = base_json['bufferViews'][bv_i]
        old_off = bv['byteOffset']
        bv['byteOffset'] = old_off + base_bin_len

    # Update the base buffer's byteLength to include the appended data
    if base_json.get('buffers'):
        base_json['buffers'][0]['byteLength'] = base_bin_len + len(appended_data)

    # Remove the _bin_blob injection if present
    base_json.pop('_bin_blob', None)

    # Build the combined BIN: base_bin + appended_data (with padding to 4-byte boundary)
    final_bin = base_bin + bytes(appended_data)
    # Pad to 4-byte boundary
    while len(final_bin) % 4 != 0:
        final_bin += b'\x00'

    write_glb(OUTPUT_FILE, base_json, final_bin)
    print(f'\nFinal animations in Aria.glb: {len(new_animations)}')
    for a in new_animations:
        print(f'  - {a["name"]} ({len(a["channels"])} channels)')


if __name__ == '__main__':
    main()
