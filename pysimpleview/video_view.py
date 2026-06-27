"""Live video widget with orientation, crop, overlays and measurement tools."""

from __future__ import annotations

import math

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import transform

# Interaction modes
MODE_VIEW = "view"
MODE_CROP = "crop"
MODE_MEASURE = "measure"
MODE_CALIBRATE = "calibrate"
MODE_WHITE_BALANCE = "white_balance"


class VideoView(QWidget):
    """Displays frames and hosts interactive crop / measure overlays.

    All overlay geometry is expressed in *image space* (the pixel grid of the
    transformed frame that is currently visible). Because flips, rotations and
    crops preserve pixel scale, distances measured in image space equal source
    pixel distances, so calibration stays valid regardless of orientation.
    """

    crop_changed = Signal(object)         # [x, y, w, h] or None
    measured = Signal(float)              # length in image pixels (live + final)
    calibrate_done = Signal(float)        # length in image pixels of calibration line
    white_balance_picked = Signal(object)  # [b, g, r] gains

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self.setMouseTracking(True)

        self._source: np.ndarray | None = None
        self._rgb: np.ndarray | None = None  # keep alive for QImage buffer
        self._qimage: QImage | None = None
        self._base_w = 0
        self._base_h = 0
        self._target = QRectF()

        # transform state
        self.flip_h = False
        self.flip_v = False
        self.rotation = 0
        self.crop: list | None = None
        self.white_balance: list | None = None  # [b, g, r] gains

        # overlays
        self.show_crosshair = False
        self.show_thirds = False

        # interaction
        self._mode = MODE_VIEW
        self._dragging = False
        self._drag_start = QPointF()
        self._drag_end = QPointF()

    # ----- public API ---------------------------------------------------

    def set_frame(self, bgr: np.ndarray) -> None:
        self._source = bgr
        self.update()

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._dragging = False
        if mode != MODE_MEASURE and mode != MODE_CALIBRATE:
            self._drag_start = self._drag_end = QPointF()
        self.update()

    def display_frame(self) -> np.ndarray | None:
        """The BGR frame as currently shown (balanced + oriented + cropped), for saving."""
        if self._source is None:
            return None
        oriented = transform.apply_orientation(
            self._source, self.flip_h, self.flip_v, self.rotation
        )
        balanced = transform.apply_white_balance(oriented, self.white_balance)
        return transform.apply_crop(balanced, self.crop)

    # ----- frame pipeline ----------------------------------------------

    def _base_frame(self) -> np.ndarray | None:
        """Frame to render. While picking white balance, show raw (uncorrected)
        colour so the sampled patch reflects the true cast; while editing crop,
        show the full uncropped frame."""
        if self._source is None:
            return None
        oriented = transform.apply_orientation(
            self._source, self.flip_h, self.flip_v, self.rotation
        )
        if self._mode == MODE_WHITE_BALANCE:
            return oriented
        balanced = transform.apply_white_balance(oriented, self.white_balance)
        if self._mode == MODE_CROP:
            return balanced
        return transform.apply_crop(balanced, self.crop)

    # ----- coordinate mapping ------------------------------------------

    def _scale(self) -> float:
        if self._base_w == 0:
            return 1.0
        return self._target.width() / self._base_w

    def _widget_to_image(self, x: float, y: float) -> QPointF:
        s = self._scale() or 1.0
        ix = (x - self._target.x()) / s
        iy = (y - self._target.y()) / s
        ix = min(max(ix, 0.0), float(self._base_w))
        iy = min(max(iy, 0.0), float(self._base_h))
        return QPointF(ix, iy)

    def _image_to_widget(self, p: QPointF) -> QPointF:
        s = self._scale()
        return QPointF(self._target.x() + p.x() * s, self._target.y() + p.y() * s)

    # ----- mouse --------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if self._mode == MODE_VIEW or event.button() != Qt.LeftButton:
            return
        self._dragging = True
        self._drag_start = self._widget_to_image(event.position().x(), event.position().y())
        self._drag_end = QPointF(self._drag_start)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        self._drag_end = self._widget_to_image(event.position().x(), event.position().y())
        if self._mode in (MODE_MEASURE, MODE_CALIBRATE):
            self.measured.emit(self._line_length())
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self._dragging or event.button() != Qt.LeftButton:
            return
        self._dragging = False
        if self._mode == MODE_CROP:
            self._finish_crop()
        elif self._mode == MODE_MEASURE:
            self.measured.emit(self._line_length())
        elif self._mode == MODE_CALIBRATE:
            length = self._line_length()
            if length > 1.0:
                self.calibrate_done.emit(length)
        elif self._mode == MODE_WHITE_BALANCE:
            gains = self._sample_white_balance()
            if gains is not None:
                self.white_balance_picked.emit(gains)
        self.update()

    def _sample_white_balance(self) -> list | None:
        """Average a small region around the drag/click and return BGR gains."""
        base = self._base_frame()
        if base is None:
            return None
        h, w = base.shape[:2]
        x0 = min(self._drag_start.x(), self._drag_end.x())
        y0 = min(self._drag_start.y(), self._drag_end.y())
        x1 = max(self._drag_start.x(), self._drag_end.x())
        y1 = max(self._drag_start.y(), self._drag_end.y())
        if x1 - x0 < 4 or y1 - y0 < 4:  # treat as a click: box around the point
            cx, cy, half = self._drag_end.x(), self._drag_end.y(), 8
            x0, y0, x1, y1 = cx - half, cy - half, cx + half, cy + half
        x0 = int(max(0, min(x0, w - 1)))
        y0 = int(max(0, min(y0, h - 1)))
        x1 = int(max(x0 + 1, min(x1, w)))
        y1 = int(max(y0 + 1, min(y1, h)))
        return transform.gains_from_patch(base[y0:y1, x0:x1])

    def _line_length(self) -> float:
        return math.hypot(
            self._drag_end.x() - self._drag_start.x(),
            self._drag_end.y() - self._drag_start.y(),
        )

    def _finish_crop(self) -> None:
        x = min(self._drag_start.x(), self._drag_end.x())
        y = min(self._drag_start.y(), self._drag_end.y())
        w = abs(self._drag_end.x() - self._drag_start.x())
        h = abs(self._drag_end.y() - self._drag_start.y())
        if w < 5 or h < 5:
            return
        self.crop = [round(x), round(y), round(w), round(h)]
        self.crop_changed.emit(self.crop)

    # ----- painting -----------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 24, 28))

        base = self._base_frame()
        if base is None:
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(self.rect(), Qt.AlignCenter, "No video")
            return

        self._base_h, self._base_w = base.shape[:2]
        rgb = cv2.cvtColor(base, cv2.COLOR_BGR2RGB)
        self._rgb = np.ascontiguousarray(rgb)
        self._qimage = QImage(
            self._rgb.data, self._base_w, self._base_h,
            self._rgb.strides[0], QImage.Format_RGB888,
        )

        # letterbox into the widget
        scale = min(self.width() / self._base_w, self.height() / self._base_h)
        disp_w = self._base_w * scale
        disp_h = self._base_h * scale
        ox = (self.width() - disp_w) / 2
        oy = (self.height() - disp_h) / 2
        self._target = QRectF(ox, oy, disp_w, disp_h)

        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(self._target, self._qimage)

        self._draw_guides(painter)
        self._draw_interaction(painter)

    def _draw_guides(self, painter: QPainter) -> None:
        r = self._target
        if self.show_thirds:
            pen = QPen(QColor(255, 255, 255, 110))
            pen.setWidth(1)
            painter.setPen(pen)
            for i in (1, 2):
                x = r.x() + r.width() * i / 3
                y = r.y() + r.height() * i / 3
                painter.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
                painter.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        if self.show_crosshair:
            pen = QPen(QColor(0, 220, 120, 200))
            pen.setWidth(1)
            painter.setPen(pen)
            cx = r.x() + r.width() / 2
            cy = r.y() + r.height() / 2
            painter.drawLine(QPointF(cx, r.top()), QPointF(cx, r.bottom()))
            painter.drawLine(QPointF(r.left(), cy), QPointF(r.right(), cy))

    def _draw_interaction(self, painter: QPainter) -> None:
        # existing crop outline while editing
        if self._mode == MODE_CROP and self.crop:
            x, y, w, h = self.crop
            tl = self._image_to_widget(QPointF(x, y))
            br = self._image_to_widget(QPointF(x + w, y + h))
            pen = QPen(QColor(255, 200, 0, 160))
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(QRectF(tl, br))

        if not (self._dragging or self._mode in (MODE_MEASURE, MODE_CALIBRATE)):
            return
        if self._drag_start == self._drag_end:
            return

        a = self._image_to_widget(self._drag_start)
        b = self._image_to_widget(self._drag_end)

        if self._mode == MODE_CROP:
            pen = QPen(QColor(255, 200, 0))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(QRectF(a, b).normalized())
        elif self._mode == MODE_WHITE_BALANCE:
            pen = QPen(QColor(0, 230, 230))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(QRectF(a, b).normalized())
        elif self._mode in (MODE_MEASURE, MODE_CALIBRATE):
            color = QColor(80, 180, 255) if self._mode == MODE_MEASURE else QColor(255, 120, 200)
            pen = QPen(color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(a, b)
            for pt in (a, b):
                painter.drawEllipse(pt, 3, 3)
