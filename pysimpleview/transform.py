"""Image orientation and crop transforms shared by the view and capture path."""

from __future__ import annotations

import cv2
import numpy as np

_ROTATIONS = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def apply_orientation(
    frame: np.ndarray, flip_h: bool, flip_v: bool, rotation: int
) -> np.ndarray:
    """Apply horizontal/vertical flips then rotation. Returns a new array."""
    if flip_h:
        frame = cv2.flip(frame, 1)
    if flip_v:
        frame = cv2.flip(frame, 0)
    rot = _ROTATIONS.get(rotation % 360)
    if rot is not None:
        frame = cv2.rotate(frame, rot)
    return frame


def apply_white_balance(frame: np.ndarray, gains) -> np.ndarray:
    """Scale the B, G, R channels by ``gains`` (BGR order); clip to 0–255.

    A no-op when ``gains`` is falsy. Returns a new uint8 array.
    """
    if not gains:
        return frame
    out = frame.astype(np.float32)
    out *= np.asarray(gains, dtype=np.float32)  # broadcast over last axis (BGR)
    np.clip(out, 0, 255, out=out)
    return out.astype(np.uint8)


def gains_from_patch(patch: np.ndarray) -> list[float]:
    """Per-channel gains (BGR) that turn ``patch`` neutral while preserving its
    overall brightness. Gains are clamped to a sane range to avoid wild casts."""
    means = patch.reshape(-1, 3).mean(axis=0)  # BGR means
    means = np.maximum(means, 1.0)
    target = float(means.mean())
    return [float(np.clip(target / m, 0.2, 5.0)) for m in means]


def apply_crop(frame: np.ndarray, crop) -> np.ndarray:
    """Crop ``[x, y, w, h]`` (in transformed-image coords), clamped to bounds."""
    if not crop:
        return frame
    h, w = frame.shape[:2]
    x, y, cw, ch = (int(round(v)) for v in crop)
    x0 = max(0, min(x, w - 1))
    y0 = max(0, min(y, h - 1))
    x1 = max(x0 + 1, min(x + cw, w))
    y1 = max(y0 + 1, min(y + ch, h))
    return frame[y0:y1, x0:x1]
