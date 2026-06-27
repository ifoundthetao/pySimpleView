"""Dialogs supporting AI identification: enhancement preview and guided capture."""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from . import transform


def bgr_to_pixmap(bgr: np.ndarray, max_size: int | None = None) -> QPixmap:
    """Convert a BGR frame to a QPixmap, optionally bounded to ``max_size`` px."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888)
    pix = QPixmap.fromImage(image)
    if max_size is not None:
        pix = pix.scaled(
            max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
    return pix


class EnhancePreviewDialog(QDialog):
    """Shows the current frame as-is next to its AI-enhanced version."""

    def __init__(self, original: np.ndarray, enhanced: np.ndarray, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Enhancement preview")
        self.resize(840, 460)

        before = self._pane("Original (as saved)", original)
        after = self._pane("Enhanced (sent to AI)", enhanced)

        panes = QHBoxLayout()
        panes.addLayout(before)
        panes.addLayout(after)

        note = QLabel(
            "Enhancement boosts local contrast to make faint markings legible; "
            "it is applied only to the image sent to the AI, never to your saved "
            "captures."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#888; font-size:11px;")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(panes)
        layout.addWidget(note)
        layout.addWidget(buttons)

    @staticmethod
    def _pane(title: str, frame: np.ndarray) -> QVBoxLayout:
        col = QVBoxLayout()
        heading = QLabel(title)
        heading.setAlignment(Qt.AlignCenter)
        image = QLabel()
        image.setAlignment(Qt.AlignCenter)
        image.setMinimumSize(380, 380)
        image.setStyleSheet("background:#18181c; border-radius:6px;")
        image.setPixmap(bgr_to_pixmap(frame, 380))
        col.addWidget(heading)
        col.addWidget(image, 1)
        return col


class GuidedCaptureDialog(QDialog):
    """Walks the user through capturing several shots for a single AI request.

    A live preview is driven by ``frame_provider`` (a callable returning the
    current processed BGR frame, or None). The user re-positions / re-lights the
    subject between shots, guided by cycling suggestions, and each captured frame
    is collected in :attr:`shots` for the caller to send together.
    """

    PREVIEW_INTERVAL_MS = 60

    SUGGESTIONS = [
        "Straight-on, even lighting.",
        "Tilt the subject ~30° to the left.",
        "Tilt the subject ~30° to the right.",
        "Rake the light low across one side (reveals etched/embossed text).",
        "Rotate 90° and straighten.",
    ]

    def __init__(
        self, frame_provider: Callable[[], np.ndarray | None], parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Guided capture for AI")
        self.resize(820, 560)
        self._frame_provider = frame_provider
        self.shots: list[np.ndarray] = []

        self.guidance = QLabel()
        self.guidance.setWordWrap(True)
        self.guidance.setStyleSheet("font-size:13px; color:#8cf;")

        self.preview = QLabel("Starting preview…")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(520, 360)
        self.preview.setStyleSheet("background:#18181c; color:#aaa; border-radius:6px;")

        self.thumbs = QListWidget()
        self.thumbs.setFlow(QListWidget.LeftToRight)
        self.thumbs.setWrapping(False)
        self.thumbs.setFixedHeight(110)
        self.thumbs.setIconSize(QSize(120, 84))

        self.capture_btn = QPushButton("📸  Capture this shot")
        self.capture_btn.clicked.connect(self._capture_shot)
        self.remove_btn = QPushButton("Remove selected")
        self.remove_btn.clicked.connect(self._remove_selected)
        cap_row = QHBoxLayout()
        cap_row.addWidget(self.capture_btn, 1)
        cap_row.addWidget(self.remove_btn)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._ok = self.buttons.button(QDialogButtonBox.Ok)
        self._ok.setText("Identify")
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.guidance)
        layout.addWidget(self.preview, 1)
        layout.addLayout(cap_row)
        layout.addWidget(QLabel("Captured shots:"))
        layout.addWidget(self.thumbs)
        layout.addWidget(self.buttons)

        self._refresh_state()

        self._timer = QTimer(self)
        self._timer.setInterval(self.PREVIEW_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ----- live preview -------------------------------------------------

    def _tick(self) -> None:
        frame = self._frame_provider()
        if frame is not None:
            self.preview.setPixmap(
                bgr_to_pixmap(frame, max(self.preview.width(), 320))
            )

    # ----- shots --------------------------------------------------------

    def _capture_shot(self) -> None:
        frame = self._frame_provider()
        if frame is None:
            return
        self.shots.append(frame.copy())
        item = QListWidgetItem(QIcon(bgr_to_pixmap(frame, 120)), f"{len(self.shots)}")
        self.thumbs.addItem(item)
        self.thumbs.scrollToBottom()
        self._refresh_state()

    def _remove_selected(self) -> None:
        row = self.thumbs.currentRow()
        if row < 0:
            return
        self.shots.pop(row)
        self.thumbs.takeItem(row)
        # Renumber the remaining thumbnails.
        for i in range(self.thumbs.count()):
            self.thumbs.item(i).setText(f"{i + 1}")
        self._refresh_state()

    def _refresh_state(self) -> None:
        n = len(self.shots)
        if n < len(self.SUGGESTIONS):
            tip = self.SUGGESTIONS[n]
            self.guidance.setText(f"Shot {n + 1}: {tip}")
        else:
            self.guidance.setText(
                f"{n} shots captured. Add more angles if useful, or click Identify."
            )
        self._ok.setEnabled(n > 0)
        self.remove_btn.setEnabled(self.thumbs.currentRow() >= 0 or n > 0)

    # ----- lifecycle ----------------------------------------------------

    def _accept(self) -> None:
        self._timer.stop()
        self.accept()

    def reject(self) -> None:  # noqa: D401
        self._timer.stop()
        super().reject()

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
