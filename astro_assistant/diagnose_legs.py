"""
GLB mesh diagnostic using trimesh's loader (no hand-rolled GLB parsing).
Reports: structure, per-mesh integrity, connected components, bbox info.
"""
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import trimesh


def diagnose_mesh(label, mesh: trimesh.Trimesh):
    print(f"\n--- Mesh: {label!r} ---")
    print(f"  vertices:               {len(mesh.vertices):,}")
    print(f"  faces:                  {len(mesh.faces):,}")
    print(f"  is_watertight:          {mesh.is_watertight}")
    print(f"  is_winding_consistent:  {mesh.is_winding_consistent}")
    print(f"  euler_number:           {mesh.euler_number}  (2 for closed genus-0)")
    try:
        vol = mesh.volume
        print(f"  volume:                 {vol:.4f}")
    except Exception:
        print(f"  volume:                 (n/a — not closed)")
    try:
        broken = trimesh.repair.broken_faces(mesh)
        if len(broken) > 0:
            print(f"  broken_faces:           {len(broken)} (non-manifold edges)")
    except Exception as e:
        print(f"  broken_faces check:     {e}")
    degenerate = np.where(mesh.area_faces < 1e-10)[0]
    if len(degenerate) > 0:
        print(f"  degenerate_faces:       {len(degenerate)} (area < 1e-10)")

    # Disconnected components — the smoking gun for "unmeshed legs/feet"
    try:
        components = mesh.split(only_watertight=False)
        if len(components) > 1:
            print(f"  *** UNMESHED: {len(components)} disconnected components ***")
            for i, c in enumerate(components):
                bb = c.bounds  # (2, 3) array
                center = (bb[0] + bb[1]) / 2
                size = bb[1] - bb[0]
                print(f"      comp {i+1}: {len(c.vertices):>6,} verts  {len(c.faces):>6,} faces"
                      f"   center=({center[0]:+.2f},{center[1]:+.2f},{center[2]:+.2f})"
                      f"   size=({size[0]:.2f}x{size[1]:.2f}x{size[2]:.2f})")
        else:
            print(f"  components:  1 (single connected mesh — good)")
    except Exception as e:
        print(f"  split check: {e}")

    if len(mesh.vertices) > 0:
        bb_min = mesh.vertices.min(axis=0)
        bb_max = mesh.vertices.max(axis=0)
        center = (bb_min + bb_max) / 2
        size = bb_max - bb_min
        print(f"  bbox min:    ({bb_min[0]:+.2f}, {bb_min[1]:+.2f}, {bb_min[2]:+.2f})")
        print(f"  bbox max:    ({bb_max[0]:+.2f}, {bb_max[1]:+.2f}, {bb_max[2]:+.2f})")
        print(f"  center:      ({center[0]:+.2f}, {center[1]:+.2f}, {center[2]:+.2f})")
        print(f"  size:        {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f}")


def main(path):
    path = Path(path)
    print(f"=== Inspecting: {path.name} ===")
    print(f"  size: {path.stat().st_size / 1e6:.2f} MB")

    scene = trimesh.load(path, force="scene")
    print(f"\n  geometries: {len(scene.geometry)}")
    for name in scene.geometry:
        print(f"    - {name!r}")

    # Inspect each geometry directly
    print(f"\n[Per-mesh diagnostics]")
    for name, geom in scene.geometry.items():
        if isinstance(geom, trimesh.Trimesh):
            diagnose_mesh(name, geom)
        else:
            print(f"\n--- Geometry {name!r}: type={type(geom).__name__} (skipping) ---")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Tench\Documents\AI Learning\astro_assistant\Meshy_AI_Sunlit_Temptation_0610024218_generate.glb"
    main(target)
