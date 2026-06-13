"""Direct pygltflib inspection of Sarah Version 7.glb."""
from pygltflib import GLTF2
import json
from pathlib import Path

GLB = Path(r"C:\Users\Tench\Documents\AI Learning\astro_assistant\Sarah Version 7.glb")

gltf = GLTF2().load(str(GLB))

print(f"File: {GLB.name}")
print(f"Size: {GLB.stat().st_size / 1024 / 1024:.2f} MB")
print("=" * 70)

print(f"\nAsset version: {gltf.asset.version if gltf.asset else 'N/A'}")
print(f"Asset generator: {gltf.asset.generator if gltf.asset else 'N/A'}")

print(f"\n--- MESHES ({len(gltf.meshes or [])}) ---")
for i, m in enumerate(gltf.meshes or []):
    n_prims = len(m.primitives or [])
    print(f"  mesh[{i}]: name='{m.name}', primitives={n_prims}")
    for j, p in enumerate(m.primitives or []):
        attrs = list(p.attributes.__dict__.keys()) if p.attributes else []
        print(f"    prim[{j}]: mode={p.mode}, attrs={attrs}")

print(f"\n--- SKINS ({len(gltf.skins or [])}) ---")
for i, s in enumerate(gltf.skins or []):
    print(f"  skin[{i}]: name='{s.name}', joints={len(s.joints or [])}")
    if s.joints:
        # Map joint indices to node names
        joint_names = []
        for ji in s.joints[:20]:
            if ji < len(gltf.nodes):
                joint_names.append(gltf.nodes[ji].name or f"node{ji}")
        print(f"    joint names (first 20): {joint_names}")

print(f"\n--- ANIMATIONS ({len(gltf.animations or [])}) ---")
for i, a in enumerate(gltf.animations or []):
    n_ch = len(a.channels or [])
    n_samp = len(a.samplers or [])
    print(f"  anim[{i}]: name='{a.name}', channels={n_ch}, samplers={n_samp}")
    if a.channels:
        for c in a.channels[:10]:
            target = c.target
            node_name = gltf.nodes[target.node].name if target.node < len(gltf.nodes) else f"node{target.node}"
            print(f"    channel: node='{node_name}' path='{target.path}'")

print(f"\n--- NODES ({len(gltf.nodes or [])}) ---")
for i, n in enumerate(gltf.nodes or []):
    extras = n.extras
    skin_idx = n.skin
    mesh_idx = n.mesh
    children = n.children or []
    print(f"  node[{i}]: name='{n.name}', mesh={mesh_idx}, skin={skin_idx}, children={children}")

print(f"\n--- TEXTURES ({len(gltf.textures or [])}) ---")
for i, t in enumerate(gltf.textures or []):
    print(f"  tex[{i}]: source={t.source}, sampler={t.sampler}")

print(f"\n--- IMAGES ({len(gltf.images or [])}) ---")
for i, im in enumerate(gltf.images or []):
    print(f"  image[{i}]: mime='{im.mimeType}', uri='{(im.uri or 'buffer-view')[:80]}'")

print(f"\n--- MATERIALS ({len(gltf.materials or [])}) ---")
for i, mat in enumerate(gltf.materials or []):
    print(f"  mat[{i}]: name='{mat.name}'")
    if mat.pbrMetallicRoughness:
        pbr = mat.pbrMetallicRoughness
        bc = pbr.baseColorTexture
        mr = pbr.metallicRoughnessTexture
        nm = mat.normalTexture
        em = mat.emissiveTexture
        oc = mat.occlusionTexture
        print(f"    baseColor: {bc.index if bc else 'N/A'}, metallicRoughness: {mr.index if mr else 'N/A'}")
        print(f"    normal: {nm.index if nm else 'N/A'}, emissive: {em.index if em else 'N/A'}, occlusion: {oc.index if oc else 'N/A'}")

print(f"\n--- BUFFERS ({len(gltf.buffers or [])}) ---")
for i, b in enumerate(gltf.buffers or []):
    print(f"  buffer[{i}]: {b.byteLength / 1024 / 1024:.2f} MB, uri='{b.uri or 'external'}'")

print(f"\n--- BUFFER VIEWS ({len(gltf.bufferViews or [])}) ---")
for i, bv in enumerate(gltf.bufferViews or []):
    print(f"  bv[{i}]: buffer={bv.buffer}, offset={bv.offset}, length={bv.byteLength}, target={bv.target}")

# Check if there are any accessors pointing at skin data
print(f"\n--- ACCESSORS (sample) ---")
if gltf.accessors:
    for i, a in enumerate(gltf.accessors[:20]):
        print(f"  acc[{i}]: type={a.type}, compType={a.componentType}, count={a.count}, "
              f"min={[f'{x:.2f}' for x in (a.min or [])]}, max={[f'{x:.2f}' for x in (a.max or [])]}")
    if len(gltf.accessors) > 20:
        print(f"  ... and {len(gltf.accessors) - 20} more")
