"""
GLB auto-cleanup for the legs/feet issue.

What it does (safe operations only):
  1. Loads the GLB
  2. Splits the mesh into connected components
  3. Drops any component with < 50 vertices (assumed debris)
  4. Keeps the largest component (main body) + any components >= 50 verts
  5. Removes degenerate faces (area < 1e-10)
  6. Tries trimesh.repair.fill_holes for any small holes in the main body
  7. Reports what couldn't be auto-fixed (Euler number, remaining issues)
  8. Saves the cleaned result next to the original with _cleaned.glb suffix

What it does NOT do (needs Blender):
  - Fix non-manifold edges / self-intersections in the main body
  - Re-merge disconnected sub-meshes that should be part of the body
  - Fix skin weights / bone assignments
  - Re-topologize

Run:  python cleanup_mesh.py  path/to/model.glb
"""
import sys
import shutil
from pathlib import Path

import numpy as np
import trimesh


DEBRIS_VERT_THRESHOLD = 50   # components with fewer verts than this are dropped
DEGENERATE_AREA = 1e-10       # faces smaller than this are dropped


def load_main_mesh(path: Path) -> trimesh.Trimesh:
    """Load the first Trimesh geometry from the GLB (skips Points/Path objects)."""
    scene = trimesh.load(path, force="scene")
    for name, geom in scene.geometry.items():
        if isinstance(geom, trimesh.Trimesh):
            print(f"  Loaded geometry: {name!r}  ({len(geom.vertices):,} verts, {len(geom.faces):,} faces)")
            return geom
    raise ValueError("No Trimesh geometry found in GLB")


def split_and_filter(mesh: trimesh.Trimesh, vert_threshold: int = DEBRIS_VERT_THRESHOLD):
    """Split into connected components. Keep main body + any large accessories.
    Drop small debris."""
    components = mesh.split(only_watertight=False)
    keep = []
    drop = []
    for c in components:
        if len(c.vertices) >= vert_threshold:
            keep.append(c)
        else:
            drop.append(c)
    return keep, drop


def merge_components(components) -> trimesh.Trimesh:
    """Concatenate the kept components back into a single Trimesh."""
    if len(components) == 1:
        return components[0]
    return trimesh.util.concatenate(components)


def remove_degenerate_faces(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Drop faces with near-zero area (collapsed triangles)."""
    bad = np.where(mesh.area_faces < DEGENERATE_AREA)[0]
    if len(bad) == 0:
        return mesh
    keep_mask = np.ones(len(mesh.faces), dtype=bool)
    keep_mask[bad] = False
    print(f"  removing {len(bad)} degenerate face(s)")
    return mesh.update_faces(keep_mask)


def report(label, mesh: trimesh.Trimesh, original_size=None):
    print(f"\n--- {label} ---")
    print(f"  vertices:               {len(mesh.vertices):,}")
    print(f"  faces:                  {len(mesh.faces):,}")
    print(f"  is_watertight:          {mesh.is_watertight}")
    print(f"  is_winding_consistent:  {mesh.is_winding_consistent}")
    print(f"  euler_number:           {mesh.euler_number}  (2 = clean closed)")
    if original_size:
        d_v = original_size[0] - len(mesh.vertices)
        d_f = original_size[1] - len(mesh.faces)
        print(f"  delta:                  {d_v:+,} verts  {d_f:+,} faces")


def main(path):
    path = Path(path)
    print(f"=== Cleaning: {path.name} ===")
    print(f"  size: {path.stat().st_size / 1e6:.2f} MB")

    mesh = load_main_mesh(path)
    report("ORIGINAL", mesh, None)
    original_v = len(mesh.vertices)
    original_f = len(mesh.faces)

    # 1) Split into components
    print(f"\n[1/4] Splitting into connected components...")
    keep, drop = split_and_filter(mesh)
    print(f"  kept:    {len(keep)} component(s)")
    for i, c in enumerate(keep):
        print(f"    {i+1}. {len(c.vertices):,} verts, {len(c.faces):,} faces")
    print(f"  dropped: {len(drop)} debris component(s)")
    for i, c in enumerate(drop):
        bb = c.bounds
        center = (bb[0] + bb[1]) / 2
        size = bb[1] - bb[0]
        print(f"    {i+1}. {len(c.vertices):,} verts  center=({center[0]:+.2f},{center[1]:+.2f},{center[2]:+.2f})  size=({size[0]:.2f}x{size[1]:.2f}x{size[2]:.2f})")

    if not keep:
        print("  !! No components above threshold; nothing left to save.")
        return

    # 2) Merge back
    print(f"\n[2/4] Merging kept components...")
    mesh = merge_components(keep)
    report("AFTER MERGE", mesh, (original_v, original_f))

    # 3) Remove degenerate faces
    print(f"\n[3/4] Removing degenerate faces...")
    mesh = remove_degenerate_faces(mesh)
    report("AFTER DEGEN REMOVAL", mesh, (original_v, original_f))

    # 4) Try to fill small holes
    print(f"\n[4/4] Trying to fill small holes in the main body...")
    filled = 0
    try:
        # fill_holes expects a Trimesh with consistent winding
        # This will only succeed on small, simple holes
        filled = trimesh.repair.fill_holes(mesh)
        if filled:
            print(f"  ✓ fill_holes() returned True — some holes patched")
        else:
            print(f"  - fill_holes() returned False — no simple holes found or topology blocked repair")
    except Exception as e:
        print(f"  - fill_holes error: {e}")
    report("AFTER HOLE FILL", mesh, (original_v, original_f))

    # Final verdict
    print(f"\n=== Summary ===")
    print(f"  vertices:  {original_v:,} -> {len(mesh.vertices):,}  ({len(mesh.vertices)-original_v:+,})")
    print(f"  faces:     {original_f:,} -> {len(mesh.faces):,}  ({len(mesh.faces)-original_f:+,})")
    print(f"  watertight: {mesh.is_watertight}  |  winding: {mesh.is_winding_consistent}  |  euler: {mesh.euler_number}")
    if mesh.euler_number != 2:
        print(f"  !! euler != 2 — main body has {abs(mesh.euler_number-2)//2} 'handles' or holes that need manual repair in Blender")

    # 5) Save
    out_path = path.with_name(path.stem + "_cleaned.glb")
    print(f"\nSaving cleaned mesh to: {out_path}")
    mesh.export(str(out_path), file_type="glb")
    print(f"  size: {out_path.stat().st_size / 1e6:.2f} MB")
    print(f"\n>>> Manual repair in Blender is still required for:")
    print(f"    - Non-manifold edges / euler number issues (topology surgery)")
    print(f"    - Bone weight cleanup on the cleaned mesh")
    print(f"    - Any real legs/feet gaps that auto-fill couldn't handle")
    print(f"\n>>> Import both files into Blender:")
    print(f"    Original: {path}")
    print(f"    Cleaned:  {out_path}")
    print(f"    Diff the two to see exactly what got removed.")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Tench\Documents\AI Learning\astro_assistant\Meshy_AI_Sunlit_Temptation_0610024218_generate.glb"
    main(target)
