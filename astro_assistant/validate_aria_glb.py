"""Validate Aria.glb structure against GLB spec."""
from pygltflib import GLTF2
import struct
from pathlib import Path

p = Path(r'C:\Users\Tench\Documents\AriaCompanion\Aria.glb')
print(f'File: {p.name}  Size: {p.stat().st_size} bytes')
print()

# Read the raw GLB and validate structure
with open(p, 'rb') as f:
    data = f.read()

# GLB header
magic = data[:4]
version, total_length = struct.unpack('<II', data[4:12])
print(f'Magic: {magic}  Version: {version}  Total length: {total_length}  Actual: {len(data)}')
print()

# JSON chunk
json_len, json_type = struct.unpack('<II', data[12:20])
json_type_str = {0x4E4F534A: 'JSON', 0x004E4942: 'BIN'}.get(json_type, f'0x{json_type:08x}')
print(f'Chunk 1: type={json_type_str}  length={json_len}')
import json
json_text = data[20:20+json_len].decode('utf-8')
j = json.loads(json_text)
asset = j.get('asset', {})
print(f'  asset.version: {asset.get("version")}')
print(f'  asset.generator: {asset.get("generator")}')
print(f'  scenes: {len(j.get("scenes", []))}')
print(f'  nodes: {len(j.get("nodes", []))}')
print(f'  meshes: {len(j.get("meshes", []))}')
print(f'  animations: {len(j.get("animations", []))}')
print(f'  buffers: {len(j.get("buffers", []))}')
for i, b in enumerate(j.get('buffers', [])):
    print(f'    buffer[{i}]: byteLength={b["byteLength"]}, uri={b.get("uri")!r}')
print(f'  bufferViews: {len(j.get("bufferViews", []))}')
print(f'  accessors: {len(j.get("accessors", []))}')

# BIN chunk
bin_offset = 20 + json_len
bin_len, bin_type = struct.unpack('<II', data[bin_offset:bin_offset+8])
bin_type_str = {0x4E4F534A: 'JSON', 0x004E4942: 'BIN'}.get(bin_type, f'0x{bin_type:08x}')
print(f'Chunk 2: type={bin_type_str}  length={bin_len}')
print(f'  Expected file size: {12 + 8 + json_len + 8 + bin_len}')
print(f'  Actual file size:   {len(data)}')
print(f'  Match: {12 + 8 + json_len + 8 + bin_len == len(data)}')

# Check for bufferView 0 to verify buffer offset
if j.get('bufferViews'):
    bv0 = j['bufferViews'][0]
    print(f'\nbufferView[0]: buffer={bv0["buffer"]} byteOffset={bv0.get("byteOffset")} byteLength={bv0["byteLength"]}')

# Now try loading with pygltflib
print('\n--- pygltflib load test ---')
try:
    g = GLTF2().load(str(p))
    print(f'  loaded OK')
    print(f'  has {len(g.animations)} animations')
except Exception as e:
    print(f'  load failed: {e}')

# Try opening as gltf 2.0
print('\n--- spec checks ---')
# glTF 2.0 spec: byte alignment - bufferView byteOffset must be 4-aligned
bad_offsets = []
for i, bv in enumerate(j.get('bufferViews', [])):
    off = bv.get('byteOffset', 0)
    if off % 4 != 0:
        bad_offsets.append((i, off))
print(f'  bufferViews with non-4-aligned byteOffset: {len(bad_offsets)}')
if bad_offsets:
    for i, off in bad_offsets[:5]:
        print(f'    bv[{i}]: offset={off}')

# accessor byteOffset alignment
bad_acc = []
for i, acc in enumerate(j.get('accessors', [])):
    off = acc.get('byteOffset', 0)
    if off % 4 != 0:
        bad_acc.append((i, off, acc.get('componentType'), acc.get('type')))
print(f'  accessors with non-4-aligned byteOffset: {len(bad_acc)}')
if bad_acc:
    for i, off, ct, t in bad_acc[:5]:
        print(f'    acc[{i}]: offset={off}, compType={ct}, type={t}')
