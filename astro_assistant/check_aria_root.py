"""Check Aria.glb root node transform."""
from pygltflib import GLTF2
from pathlib import Path

g = GLTF2().load(str(Path(r'C:\Users\Tench\Documents\AriaCompanion\Aria.glb')))
print('Scene roots:')
for sn in g.scenes[0].nodes:
    n = g.nodes[sn]
    trans = getattr(n, 'translation', None) or [0,0,0]
    rot = getattr(n, 'rotation', None) or [0,0,0,1]
    scale = getattr(n, 'scale', None) or [1,1,1]
    print(f'  [{sn}] {n.name}')
    print(f'    translation: {trans}')
    print(f'    rotation: {rot}')
    print(f'    scale: {scale}')

print('\nNode 162 (J_Bip_C_Hips):')
n = g.nodes[162]
trans = getattr(n, 'translation', None) or [0,0,0]
print(f'  name: {n.name}')
print(f'  translation: {trans}')

print('\nNode 167 (Armature, scene root):')
n = g.nodes[167]
trans = getattr(n, 'translation', None) or [0,0,0]
scale = getattr(n, 'scale', None) or [1,1,1]
print(f'  name: {n.name}')
print(f'  translation: {trans}')
print(f'  scale: {scale}')
