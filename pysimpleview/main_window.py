"""Main application window: controls panel + live view, wired to config."""

from __future__ import annotations

from pathlib import Path

import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import log, naming, video_view, vision
from .ai_settings_dialog import AISettingsDialog
from .camera import CaptureThread
from .config import Config
from .device_dialog import DeviceDialog
from .video_view import VideoView
from .vision import keys as vision_keys
from .vision_worker import VisionThread

_log = log.get(__name__)


class MainWindow(QWidget):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._thread: CaptureThread | None = None
        self._vision_thread: VisionThread | None = None

        self.setWindowTitle("pySimpleView — USB Microscope Capture")
        self.resize(1180, 720)

        self.view = VideoView()
        self._apply_view_state()

        panel = self._build_panel()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setFixedWidth(340)

        layout = QHBoxLayout(self)
        layout.addWidget(scroll)
        layout.addWidget(self.view, 1)

        self.view.crop_changed.connect(self._on_crop_changed)
        self.view.measured.connect(self._on_measured)
        self.view.calibrate_done.connect(self._on_calibrate_done)
        self.view.white_balance_picked.connect(self._on_white_balance_picked)

        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.capture)

        self._refresh_preview()
        self._update_calibration_label()
        self.start_capture(self.config["device_index"])

    # ----- UI construction ---------------------------------------------

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)

        # Camera
        cam_box = QGroupBox("Camera")
        cam_l = QVBoxLayout(cam_box)
        self.camera_label = QLabel("—")
        change_btn = QPushButton("Change camera…")
        change_btn.clicked.connect(self.choose_device)
        cam_l.addWidget(self.camera_label)
        cam_l.addWidget(change_btn)
        v.addWidget(cam_box)

        # Capture
        cap_box = QGroupBox("Capture")
        cap_l = QVBoxLayout(cap_box)
        capture_btn = QPushButton("📸  Capture  (Space)")
        capture_btn.setMinimumHeight(44)
        capture_btn.clicked.connect(self.capture)
        self.status_label = QLabel("Ready.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color:#888;")
        cap_l.addWidget(capture_btn)
        cap_l.addWidget(self.status_label)
        v.addWidget(cap_box)

        # Output / naming
        out_box = QGroupBox("Output & naming")
        out_l = QVBoxLayout(out_box)

        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(self.config["output_dir"])
        self.dir_edit.editingFinished.connect(self._on_dir_edited)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self.browse_dir)
        dir_row.addWidget(self.dir_edit)
        dir_row.addWidget(browse_btn)
        out_l.addWidget(QLabel("Output directory:"))
        out_l.addLayout(dir_row)

        out_l.addWidget(QLabel("Single file name:"))
        self.name_edit = QLineEdit(self.config["single_name"])
        self.name_edit.editingFinished.connect(self._on_name_edited)
        out_l.addWidget(self.name_edit)

        self.follow_check = QCheckBox("Follow naming convention")
        self.follow_check.setChecked(bool(self.config["follow_convention"]))
        self.follow_check.toggled.connect(self._on_follow_toggled)
        out_l.addWidget(self.follow_check)

        self.conv_edit = QLineEdit(self.config["convention"])
        self.conv_edit.setPlaceholderText("resistors-${%04d}.png")
        self.conv_edit.editingFinished.connect(self._on_conv_edited)
        out_l.addWidget(self.conv_edit)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Format:"))
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["png", "jpg", "bmp", "tiff"])
        self.fmt_combo.setCurrentText(self.config["image_format"])
        self.fmt_combo.currentTextChanged.connect(self._on_fmt_changed)
        fmt_row.addWidget(self.fmt_combo)
        fmt_row.addStretch()
        out_l.addLayout(fmt_row)

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("color:#5a9; font-style:italic;")
        out_l.addWidget(self.preview_label)
        v.addWidget(out_box)

        # Orientation
        ori_box = QGroupBox("Orientation")
        ori_l = QVBoxLayout(ori_box)
        self.fliph_check = QCheckBox("Flip horizontal")
        self.fliph_check.setChecked(bool(self.config["flip_h"]))
        self.fliph_check.toggled.connect(lambda s: self._set("flip_h", s))
        self.flipv_check = QCheckBox("Flip vertical")
        self.flipv_check.setChecked(bool(self.config["flip_v"]))
        self.flipv_check.toggled.connect(lambda s: self._set("flip_v", s))
        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Rotation:"))
        self.rot_combo = QComboBox()
        self.rot_combo.addItems(["0°", "90°", "180°", "270°"])
        self.rot_combo.setCurrentText(f"{self.config['rotation']}°")
        self.rot_combo.currentTextChanged.connect(self._on_rotation_changed)
        rot_row.addWidget(self.rot_combo)
        rot_row.addStretch()
        ori_l.addWidget(self.fliph_check)
        ori_l.addWidget(self.flipv_check)
        ori_l.addLayout(rot_row)
        v.addWidget(ori_box)

        # Overlays
        ov_box = QGroupBox("Overlays")
        ov_l = QVBoxLayout(ov_box)
        self.cross_check = QCheckBox("Centering crosshair")
        self.cross_check.setChecked(bool(self.config["show_crosshair"]))
        self.cross_check.toggled.connect(lambda s: self._set("show_crosshair", s))
        self.thirds_check = QCheckBox("Rule-of-thirds grid")
        self.thirds_check.setChecked(bool(self.config["show_thirds"]))
        self.thirds_check.toggled.connect(lambda s: self._set("show_thirds", s))
        self.burn_check = QCheckBox("Burn guides into saved image")
        self.burn_check.setChecked(bool(self.config["burn_overlays"]))
        self.burn_check.toggled.connect(lambda s: self._set("burn_overlays", s))
        ov_l.addWidget(self.cross_check)
        ov_l.addWidget(self.thirds_check)
        ov_l.addWidget(self.burn_check)
        v.addWidget(ov_box)

        # White balance
        wb_box = QGroupBox("White balance")
        wb_l = QVBoxLayout(wb_box)
        self.wb_btn = QPushButton("Set white balance")
        self.wb_btn.setCheckable(True)
        self.wb_btn.toggled.connect(self._on_wb_toggled)
        wb_clear_btn = QPushButton("Clear (raw colour)")
        wb_clear_btn.clicked.connect(self._clear_white_balance)
        self.wb_status = QLabel()
        self.wb_status.setWordWrap(True)
        self.wb_status.setStyleSheet("color:#888;")
        wb_l.addWidget(self.wb_btn)
        wb_l.addWidget(wb_clear_btn)
        wb_l.addWidget(self.wb_status)
        v.addWidget(wb_box)
        self._update_wb_status()

        # Crop
        crop_box = QGroupBox("Crop")
        crop_l = QVBoxLayout(crop_box)
        self.crop_btn = QPushButton("Set crop region")
        self.crop_btn.setCheckable(True)
        self.crop_btn.toggled.connect(self._on_crop_toggled)
        clear_crop_btn = QPushButton("Clear crop")
        clear_crop_btn.clicked.connect(self._clear_crop)
        self.crop_status = QLabel()
        self.crop_status.setStyleSheet("color:#888;")
        crop_l.addWidget(self.crop_btn)
        crop_l.addWidget(clear_crop_btn)
        crop_l.addWidget(self.crop_status)
        v.addWidget(crop_box)
        self._update_crop_status()

        # Measurement
        meas_box = QGroupBox("Measurement")
        meas_l = QVBoxLayout(meas_box)
        self.measure_btn = QPushButton("Measure")
        self.measure_btn.setCheckable(True)
        self.measure_btn.toggled.connect(self._on_measure_toggled)
        calib_btn = QPushButton("Calibrate…")
        calib_btn.clicked.connect(self._start_calibration)
        self.measure_result = QLabel("Draw a line to measure.")
        self.measure_result.setStyleSheet("color:#8cf;")
        self.calib_label = QLabel()
        self.calib_label.setStyleSheet("color:#888;")
        self.calib_label.setWordWrap(True)
        meas_l.addWidget(self.measure_btn)
        meas_l.addWidget(calib_btn)
        meas_l.addWidget(self.measure_result)
        meas_l.addWidget(self.calib_label)
        v.addWidget(meas_box)

        # AI identification
        ai_box = QGroupBox("Identify (AI)")
        ai_l = QVBoxLayout(ai_box)
        ai_row = QHBoxLayout()
        self.identify_btn = QPushButton("Identify")
        self.identify_btn.clicked.connect(self.identify)
        ai_settings_btn = QPushButton("AI settings…")
        ai_settings_btn.clicked.connect(self.open_ai_settings)
        ai_row.addWidget(self.identify_btn)
        ai_row.addWidget(ai_settings_btn)
        self.ai_provider_label = QLabel()
        self.ai_provider_label.setStyleSheet("color:#888;")
        self.ai_result = QPlainTextEdit()
        self.ai_result.setReadOnly(True)
        self.ai_result.setMinimumHeight(120)
        self.ai_result.setPlaceholderText("AI description of the current view appears here.")
        ai_l.addLayout(ai_row)
        ai_l.addWidget(self.ai_provider_label)
        ai_l.addWidget(self.ai_result)
        v.addWidget(ai_box)
        self._update_ai_label()

        v.addStretch()
        return panel

    # ----- capture lifecycle -------------------------------------------

    def start_capture(self, index: int) -> None:
        _log.debug("start_capture(%d)", index)
        self._stop_capture()
        self.camera_label.setText(f"Camera {index}")
        self.status_label.setText("Ready.")
        self._thread = CaptureThread(index, self)
        self._thread.frame_ready.connect(self.view.set_frame)
        self._thread.error.connect(self._on_capture_error)
        self._thread.camera_lost.connect(self._on_camera_lost)
        self._thread.reconnecting.connect(self._on_reconnecting)
        self._thread.recovered.connect(self._on_recovered)
        self._thread.start()

    def _stop_capture(self) -> None:
        if self._thread is not None:
            try:
                self._thread.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._thread.stop()
            self._thread = None

    def _on_capture_error(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_reconnecting(self, index: int, attempt: int, attempts: int) -> None:
        self.camera_label.setText(f"Camera {index} — reconnecting…")
        self.status_label.setText(
            f"Camera {index} dropped — reconnecting (attempt {attempt}/{attempts})…"
        )

    def _on_recovered(self, index: int) -> None:
        self.camera_label.setText(f"Camera {index}")
        self.status_label.setText(f"Camera {index} reconnected.")

    def _on_camera_lost(self, index: int) -> None:
        # The thread has already given up and released the device. Tear it down
        # and leave the camera alone — we won't touch it again until the user
        # picks one via "Change camera…".
        _log.warning("camera %d lost; tearing down capture", index)
        self.camera_label.setText(f"Camera {index} — not responding")
        self._stop_capture()

    def choose_device(self) -> None:
        # Release the live device first so the dialog has exclusive access.
        # Otherwise the main capture and the dialog's preview fight over the
        # same camera (two AVFoundation opens at once), which wedges flaky
        # hub/KVM setups.
        previous = self.config["device_index"]
        _log.debug("choose_device: releasing camera %s for picker", previous)
        self._stop_capture()

        dialog = DeviceDialog(previous, self)
        chosen = dialog.selected_index if dialog.exec() else None

        if chosen is not None:
            self._set("device_index", chosen)
            self.start_capture(chosen)
        else:
            # Cancelled — resume whatever we were showing before.
            self.start_capture(previous)

    # ----- config helpers ----------------------------------------------

    def _set(self, key: str, value) -> None:
        self.config[key] = value
        self.config.save()
        self._apply_view_state()

    def _apply_view_state(self) -> None:
        self.view.flip_h = bool(self.config["flip_h"])
        self.view.flip_v = bool(self.config["flip_v"])
        self.view.rotation = int(self.config["rotation"])
        self.view.show_crosshair = bool(self.config["show_crosshair"])
        self.view.show_thirds = bool(self.config["show_thirds"])
        self.view.crop = self.config["crop"]
        self.view.white_balance = self.config["white_balance"]
        self.view.update()

    # ----- naming -------------------------------------------------------

    def _on_dir_edited(self) -> None:
        self._set("output_dir", self.dir_edit.text().strip())
        self._refresh_preview()

    def browse_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose output directory", self.config["output_dir"]
        )
        if chosen:
            self.dir_edit.setText(chosen)
            self._set("output_dir", chosen)
            self._refresh_preview()

    def _on_name_edited(self) -> None:
        self._set("single_name", self.name_edit.text().strip())
        self._refresh_preview()

    def _on_conv_edited(self) -> None:
        self._set("convention", self.conv_edit.text().strip())
        self._refresh_preview()

    def _on_follow_toggled(self, state: bool) -> None:
        self._set("follow_convention", state)
        self._refresh_preview()

    def _on_fmt_changed(self, text: str) -> None:
        self._set("image_format", text)
        self._refresh_preview()

    def _next_path(self) -> Path:
        directory = Path(self.config["output_dir"])
        if self.config["follow_convention"] and naming.has_token(self.config["convention"]):
            name = naming.next_filename(self.config["convention"], directory)
        else:
            name = naming.resolve_single_name(
                self.config["single_name"], self.config["image_format"]
            )
        return directory / name

    def _refresh_preview(self) -> None:
        self.preview_label.setText(f"Next file: {self._next_path().name}")

    # ----- capture ------------------------------------------------------

    def capture(self) -> None:
        frame = self.view.display_frame()
        if frame is None:
            self.status_label.setText("No frame to capture yet.")
            return
        if self.config["burn_overlays"]:
            frame = self._burn_guides(frame.copy())

        target = self._next_path()
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            reply = QMessageBox.question(
                self, "Overwrite file?",
                f"{target.name} already exists.\nOverwrite it?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self.status_label.setText("Capture cancelled.")
                return

        if cv2.imwrite(str(target), frame):
            self.status_label.setText(f"Saved {target.name}")
        else:
            self.status_label.setText(f"Failed to write {target.name}")
        self._refresh_preview()

    def _burn_guides(self, frame):
        h, w = frame.shape[:2]
        green = (120, 220, 0)
        white = (200, 200, 200)
        if self.config["show_thirds"]:
            for i in (1, 2):
                cv2.line(frame, (w * i // 3, 0), (w * i // 3, h), white, 1)
                cv2.line(frame, (0, h * i // 3), (w, h * i // 3), white, 1)
        if self.config["show_crosshair"]:
            cv2.line(frame, (w // 2, 0), (w // 2, h), green, 1)
            cv2.line(frame, (0, h // 2), (w, h // 2), green, 1)
        return frame

    # ----- orientation --------------------------------------------------

    def _on_rotation_changed(self, text: str) -> None:
        self._set("rotation", int(text.rstrip("°")))

    # ----- crop ---------------------------------------------------------

    def _on_crop_toggled(self, checked: bool) -> None:
        if checked:
            self.measure_btn.setChecked(False)
            self.wb_btn.setChecked(False)
            self.crop_btn.setText("Drag on video, then release")
            self.view.set_mode(video_view.MODE_CROP)
        else:
            self.crop_btn.setText("Set crop region")
            if self.view.mode == video_view.MODE_CROP:
                self.view.set_mode(video_view.MODE_VIEW)

    def _on_crop_changed(self, crop) -> None:
        self.config["crop"] = crop
        self.config.save()
        self.crop_btn.setChecked(False)
        self._update_crop_status()

    def _clear_crop(self) -> None:
        self.config["crop"] = None
        self.config.save()
        self.view.crop = None
        self.view.update()
        self._update_crop_status()

    def _update_crop_status(self) -> None:
        crop = self.config["crop"]
        if crop:
            self.crop_status.setText(f"Crop: {crop[2]}×{crop[3]} px")
        else:
            self.crop_status.setText("No crop (full frame).")

    # ----- white balance ------------------------------------------------

    def _on_wb_toggled(self, checked: bool) -> None:
        if checked:
            self.crop_btn.setChecked(False)
            self.measure_btn.setChecked(False)
            self.wb_btn.setText("Click/drag a neutral area")
            self.view.set_mode(video_view.MODE_WHITE_BALANCE)
        else:
            self.wb_btn.setText("Set white balance")
            if self.view.mode == video_view.MODE_WHITE_BALANCE:
                self.view.set_mode(video_view.MODE_VIEW)

    def _on_white_balance_picked(self, gains) -> None:
        self.config["white_balance"] = gains
        self.config.save()
        self.view.white_balance = gains
        self.wb_btn.setChecked(False)
        self._update_wb_status()

    def _clear_white_balance(self) -> None:
        self.config["white_balance"] = None
        self.config.save()
        self.view.white_balance = None
        self.view.update()
        self._update_wb_status()

    def _update_wb_status(self) -> None:
        gains = self.config["white_balance"]
        if gains:
            b, g, r = gains
            self.wb_status.setText(
                f"Corrected · gains  B {b:.2f} / G {g:.2f} / R {r:.2f}"
            )
        else:
            self.wb_status.setText("Raw colour (no correction).")

    # ----- measurement --------------------------------------------------

    def _on_measure_toggled(self, checked: bool) -> None:
        if checked:
            self.crop_btn.setChecked(False)
            self.wb_btn.setChecked(False)
            self.view.set_mode(video_view.MODE_MEASURE)
            self.measure_result.setText("Drag a line on the video.")
        elif self.view.mode == video_view.MODE_MEASURE:
            self.view.set_mode(video_view.MODE_VIEW)

    def _on_measured(self, pixels: float) -> None:
        scale = self.config["scale_units_per_px"]
        if scale:
            real = pixels * scale
            unit = self.config["scale_unit"]
            self.measure_result.setText(f"{pixels:.1f} px  ≈  {real:.2f} {unit}")
        else:
            self.measure_result.setText(f"{pixels:.1f} px  (not calibrated)")

    def _start_calibration(self) -> None:
        self.measure_btn.setChecked(False)
        self.crop_btn.setChecked(False)
        self.wb_btn.setChecked(False)
        self.view.set_mode(video_view.MODE_CALIBRATE)
        self.measure_result.setText("Draw a line over a known length…")

    def _on_calibrate_done(self, pixels: float) -> None:
        unit = self.config["scale_unit"]
        length, ok = QInputDialog.getDouble(
            self, "Calibrate",
            f"The drawn line is {pixels:.1f} px.\nEnter its real length ({unit}):",
            1.0, 0.0001, 1_000_000.0, 4,
        )
        self.view.set_mode(video_view.MODE_VIEW)
        if not ok or length <= 0:
            self.measure_result.setText("Calibration cancelled.")
            return
        self._set_calibration(length / pixels)

    def _set_calibration(self, units_per_px: float) -> None:
        self.config["scale_units_per_px"] = units_per_px
        self.config.save()
        self._update_calibration_label()
        self.measure_result.setText("Calibrated. Use Measure to draw lines.")

    def _update_calibration_label(self) -> None:
        scale = self.config["scale_units_per_px"]
        unit = self.config["scale_unit"]
        if scale:
            self.calib_label.setText(f"Calibrated: {scale:.4f} {unit}/px")
        else:
            self.calib_label.setText("Not calibrated — measurements show pixels only.")

    # ----- AI identification --------------------------------------------

    def _update_ai_label(self) -> None:
        provider = self.config["vision_provider"]
        spec = vision.preset(provider)
        model = self.config["vision_model"] or spec["model"]
        keyed = "key set" if vision_keys.has_api_key(provider) else "no key"
        self.ai_provider_label.setText(f"{spec['label']} · {model} · {keyed}")

    def open_ai_settings(self) -> None:
        dialog = AISettingsDialog(self.config, self)
        if dialog.exec():
            self._update_ai_label()

    def identify(self) -> None:
        if self._vision_thread is not None:
            return
        frame = self.view.display_frame()
        if frame is None:
            self.ai_result.setPlainText("No frame to identify yet.")
            return

        provider_key = self.config["vision_provider"]
        api_key = vision_keys.get_api_key(provider_key)
        if not api_key:
            self.ai_result.setPlainText(
                "No API key set for this provider. Click “AI settings…” to add one."
            )
            return

        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            self.ai_result.setPlainText("Could not encode the current frame.")
            return

        provider = vision.build_provider(
            provider_key,
            self.config["vision_model"],
            self.config["vision_base_url"],
            api_key,
        )
        self.identify_btn.setEnabled(False)
        self.ai_result.setPlainText("Identifying…")
        self._vision_thread = VisionThread(
            provider, buffer.tobytes(), "image/jpeg", self.config["vision_prompt"], self
        )
        self._vision_thread.succeeded.connect(self._on_vision_ok)
        self._vision_thread.failed.connect(self._on_vision_fail)
        self._vision_thread.finished.connect(self._on_vision_finished)
        self._vision_thread.start()

    def _on_vision_ok(self, text: str) -> None:
        self.ai_result.setPlainText(text)

    def _on_vision_fail(self, message: str) -> None:
        self.ai_result.setPlainText(f"Error: {message}")

    def _on_vision_finished(self) -> None:
        self.identify_btn.setEnabled(True)
        self._vision_thread = None

    # ----- shutdown -----------------------------------------------------

    def closeEvent(self, event) -> None:
        self._stop_capture()
        if self._vision_thread is not None:
            self._vision_thread.wait(3000)
        super().closeEvent(event)
