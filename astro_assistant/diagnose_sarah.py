"""Full diagnostic on Sarah Version 7.glb - report on meshes, rigging, textures, topology."""
import trimesh
import numpy as np
import json
import sys
from pathlib import Path

GLB = Path(r"C:\Users\Tench\Documents\AI Learning\astro_assistant\Sarah Version 7.glb")

print(f"File: {GLB.name}")
print(f"Size: {GLB.stat().st_size / 1024 / 1024:.2f} MB")
print("=" * 70)

scene = trimesh.load(str(GLB), force='scene')

# Geometry summary
print("\n--- GEOMETRY ---")
print(f"Scene type: {type(scene).__name__}")
if hasattr(scene, 'geometry'):
    print(f"Number of named geometries: {len(scene.geometry)}")
    for name, mesh in scene.geometry.items():
        print(f"  '{name}': {len(mesh.vertices)} verts, {len(mesh.faces)} faces, "
              f"watertight={mesh.is_watertight}, euler={mesh.euler_number}")

# Whole-scene aggregate
if hasattr(scene, 'vertices'):
    all_v = scene.vertices
    print(f"\nTotal scene vertices: {len(all_v)}")
    print(f"Total scene faces:    {len(scene.faces) if hasattr(scene, 'faces') else 'N/A'}")
    print(f"Bounds (min/max): {all_v.min(axis=0).tolist()} / {all_v.max(axis=0).tolist()}")
    print(f"Height span: {all_v[:,1].max() - all_v[:,1].min():.3f}")

# Skin/animations
print("\n--- RIGGING (skin) ---")
try:
    # pyglet-style: scene.graph
    g = scene.graph
    print(f"Graph nodes: {len(g.nodes) if hasattr(g, 'nodes') else 'N/A'}")
    if hasattr(g, 'nodes'):
        for n in list(g.nodes)[:20]:
            print(f"  node: {n}")
except Exception as e:
    print(f"  (graph inspect failed: {e})")

# Trimesh scene metadata
try:
    meta = scene.metadata
    if meta:
        print(f"\nScene metadata keys: {list(meta.keys())[:30]}")
except Exception:
    pass

# Raw gltf inspection via the underlying dict if available
print("\n--- RAW GLTF STRUCTURE ---")
try:
    if hasattr(scene, '_source') and hasattr(scene.scene, '_source'):
        pass
    # try opening with pygltflib
    try:
        from pygltflib import GLTF2
        gltf = GLTF2().load(str(GLB))
        print(f"  gltf version: {gltf.asset.version if gltf.asset else 'N/A'}")
        print(f"  meshes: {len(gltf.meshes or [])}")
        for i, m in enumerate(gltf.meshes or []):
            n_prims = len(m.primitives or [])
            print(f"    mesh[{i}]: name='{m.name}', primitives={n_prims}")
        print(f"  skins: {len(gltf.skins or [])}")
        for i, s in enumerate(gltf.skins or []):
            joints = len(s.joints or [])
            print(f"    skin[{i}]: name='{s.name}', joints={joints}")
        print(f"  animations: {len(gltf.animations or [])}")
        for i, a in enumerate(gltf.animations or []):
            n_ch = sum(len(c.target.path or '') > 0 for c in (a.channels or []))
            print(f"    anim[{i}]: name='{a.name}', channels={n_ch}")
        print(f"  nodes: {len(gltf.nodes or [])}")
        print(f"  textures: {len(gltf.textures or [])}")
        print(f"  images: {len(gltf.images or [])}")
        for i, im in enumerate(gltf.images or []):
            uri = im.uri or 'buffer-view'
            print(f"    image[{i}]: {im.mimeType or '?'} ({uri[:60]})")
        print(f"  materials: {len(gltf.materials or [])}")
        for i, mat in enumerate(gltf.materials or []):
            print(f"    material[{i}]: name='{mat.name}'")
            if mat.pbrMetallicRoughness and mat.pbrMetallicRoughness.baseColorTexture:
                t = mat.pbrMetallicRoughness.baseColorTexture
                print(f"      baseColor -> tex index: {t.index}")
        print(f"  buffers: {len(gltf.buffers or [])}")
        for i, b in enumerate(gltf.buffers or []):
            print(f"    buffer[{i}]: {b.byteLength / 1024:.1f} KB, uri='{b.uri or 'external'}'")
    except ImportError:
        print("  (pygltflib not installed - skipping deep inspection)")
except Exception as e:
    print(f"  (raw gltf inspect failed: {e})")

# Component analysis
print("\n--- CONNECTED COMPONENTS ---")
if hasattr(scene, 'geometry'):
    for name, mesh in scene.geometry.items():
        try:
            comps = mesh.split(only_watertight=False)
            print(f"  '{name}': {len(comps)} components")
            for i, c in enumerate(sorted(comps, key=lambda m: -len(m.vertices))[:10]):
                print(f"    comp[{i}]: {len(c.vertices)} verts, watertight={c.is_watertight}, "
                      f"bounds y=[{c.bounds[0,1]:.2f}, {c.bounds[1,1]:.2f}]")
        except Exception as e:
            print(f"  (component split failed: {e})")
