import numpy as np
import skeletor as sk
import trimesh

from ORSModel.ors import ROI, FaceVertexMesh, Progress
import ORSModel


def ors_to_trimesh(ors_mesh: FaceVertexMesh) -> trimesh.Trimesh:
    """
    Converts a Dragonfly ORS mesh to a trimesh mesh.
    :param ors_mesh: The ORS mesh to convert
    :return: The trimesh mesh
    """
    vertices = ors_mesh.getVertices(0).getNDArray().reshape(-1, 3) * 1e9  # Convert from m to nm
    edges = ors_mesh.getEdges(0).getNDArray().reshape(-1, 3)

    return trimesh.Trimesh(vertices=vertices, faces=edges)


def roi_to_mesh(roi: ROI, cubic=False, smooth=True):
    """
    Does all the preprocessing required to convert a Dragonfly ROI to a trimesh mesh with smoothing applied.
    :return: The Trimesh mesh
    """

    if not cubic:
        scale_x = roi.getXSpacing()
        scale_y = roi.getYSpacing()
        scale_z = roi.getZSpacing()

        # Aim to have zSample = 2 and adjust xSample and ySample accordingly
        z_sample = 2
        x_sample = int(round(scale_z / scale_x * z_sample))
        y_sample = int(round(scale_z / scale_y * z_sample))

        # Clamp x_sample and y_sample to [2, 10] for performance reasons
        x_sample = max(2, min(x_sample, 10))
        y_sample = max(2, min(y_sample, 10))

        dragonfly_mesh = roi.getAsMarchingCubesMesh(
            isovalue=0.5,
            bSnapToContour=False,
            flipNormal=False,
            timeStep=0,
            xSample=x_sample,
            ySample=y_sample,
            zSample=z_sample,
            pNearest=False,
            pWorld=True,
            IProgress=None,
            pMesh=None
        )
    else:
        dragonfly_mesh = roi.getAsCubicMesh(True, None, None)

    if 0 in (dragonfly_mesh.getVertexCount(0), dragonfly_mesh.getEdgeCount(0)):
        # TODO: handle this edge case better
        return trimesh.Trimesh()

    # Smooth the mesh
    if smooth:
        dragonfly_mesh.laplacianSmooth(2, 0, 0.3)

    mesh = ors_to_trimesh(dragonfly_mesh)
    dragonfly_mesh.deleteObjectAndAllItsChildren()

    return mesh


def mesh_to_ors(mesh: trimesh.Trimesh) -> FaceVertexMesh:
    """
    Converts a processing.mesh.Mesh object to a Dragonfly ORS mesh. Used for displaying the final mesh to the user.
    Precondition: The mesh is not none

    :param mesh: The mesh to convert
    :return: The Dragonfly ORS mesh
    """

    np_vertices = np.asarray(mesh.vertices, dtype=np.float64).flatten()
    np_indices = np.asarray(mesh.faces).flatten()

    # divide vertices by 1e9 to get meters instead of nanometers
    np_vertices = np_vertices / 1e9

    ors_mesh = FaceVertexMesh()
    ors_mesh.setTSize(1)  # set the time dimension

    ors_mesh_vertices = ors_mesh.getVertices(0)
    ors_mesh_vertices.setSize(len(np_vertices))

    for i in range(len(np_vertices)):
        ors_mesh_vertices.atPut(i, np_vertices[i])

    ors_indices = ors_mesh.getEdges(0)
    ors_indices.setSize(len(np_indices))

    for i in range(len(np_indices)):
        ors_indices.atPut(i, np_indices[i])

    return ors_mesh


def vector3_to_np(vector3: ORSModel.Vector3) -> np.array:
    return np.array([vector3.getX(), vector3.getY(), vector3.getZ()], dtype=np.float64)


def annotations_to_list(annotations: ORSModel.Annotation) -> list[tuple[np.array, str]]:
    control_points = annotations.getControlPointCount(0)

    output = []
    for i in range(control_points):
        output.append((
            vector3_to_np(annotations.getControlPointPositionAtIndex(i, 0, None)) * 1e9,
            annotations.getControlPointCaptionAtIndex(i, 0)
        ))

    return output


def multiroi_to_mesh(multiroi: ORSModel.MultiROI) -> trimesh.Trimesh:
    """
    Converts a Dragonfly MultiROI to a trimesh mesh.
    :param multiroi: The MultiROI to convert
    :return: The trimesh mesh
    """

    meshes = []

    for label in range(1, multiroi.getLabelCount() + 1):
        copy_roi: ORSModel.ors.ROI = ORSModel.ors.ROI()
        copy_roi.copyShapeFromStructuredGrid(multiroi)
        multiroi.addToVolumeROI(copy_roi, label)

        meshes.append(roi_to_mesh(copy_roi, True, False))
        copy_roi.deleteObjectAndAllItsChildren()

    return trimesh.util.concatenate(meshes, trimesh.Trimesh())


def skeletonize_mesh(mesh: trimesh.Trimesh) -> sk.Skeleton:
    skel = sk.skeletonize.by_wavefront(mesh, origins=None, waves=1, step_size=1)
    sk.post.remove_bristles(skel, los_only=False, inplace=True)
    sk.post.clean_up(skel, inplace=True, theta=1)
    sk.post.despike(skel, inplace=True)

    return skel

