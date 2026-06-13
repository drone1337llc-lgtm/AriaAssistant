import struct, json
p = r'C:\Users\Tench\Documents\AI Learning\elven maiden\Meshy_AI_Arcane_Pedestal_in_th_0610005808_generate.glb'
with open(p, 'rb') as f:
    magic = f.read(4)
    ver = struct.unpack('<II', f.read(8))
    total_len = struct.unpack('<I', f.read(4))[0]
    chunk_len = struct.unpack('<I', f.read(4))[0]
    chunk_type = f.read(4)
    json_str = f.read(chunk_len).decode('utf-8', errors='replace')
data = json.loads(json_str)
print(f"Magic: {magic}")
print(f"Version: {ver}")
print(f"Total length: {total_len:,} bytes")
print(f"JSON chunk length: {chunk_len:,} bytes")
print(f"Asset version: {data.get('asset', {}).get('version', '?')}")
print(f"Generator: {data.get('asset', {}).get('generator', '?')}")
nodes = data.get('nodes', [])
meshes = data.get('meshes', [])
skins = data.get('skins', [])
animations = data.get('animations', [])
buffers = data.get('buffers', [])
bufferViews = data.get('bufferViews', [])
accessors = data.get('accessors', [])
print(f"Nodes: {len(nodes)}")
print(f"Meshes: {len(meshes)}")
print(f"Skins: {len(skins)}")
print(f"Animations: {len(animations)}")
print(f"Buffers: {len(buffers)}")
print(f"Buffer views: {len(bufferViews)}")
print(f"Accessors: {len(accessors)}")
if skins:
    s = skins[0]
    print(f"Skin[0] joints: {len(s.get('joints', []))}")
    print(f"Skin[0] skeleton root: node {s.get('skeleton', '?')}")
if animations:
    for i, a in enumerate(animations):
        print(f"Animation[{i}]: name='{a.get('name', '?')}' samplers={len(a.get('samplers', []))} channels={len(a.get('channels', []))}")
if meshes:
    for i, m in enumerate(meshes):
        prims = m.get('primitives', [])
        print(f"Mesh[{i}] '{m.get('name', '?')}': {len(prims)} primitives")
        for j, p in enumerate(prims):
            attrs = p.get('attributes', {})
            print(f"  Primitive[{j}]: attributes={list(attrs.keys())}, indices={'yes' if p.get('indices') is not None else 'no'}")
