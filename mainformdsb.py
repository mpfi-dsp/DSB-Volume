import math
import os
from typing import Optional

from PyQt6.QtGui import QIntValidator, QShortcut, QKeySequence

import ORSModel
from OrsHelpers.viewLayoutHelper import DisplayLayoutHelper
import numpy as np
from scipy.spatial import KDTree
import trimesh
from OrsLibraries.workingcontext import WorkingContext
from ORSServiceClass.windowclasses.orsabstractwindow import OrsAbstractWindow
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QFileDialog

from .pipeline.preprocessing.preprocessingworker import PreprocessingWorker
from .pipeline.beheading import skel_helper, spine_analysis, polyline_utils
from .pipeline.preprocessing import meshhelper
from .pipeline.beheading import geometry as geom
from .pipeline import payload
from .ui_mainformdsb import Ui_MainFormDsb
from .visualize import visualize as vis


class MainFormDsb(OrsAbstractWindow):
    def __init__(self, implementation, parent=None):
        super().__init__(implementation, parent)
        self.ui = Ui_MainFormDsb()
        self.ui.setupUi(self)
        self.ui.ccb_dendrite_roi_chooser.setManagedClass([ORSModel.ROI])
        self.ui.ccb_annotation_chooser.setManagedClass([ORSModel.Annotation])
        self.ui.ccb_multiroi_chooser.setManagedClass([ORSModel.MultiROI])
        self.ui.ccb_annotation_chooser.setEnabled(self.ui.chk_vis_annotations.isChecked())
        self.ui.ccb_multiroi_chooser.setEnabled(self.ui.chk_vis_multiroi.isChecked())

        # I have to set these manually for some reason
        self.ui.chk_vis_annotations.stateChanged.connect(self.on_chk_vis_annotations_stateChanged)
        self.ui.chk_vis_multiroi.stateChanged.connect(self.on_chk_vis_multiroi_stateChanged)
        self.ui.line_spine_num.textEdited.connect(self.on_line_spine_num_textEdited)

        self.ui.line_spine_num.setValidator(QIntValidator(0, 9999))
        self.ui.btn_go_to_spine_num.setEnabled(False)
        self.ui.sldr_neck_point.setMaximum(1000)
        WorkingContext.registerOrsWidget('DSB_efd060071a1711f0b40cf83441a96bd5', implementation, 'MainFormDsb', self)
        self.mesh: Optional[trimesh.Trimesh] = None
        self.visualizer = None
        self.spine_skeletons = None
        self.neck_point_slider_values = []
        self.annotations_kdtree: Optional[KDTree] = None
        self.annotations = []
        self.neck_pt_3d: Optional[np.ndarray] = None
        self.neck_pt_tangent: Optional[np.ndarray] = None
        self.worker: Optional[PreprocessingWorker] = None

        self.shortcut_neck_point_left = QShortcut(QKeySequence("Q"), self)
        self.shortcut_neck_point_left.activated.connect(self.move_slider_left)

        self.shortcut_neck_point_right = QShortcut(QKeySequence("E"), self)
        self.shortcut_neck_point_right.activated.connect(self.move_slider_right)

        self.ui.btn_next_spine.setShortcut("D")
        self.ui.btn_prev_spine.setShortcut("A")
        self.ui.btn_save_head.setShortcut("R")
        self.ui.btn_go_to_spine_num.setShortcut("Enter")

    def move_slider_left(self):
        self.ui.sldr_neck_point.setValue(self.ui.sldr_neck_point.value() - 10)

    def move_slider_right(self):
        self.ui.sldr_neck_point.setValue(self.ui.sldr_neck_point.value() + 10)

    def update_status_label(self, text: str):
        self.ui.lbl_status.setText(text)

    @pyqtSlot()
    def on_btn_preprocessing_run_clicked(self):
        selected_roi = ORSModel.orsObj(self.ui.ccb_dendrite_roi_chooser.getSelectedGuid())
        if selected_roi is None:
            self.ui.lbl_status.setText("No ROI selected")
            return

        filepath = self.ui.line_preprocessing_output_path.text()
        if not filepath:
            self.ui.lbl_status.setText("No output path selected")
            return

        if not os.path.isdir(os.path.dirname(filepath)):
            self.ui.lbl_status.setText("Output path is invalid")
            return

        self.worker = PreprocessingWorker(
            filepath, selected_roi,
            ORSModel.orsObj(self.ui.ccb_multiroi_chooser.getSelectedGuid()) if self.ui.chk_vis_multiroi.isChecked() else None,
            ORSModel.orsObj(self.ui.ccb_annotation_chooser.getSelectedGuid()) if self.ui.chk_vis_annotations.isChecked() else None
        )

        self.worker.update_label.connect(self.update_status_label)
        self.worker.finished.connect(lambda: self.ui.btn_preprocessing_run.setEnabled(True))

        self.worker.start()
        self.ui.btn_preprocessing_run.setEnabled(False)  # Disable it until the worker is done

    @pyqtSlot()
    def on_btn_select_csv_output_clicked(self):
        filepath, _ = QFileDialog.getSaveFileName(
            None,
            "Select Output CSV Location",
            "",
            "CSV File (*.csv)"
        )

        if filepath:
            self.ui.line_csv_output.setText(filepath)
        else:
            self.ui.lbl_status.setText("No file selected")
            return

    @pyqtSlot()
    def on_btn_preprocessing_output_clicked(self):
        filepath, _ = QFileDialog.getSaveFileName(
            None,
            "Select Output File Location",
            "",
            "DSB Files (*.dsb)"
        )

        if filepath:
            self.ui.line_preprocessing_output_path.setText(filepath)
        else:
            self.ui.lbl_status.setText("No file selected")
            return

    def compute_neck_point_and_tangent(self, idx: int):
        """
        Computes the neck point of the spine

        :return: (neck point 3D, neck tangent vector, neck point 1D)
        """

        if self.mesh is None or self.spine_skeletons is None:
            return None, None

        spine_skeleton = self.spine_skeletons[idx]
        spacing = 6

        points_tangents, radii_tangents = skel_helper.get_radius_polyline(
            spine_skeleton[::-1], self.mesh, n_rays=125, aggregate='percentile99',
            projection='tangents', path_interpolation_spacing=spacing
        )

        cumulative_points = geom.accumulate(points_tangents)

        neck_point_1d = spine_analysis.find_neck_point_from_head_radius(
            spine_skeleton[::-1], self.mesh, cumulative_points, radii_tangents
        )

        neck_point_3d, neck_tangent = geom.point_and_tangent_along_polyline(spine_skeleton, neck_point_1d)
        return neck_point_3d, neck_tangent, neck_point_1d

    def jump_vis(self, n: int) -> None:
        """
        Jumps n spines forward or backward in the visualization.
        :param n: -1 to jump backward, 1 to jump forward, 0 to reload the current spine, etc.
        """

        if self.visualizer is None:
            self.ui.lbl_status.setText("Load a preprocessing file first")
            return

        vis_current = self.visualizer.currently_visualizing
        vis_next = (vis_current + n) if vis_current is not None else 0
        if vis_next >= len(self.spine_skeletons) or vis_next < 0:
            self.ui.lbl_status.setText("No more spines to visualize")
            return

        if not self.visualizer.has_spine_point(vis_next):
            accumulated = geom.accumulate(self.spine_skeletons[vis_next])

            # Compute the neck point and tangent for the next spine
            if self.ui.chk_compute_beheading_pt.isChecked():
                self.neck_pt_3d, self.neck_pt_tangent, neck_pt_1d = self.compute_neck_point_and_tangent(vis_next)
            else:
                neck_pt_1d = accumulated[-1]
                self.neck_pt_3d, self.neck_pt_tangent = geom.point_and_tangent_along_polyline(self.spine_skeletons[vis_next], neck_pt_1d)

            self.visualizer.transform_plane(self.neck_pt_3d, self.neck_pt_tangent)
            self.neck_point_slider_values[vis_next] = int((accumulated[-1] - neck_pt_1d) / accumulated[-1] * self.ui.sldr_neck_point.maximum())

            if self.neck_pt_3d is None or self.neck_pt_tangent is None:
                self.ui.lbl_status.setText("Failed to compute neck point and tangent")
                return

            self.visualizer.set_spine_point(vis_next, self.neck_pt_3d)

        self.visualizer.vis_spine_idx(vis_next)
        self.ui.sldr_neck_point.setValue(self.neck_point_slider_values[vis_next])
        self.ui.line_spine_num.setText(f"{vis_next + 1}")

    @pyqtSlot()
    def on_btn_prev_spine_clicked(self):
        self.jump_vis(-1)

    @pyqtSlot()
    def on_btn_next_spine_clicked(self):
        self.jump_vis(1)

    @pyqtSlot()
    def on_btn_select_preprocessing_file_clicked(self):
        filepath, _ = QFileDialog.getOpenFileName(
            None,
            "Select Preprocessing File",
            "",
            "DSB Files (*.dsb)"
        )

        if not filepath:
            self.ui.lbl_status.setText("No file selected")
            return

        pld = payload.pld_load(filepath)
        self.mesh = pld.dendrite_mesh
        self.spine_skeletons, radii = polyline_utils.get_branch_polylines_by_length(
            pld.skeleton, min_length=0, max_length=10000, min_nodes=5, max_nodes=5000, radius_threshold=math.inf
        )
        self.neck_point_slider_values = [0 for _ in range(len(self.spine_skeletons))]

        self.annotations = pld.annotations if pld.annotations is not None else []

        if self.annotations:
            self.annotations_kdtree = KDTree([point for point, _ in self.annotations])

        self.ui.vis_widget.show()

        if self.visualizer is not None:
            self.visualizer.destroy()
            self.visualizer = None

        self.visualizer = vis.Visualizer(self.ui.vis_widget, pld.dendrite_mesh, self.spine_skeletons, pld.annotations, pld.psds)
        self.ui.vis_widget.reset_camera()
        self.jump_vis(0)
        self.ui.lbl_spine_nums_total.setText(f"/ {len(self.spine_skeletons)}")

    @pyqtSlot()
    def on_chk_vis_annotations_stateChanged(self):
        self.ui.ccb_annotation_chooser.setEnabled(self.ui.chk_vis_annotations.isChecked())

    @pyqtSlot()
    def on_chk_vis_multiroi_stateChanged(self):
        self.ui.ccb_multiroi_chooser.setEnabled(self.ui.chk_vis_multiroi.isChecked())

    def change_name(self, neck_point) -> Optional[str]:
        if self.annotations_kdtree is None:
            return None

        dist, idx = self.annotations_kdtree.query(neck_point, k=1)
        if dist > 4000:
            return None

        return self.annotations[idx][1] if idx < len(self.annotations) else None

    @pyqtSlot(int)
    def on_sldr_neck_point_valueChanged(self, value):
        current_idx = self.visualizer.currently_visualizing

        if (self.mesh is None
            or current_idx is None
            or current_idx >= len(self.neck_point_slider_values)
        ):
            self.ui.lbl_status.setText("No spine selected")
            return

        accumulated = geom.accumulate(self.spine_skeletons[current_idx])
        spine_len = accumulated[-1]
        slider_max = self.ui.sldr_neck_point.maximum()
        neck_pt_1d = spine_len * (slider_max - value) / slider_max
        self.neck_pt_3d, self.neck_pt_tangent = geom.point_and_tangent_along_polyline(
            self.spine_skeletons[current_idx], neck_pt_1d
        )

        self.visualizer.transform_plane(self.neck_pt_3d, self.neck_pt_tangent)

        self.neck_point_slider_values[current_idx] = value
        self.visualizer.set_spine_point(current_idx, self.neck_pt_3d)

        new_name = self.change_name(self.neck_pt_3d)
        if new_name is not None:
            self.ui.line_head_name.setText(f"{new_name}")
        else:
            self.ui.line_head_name.setText(f"{current_idx + 1}")

    @pyqtSlot()
    def on_line_spine_num_textEdited(self):
        if self.visualizer.currently_visualizing is None:
            return

        try:
            value = int(self.ui.line_spine_num.text().strip())
        except ValueError:
            return

        if value - 1 != self.visualizer.currently_visualizing:
            self.ui.btn_go_to_spine_num.setEnabled(True)
        else:
            self.ui.btn_go_to_spine_num.setEnabled(False)

    @pyqtSlot()
    def on_btn_go_to_spine_num_clicked(self):
        try:
            value = int(self.ui.line_spine_num.text().strip()) - 1
        except ValueError:
            self.ui.lbl_status.setText("Invalid spine number")
            return

        current_idx = self.visualizer.currently_visualizing
        delta = value - current_idx

        self.jump_vis(delta)
        self.ui.btn_go_to_spine_num.setEnabled(False)

    @pyqtSlot()
    def on_btn_save_head_clicked(self):
        current_idx = self.visualizer.currently_visualizing

        if (self.mesh is None
                or current_idx is None
                or current_idx >= len(self.neck_point_slider_values)
        ):
            self.ui.lbl_status.setText("No spine selected")
            return

        if self.neck_pt_3d is None or self.neck_pt_tangent is None:
            self.ui.lbl_status.setText("No neck point computed")
            return

        beheaded = self.mesh.slice_plane(self.neck_pt_3d, -self.neck_pt_tangent, cap=True)

        closest_component: Optional[trimesh.Trimesh] = None
        closest_component_dist = np.inf

        for component in beheaded.split(only_watertight=False):
            dist = trimesh.proximity.closest_point(component, [self.neck_pt_3d])[1][0]

            if dist < closest_component_dist:
                closest_component = component
                closest_component_dist = dist

        if closest_component is None:
            self.ui.lbl_status.setText("No component found for base - cancelling beheading")
            return

        centroid = np.array(closest_component.centroid)

        ors_mesh = meshhelper.mesh_to_ors(mesh=closest_component)
        head_name = self.ui.line_head_name.text()
        ors_mesh.setTitle(f"Spine Head {head_name}")
        ors_mesh.publish()
        self.ui.lbl_status.setText(f"Saved: Spine Head {head_name}")

        if filepath := self.ui.line_csv_output.text():
            vol = closest_component.volume / 1e9  # Convert from nm³ to μm³
            payload.csv_save(filepath, head_name, current_idx + 1, vol, self.neck_pt_3d, centroid)

    @pyqtSlot()
    def on_btn_go_to_spine_clicked(self):
        if self.neck_pt_3d is None:
            self.ui.lbl_status.setText("No neck point computed")
            return

        view = WorkingContext.getCurrentView(None)
        if view is None:
            self.ui.lbl_status.setText("No current view found")
            return

        ors_vec = ORSModel.ors.Vector3()
        ors_vec.setXYZ(*(self.neck_pt_3d / 1e9))  # Convert from nm to m
        DisplayLayoutHelper.moveAllLayoutOfViewToIncludePoint(view, ors_vec, True, False)

    @pyqtSlot()
    def closeEvent(self, event):
        self.ui.vis_widget.Finalize()  # Explicitly finalize to prevent a black screen upon exit of the plugin window
        super().closeEvent(event)
