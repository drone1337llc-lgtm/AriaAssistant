"""Inventory all Aria animation files with durations."""
from pygltflib import GLTF2
from pathlib import Path

base = Path(r'C:\Users\Tench\Desktop')
print('=== ARIA ANIMATION INVENTORY ===')
print()
print(f'{"ANIMATION":<55} {"DUR_SEC":<10} {"CHANNELS":<10}')
print('-' * 80)
for folder in sorted(base.glob('AriaPart*Animations')):
    print(f'\n--- {folder.name} ---')
    for glb in sorted(folder.glob('Meshy_AI_biped/*.glb')):
        g = GLTF2().load(str(glb))
        if g.animations:
            a = g.animations[0]
            dur = '-'
            try:
                acc = g.accessors[a.samplers[0].input]
                if acc.max and acc.min:
                    dur = f'{acc.max[0] - acc.min[0]:.2f}'
            except Exception:
                pass
            n_ch = len(a.channels or [])
            # Strip the prefix
            name = glb.stem.replace('Meshy_AI_biped_', '').replace('Animation_', '').replace('_withSkin', '')
            print(f'  {name:<53} {dur:<10} {n_ch:<10}')
