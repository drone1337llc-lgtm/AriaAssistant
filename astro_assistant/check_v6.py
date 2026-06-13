"""Quick check: does Meshy_AI_Female_Character_Rigg_biped version 6 have a rig?"""
from pygltflib import GLTF2
from pathlib import Path
import os

# Look for any .glb/.fbx inside the v6 folder
v6_dir = Path(r"C:\Users\Tench\Documents\AI Learning\astro_assistant\Meshy_AI_Female_Character_Rigg_biped version 6")
v6_fbx_dir = Path(r"C:\Users\Tench\Documents\AI Learning\astro_assistant\Meshy_AI_Female_Character_Rigg_biped fbx version6")

def scan(d):
    if not d.exists():
        print(f"  MISSING: {d.name}")
        return None
    files = list(d.rglob("*"))
    glbs = [f for f in files if f.suffix.lower() in {".glb", ".gltf"}]
    fbxs = [f for f in files if f.suffix.lower() in {".fbx", ".obj"}]
    images = [f for f in files if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".tga", ".exr"}]
    print(f"  {d.name}:")
    print(f"    glb/gltf: {[str(f.relative_to(d)) for f in glbs]}")
    print(f"    fbx/obj:  {[str(f.relative_to(d)) for f in fbxs]}")
    print(f"    images:   {len(images)} files")
    if images:
        total = sum(f.stat().st_size for f in images) / 1024 / 1024
        print(f"    image total: {total:.2f} MB")
        for f in images[:10]:
            print(f"      {f.name} ({f.stat().st_size / 1024:.0f} KB)")
    return glbs

print("=== V6 FOLDER ===")
glbs = scan(v6_dir)
print("\n=== V6 FBX FOLDER ===")
glbs_fbx = scan(v6_fbx_dir)

# If we found a GLB in v6, inspect it
if glbs:
    print(f"\n=== INSPECTING {glbs[0].name} ===")
    gltf = GLTF2().load(str(glbs[0]))
    print(f"  Nodes: {len(gltf.nodes or [])}")
    print(f"  Skins: {len(gltf.skins or [])}")
    print(f"  Animations: {len(gltf.animations or [])}")
    print(f"  Meshes: {len(gltf.meshes or [])}")
    print(f"  Materials: {len(gltf.materials or [])}")
    print(f"  Textures: {len(gltf.textures or [])}")
    if gltf.nodes:
        for i, n in enumerate(gltf.nodes[:20]):
            print(f"    node[{i}]: name='{n.name}' mesh={n.mesh} skin={n.skin}")
