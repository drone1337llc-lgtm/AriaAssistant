"""Full inspection of the canonical Aria mesh (Ariamodel.glb)."""
from pygltflib import GLTF2
import struct
from pathlib import Path

p = Path(r'C:\Users\Tench\Desktop\Ariamodel.glb')
g = GLTF2().load(str(p))
print(f'File: {p.name}  Size: {p.stat().st_size / 1024 / 1024:.2f} MB')
print()
print(f'Meshes: {len(g.meshes)}')
print(f'Nodes: {len(g.nodes)}')
print(f'Skins: {len(g.skins)}')
print(f'Animations: {len(g.animations)}')
print(f'Materials: {len(g.materials)}')
print(f'Textures: {len(g.textures)}')
print()

# Scene tree
print('=== Scene tree ===')
def walk(idx, depth=0):
    if idx >= len(g.nodes): return
    n = g.nodes[idx]
    marker = ''
    if n.mesh is not None: marker += ' [MESH]'
    if n.skin is not None: marker += ' [SKIN]'
    print('  ' + '  ' * depth + f'[{idx}] {n.name}{marker}')
    for c in n.children or []:
        walk(c, depth+1)

if g.scenes:
    for sn in g.scenes[0].nodes:
        walk(sn)

# All node names
print('\n=== All node names ===')
for i, n in enumerate(g.nodes):
    print(f'  [{i}] {n.name}')

# Animation names
print('\n=== Animations ===')
for a in g.animations or []:
    print(f'  {a.name}  ({len(a.channels)} channels, {len(a.samplers)} samplers)')

# Get all positions of the main mesh
print('\n=== Mesh bounds (approximate) ===')
for mi, m in enumerate(g.meshes):
    for pi, p_ in enumerate(m.primitives):
        pos_attr = p_.attributes.POSITION
        if pos_attr is not None:
            acc = g.accessors[pos_attr]
            print(f'  mesh[{mi}].prim[{pi}]: {acc.count} verts, '
                  f'bbox y=[{acc.min[1]:.2f}, {acc.max[1]:.2f}], '
                  f'bbox x=[{acc.min[0]:.2f}, {acc.max[0]:.2f}], '
                  f'bbox z=[{acc.min[2]:.2f}, {acc.max[2]:.2f}]')
