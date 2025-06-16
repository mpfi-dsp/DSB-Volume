"""
This script visualizes a DSB file using trimesh and meshparty.
This requires the external library meshparty, which is not included in the requirements.txt file.

Annotations and PSDs are not visualized in this script.
"""
import hashlib
import math

import trimesh
from meshparty import trimesh_vtk as vtk

from pipeline import payload as pld
from pipeline.beheading import polyline_utils

DSB_FILE = "F:/DSB Files/cell1_roi5.dsb"


def color_hash(n) -> tuple[float, float, float]:
    hash_bytes = hashlib.md5(str(n).encode()).digest()

    r = (hash_bytes[0] % 128) / 255
    g = (hash_bytes[1] % 128) / 255
    b = (hash_bytes[2] % 128) / 255

    return r, g, b


def main():
    payload = pld.pld_load(DSB_FILE)

    mesh = payload.dendrite_mesh

    spine_skeletons, _ = polyline_utils.get_branch_polylines_by_length(
        payload.skeleton, min_length=0, max_length=10000, min_nodes=5, max_nodes=5000, radius_threshold=math.inf
    )

    mesh_actor = vtk.mesh_actor(mesh, color=(0.5, 0.5, 0.5))

    polyline_actors = [
        vtk.linked_point_actor(polyline[:-1], polyline[1:], line_width=2, color=color_hash(idx), opacity=1)
        for idx, polyline in enumerate(spine_skeletons)
    ]

    vtk.render_actors([mesh_actor] + polyline_actors)


if __name__ == "__main__":
    main()
