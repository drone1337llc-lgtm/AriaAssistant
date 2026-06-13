"""Check Aria's VRM bone names (which were Meshy-biped, but might have the J_Bip_ prefix too)."""
from pathlib import Path
import re

# Aria's current mesh: Aria.glb
aria_glb = Path(r'C:\Users\Tench\Documents\AriaCompanion\Aria.glb')
data = aria_glb.read_bytes()
print(f'Aria.glb size: {len(data) / 1024 / 1024:.2f} MB')

# Find likely bone names
strings = re.findall(rb'[A-Za-z][A-Za-z0-9_]{3,40}', data)
unique = sorted(set(s.decode('ascii', errors='replace') for s in strings))
bone_like = [s for s in unique if any(kw.lower() in s.lower() for kw in [
    'Hip', 'Spine', 'Head', 'Shoulder', 'Arm', 'Leg', 'Hand', 'Foot',
    'Thumb', 'Index', 'Middle', 'Ring', 'Pinky', 'mixamorig', 'Chest', 'Neck', 'Toe',
    'Root', 'Pelvis', 'Knee', 'Elbow', 'Wrist', 'Ankle', 'Finger', 'J_Bip', 'Bip'])]

print(f'Aria.glb bone-like names ({len(bone_like)}):')
for b in bone_like:
    print(f'  {b}')
