"""Inspect the base Character_output.glb (no animation) from v6 - this should be our 'Sarah' canonical version."""
from pygltflib import GLTF2
from pathlib import Path
import trimesh
import numpy as np

CHAR_GLTF = Path(r"C:\Users\Tench\Documents\AI Learning\astro_assistant\Meshy_AI_Female_Character_Rigg_biped version 6\Meshy_AI_Female_Character_Rigg_biped\Meshy_AI_Female_Character_Rigg_biped_Character_output.glb")

print(f"File: {CHAR_GLTF.name}")
print(f"Size: {CHAR_GLTF.stat().st_size / 1024 / 1024:.2f} MB")
print("=" * 70)

gltf = GLTF2().load(str(CHAR_GLTF))

print(f"\nMeshes: {len(gltf.meshes or [])}")
print(f"Nodes: {len(gltf.nodes or [])}")
print(f"Skins: {len(gltf.skins or [])}")
print(f"Animations: {len(gltf.animations or [])}")
print(f"Materials: {len(gltf.materials or [])}")
print(f"Textures: {len(gltf.textures or [])}")
print(f"Images: {len(gltf.images or [])}")

print(f"\n--- All nodes ---")
for i, n in enumerate(gltf.nodes or []):
    print(f"  node[{i}]: name='{n.name}' mesh={n.mesh} skin={n.skin} children={n.children}")

print(f"\n--- Materials ---")
for i, m in enumerate(gltf.materials or []):
    print(f"  mat[{i}]: name='{m.name}'")
    if m.pbrMetallicRoughness:
        pbr = m.pbrMetallicRoughness
        bc = pbr.baseColorTexture
        print(f"    baseColor tex: {bc.index if bc else 'none'}")

print(f"\n--- Trimesh geometry ---")
try:
    scene = trimesh.load(str(CHAR_GLTF), force='scene')
    if hasattr(scene, 'geometry'):
        for name, mesh in scene.geometry.items():
            print(f"  '{name}': {len(mesh.vertices)} verts, {len(mesh.faces)} faces, "
                  f"watertight={mesh.is_watertight}, euler={mesh.euler_number}")
            try:
                comps = mesh.split(only_watertight=False)
                print(f"    components: {len(comps)}")
                comps_sorted = sorted(comps, key=lambda m: -len(m.vertices))[:5]
                for j, c in enumerate(comps_sorted):
                    print(f"      comp[{j}]: {len(c.vertices)} verts, "
                          f"watertight={c.is_watertight}, "
                          f"y_bounds=[{c.bounds[0,1]:.2f},{c.bounds[1,1]:.2f}]")
            except Exception as e:
                print(f"    (component split failed: {e})")
except Exception as e:
    print(f"  trimesh load failed: {e}")
