"""Device picker dialog with a live preview of the highlighted camera."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from . import log
from .camera import CaptureThread, list_devices

_log = log.get(__name__)


class DeviceDialog(QDialog):
    """Lists available camera indices and live-previews the selected one.

    The device list cannot be notified when a camera is plugged in, so while
    the dialog is open it re-scans every couple of seconds and folds any newly
    detected cameras into the list. To avoid disturbing a flaky camera, each
    scan only probes indices we haven't already found, the scan stops after a
    run of empty cycles, and a camera whose preview dies is marked bad and left
    alone for the rest of this dialog session.
    """

    POLL_INTERVAL_MS = 1500
    # Stop polling after this many consecutive scans turn up nothing new.
    MAX_IDLE_POLLS = 10

    def __init__(self, current: int | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose a camera")
        self.resize(640, 420)
        self.selected_index: int | None = None
        self._thread: CaptureThread | None = None
        self._known: set[int] = set()
        self._dead: set[int] = set()
        self._idle_polls = 0

        self.list = QListWidget()
        self.preview = QLabel("Scanning for cameras…")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(420, 320)
        self.preview.setStyleSheet("background:#18181c; color:#aaa; border-radius:6px;")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.Ok)
        self._ok_button.setEnabled(False)

        top = QHBoxLayout()
        top.addWidget(self.list, 1)
        top.addWidget(self.preview, 2)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Cameras detected on this Mac:"))
        layout.addLayout(top)
        layout.addWidget(buttons)

        self.list.currentItemChanged.connect(self._on_select)
        self._populate(current)

        # Cameras can be hot-plugged; re-scan periodically while the dialog is up.
        self._poll = QTimer(self)
        self._poll.setInterval(self.POLL_INTERVAL_MS)
        self._poll.timeout.connect(self._refresh_devices)
        self._poll.start()

    def _populate(self, current: int | None) -> None:
        # The main window is still capturing `current`; assume it's present and
        # seed it directly rather than probing it (that would fight the live
        # capture). Other indices get a full scan.
        if current is not None:
            self._add_devices([current])
        self._add_devices(self._scan_devices())
        if self.list.count() == 0:
            self.preview.setText(
                "No cameras found.\nConnect a USB device — still scanning…"
            )
            return
        self._select_index(current)

    def _scan_devices(self) -> list[int]:
        # Only hunt for indices we don't already have. Cameras we've found stay
        # in the list (we don't re-probe them), and ones we've given up on stay
        # excluded — that's what keeps us from cycling on a flaky device.
        return list_devices(exclude=self._known | self._dead)

    def _add_devices(self, devices: list[int]) -> int:
        """Insert any not-yet-listed cameras in index order; return how many."""
        added = 0
        for idx in devices:
            if idx in self._known:
                continue
            item = QListWidgetItem(f"Camera {idx}")
            item.setData(Qt.UserRole, idx)
            self.list.insertItem(self._row_for_index(idx), item)
            self._known.add(idx)
            added += 1
        return added

    def _row_for_index(self, idx: int) -> int:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) > idx:
                return row
        return self.list.count()

    def _select_index(self, index: int | None) -> None:
        if index is not None:
            for row in range(self.list.count()):
                if self.list.item(row).data(Qt.UserRole) == index:
                    self.list.setCurrentRow(row)
                    return
        if self.list.count():
            self.list.setCurrentRow(0)

    def _refresh_devices(self) -> None:
        had_none = self.list.count() == 0
        added = self._add_devices(self._scan_devices())
        if added:
            _log.debug("poll: %d new camera(s); known=%s", added, sorted(self._known))
            self._idle_polls = 0
            if had_none:
                self.list.setCurrentRow(0)
            return
        # Nothing new this cycle. Give up scanning after a while so we're not
        # endlessly reopening empty/flaky indices in the background.
        self._idle_polls += 1
        if self._idle_polls >= self.MAX_IDLE_POLLS:
            _log.debug("poll: idle for %d cycles, stopping scan", self._idle_polls)
            self._poll.stop()
            if self.list.count() == 0:
                self.preview.setText(
                    "No cameras found.\nReopen “Change camera…” to scan again."
                )

    def _on_select(self, item: QListWidgetItem | None) -> None:
        self._stop_preview()
        if item is None:
            self.selected_index = None
            self._ok_button.setEnabled(False)
            return
        index = item.data(Qt.UserRole)
        if index in self._dead:
            self.preview.setText(
                "This camera stopped responding.\nReopen the dialog to retry."
            )
            self.selected_index = None
            self._ok_button.setEnabled(False)
            return
        _log.debug("preview: selecting camera %d", index)
        self.selected_index = index
        self._ok_button.setEnabled(True)
        self.preview.setText("Starting preview…")
        self._thread = CaptureThread(index, self)
        self._thread.frame_ready.connect(self._show_frame)
        self._thread.error.connect(self.preview.setText)
        self._thread.reconnecting.connect(
            lambda idx, n, total: self.preview.setText(
                f"Camera {idx} dropped — reconnecting ({n}/{total})…"
            )
        )
        self._thread.camera_lost.connect(self._on_preview_lost)
        self._thread.start()

    def _on_preview_lost(self, index: int) -> None:
        # The preview camera died. Mark it bad so we stop probing/previewing it
        # for the rest of this dialog; reopening the dialog clears the slate.
        _log.warning("preview: camera %d lost, marking dead", index)
        self._dead.add(index)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) == index:
                item.setText(f"Camera {index} — not responding")
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                break
        self._stop_preview()
        if self.selected_index == index:
            self.selected_index = None
            self._ok_button.setEnabled(False)

    def _show_frame(self, bgr: np.ndarray) -> None:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        rgb = np.ascontiguousarray(rgb)
        h, w = rgb.shape[:2]
        image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888)
        pix = QPixmap.fromImage(image).scaled(
            self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.preview.setPixmap(pix)

    def _stop_preview(self) -> None:
        if self._thread is not None:
            try:
                self._thread.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._thread.stop()
            self._thread = None

    def _accept(self) -> None:
        self._poll.stop()
        self._stop_preview()
        self.accept()

    def reject(self) -> None:  # noqa: D401
        self._poll.stop()
        self._stop_preview()
        super().reject()

    def closeEvent(self, event) -> None:
        self._poll.stop()
        self._stop_preview()
        super().closeEvent(event)
