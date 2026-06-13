"""Peek inside a binary FBX to find bone names.
FBX binary format has: header (23 bytes) + node tree. Each node has a name property.
We can scan for the string 'Property' followed by 'Lcl Translation' to find skeleton nodes,
or just scan the whole binary for likely bone names.
"""
from pathlib import Path
import re

fbx = Path(r'C:\Users\Tench\Documents\AriaCompanion\ani\Idle.fbx')
data = fbx.read_bytes()
print(f'File: {fbx.name}  Size: {len(data) / 1024:.1f} KB')

# FBX binary format has node names as null-terminated UTF-8 strings
# Mixed in with binary data. Search for likely bone name patterns.
bone_keywords = ['Hips', 'Spine', 'Head', 'Shoulder', 'Arm', 'Leg', 'Hand', 'Foot',
                 'Thumb', 'Index', 'Middle', 'Ring', 'Pinky',
                 'mixamorig', 'Hip', 'Chest', 'Neck', 'Toe']
found = {}
for kw in bone_keywords:
    matches = [m.start() for m in re.finditer(kw.encode('ascii'), data)]
    if matches:
        found[kw] = len(matches)

print(f'\nBone keyword frequency:')
for kw, count in found.items():
    print(f'  {kw}: {count}')

# Extract all strings that look like bone names (4-30 chars, alphanumeric, with optional 'mixamorig' prefix)
# Scan for sequences of printable ASCII
strings = re.findall(rb'[A-Za-z][A-Za-z0-9_]{3,40}', data)
unique = sorted(set(s.decode('ascii', errors='replace') for s in strings))

# Filter for likely-bone names
bone_like = [s for s in unique if any(kw.lower() in s.lower() for kw in [
    'Hip', 'Spine', 'Head', 'Shoulder', 'Arm', 'Leg', 'Hand', 'Foot',
    'Thumb', 'Index', 'Middle', 'Ring', 'Pinky', 'mixamorig', 'Chest', 'Neck', 'Toe',
    'Root', 'Pelvis', 'Knee', 'Elbow', 'Wrist', 'Ankle', 'Finger'])]

print(f'\nLikely bone names ({len(bone_like)}):')
for b in bone_like[:60]:
    print(f'  {b}')
