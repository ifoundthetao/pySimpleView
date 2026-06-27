"""Camera enumeration and a background capture thread."""

from __future__ import annotations

import sys

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from . import log

_log = log.get(__name__)


def _make_capture(index: int) -> cv2.VideoCapture:
    """Open a capture device, preferring AVFoundation on macOS."""
    if sys.platform == "darwin":
        cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
        if cap.isOpened():
            _log.debug("opened camera %d via AVFoundation", index)
            return cap
        cap.release()
        _log.debug("AVFoundation failed for camera %d, trying default backend", index)
    cap = cv2.VideoCapture(index)
    _log.debug("camera %d default backend isOpened=%s", index, cap.isOpened())
    return cap


def list_devices(max_index: int = 6, exclude: set[int] | None = None) -> list[int]:
    """Return indices of cameras that open and deliver a frame.

    Indices in ``exclude`` are not probed at all. Pass cameras that are already
    open elsewhere (a live capture/preview), already known to be present, or
    known-bad — reopening them would either fight the live capture or keep
    hammering a flaky device.
    """
    exclude = exclude or set()
    _log.debug("list_devices(max_index=%d, exclude=%s)", max_index, sorted(exclude))
    available: list[int] = []
    for i in range(max_index):
        if i in exclude:
            continue
        cap = _make_capture(i)
        try:
            if cap.isOpened():
                ok, _ = cap.read()
                _log.debug("probe camera %d: opened=True read_ok=%s", i, ok)
                if ok:
                    available.append(i)
            else:
                _log.debug("probe camera %d: opened=False", i)
        finally:
            cap.release()
    _log.debug("list_devices -> %s", available)
    return sorted(available)


class CaptureThread(QThread):
    """Continuously reads frames from a device and emits them as BGR arrays.

    A flaky device (unpowered hub, KVM) can briefly drop off the bus and come
    back. Rather than give up the moment reads start failing, the thread tries
    to reopen the device a few times with exponential backoff, only declaring it
    lost after the retries are exhausted.
    """

    frame_ready = Signal(object)  # numpy.ndarray, BGR
    error = Signal(str)
    camera_lost = Signal(int)  # index; emitted once we give up on the device
    reconnecting = Signal(int, int, int)  # index, attempt, max_attempts
    recovered = Signal(int)  # index; a reconnect attempt succeeded

    # Reads in a row that may fail before we treat the stream as dropped.
    MAX_READ_FAILURES = 10
    # How many times to reopen a dropped device before giving up.
    MAX_RECONNECTS = 5
    # Backoff between reconnect attempts: BASE * 2**(attempt-1), capped at MAX.
    RECONNECT_BASE_MS = 250
    RECONNECT_MAX_MS = 3000

    def __init__(self, index: int, parent=None) -> None:
        super().__init__(parent)
        self._index = index
        self._running = False

    def run(self) -> None:  # noqa: D401 - QThread entry point
        _log.debug("CaptureThread[%d] starting", self._index)
        self._running = True
        total = 0
        attempt = 0  # consecutive (re)connect tries since the last live stream
        try:
            while self._running:
                session = self._stream_once()
                total += session
                if not self._running:
                    break
                if session > 0 and attempt > 0:
                    _log.info("CaptureThread[%d] recovered", self._index)
                    self.recovered.emit(self._index)
                # A live stream that delivered frames resets the retry budget;
                # an attempt that produced nothing counts against it.
                attempt = 0 if session > 0 else attempt
                attempt += 1
                if attempt > self.MAX_RECONNECTS:
                    _log.warning(
                        "CaptureThread[%d] giving up after %d reconnect "
                        "attempt(s) (%d frames delivered total)",
                        self._index, attempt - 1, total,
                    )
                    self.error.emit(
                        f"Camera {self._index} stopped responding "
                        f"(unpowered hubs / KVMs can cause this). "
                        f"Click “Change camera…” to retry."
                    )
                    self.camera_lost.emit(self._index)
                    return
                delay = self._backoff_ms(attempt)
                _log.info(
                    "CaptureThread[%d] reconnecting, attempt %d/%d in %dms",
                    self._index, attempt, self.MAX_RECONNECTS, delay,
                )
                self.reconnecting.emit(self._index, attempt, self.MAX_RECONNECTS)
                if not self._sleep(delay):
                    break
        except Exception:  # pragma: no cover - surface unexpected crashes in logs
            _log.exception("CaptureThread[%d] crashed in capture loop", self._index)
            self.camera_lost.emit(self._index)
        finally:
            _log.debug("CaptureThread[%d] stopped (delivered %d frames total)",
                       self._index, total)

    def _stream_once(self) -> int:
        """Open the device and stream until it drops or we're stopped.

        Returns the number of frames delivered during this session (0 if the
        device could not be opened or never produced a frame).
        """
        cap = _make_capture(self._index)
        if not cap.isOpened():
            cap.release()
            _log.debug("CaptureThread[%d] open failed", self._index)
            return 0
        frames = 0
        failures = 0
        try:
            while self._running:
                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    if failures >= self.MAX_READ_FAILURES:
                        _log.debug(
                            "CaptureThread[%d] stream dropped after %d frames",
                            self._index, frames,
                        )
                        break
                    self.msleep(60)
                    continue
                failures = 0
                frames += 1
                self.frame_ready.emit(frame)
                self.msleep(15)
        finally:
            cap.release()
        return frames

    def _backoff_ms(self, attempt: int) -> int:
        return min(self.RECONNECT_MAX_MS, self.RECONNECT_BASE_MS * 2 ** (attempt - 1))

    def _sleep(self, ms: int) -> bool:
        """Sleep in small slices so stop() stays responsive during backoff.

        Returns False if a stop was requested while waiting.
        """
        waited = 0
        while waited < ms:
            if not self._running:
                return False
            chunk = min(50, ms - waited)
            self.msleep(chunk)
            waited += chunk
        return self._running

    def stop(self) -> None:
        _log.debug("CaptureThread[%d] stop() requested", self._index)
        self._running = False
        if not self.wait(2000):
            _log.warning("CaptureThread[%d] did not stop within 2s "
                         "(read likely blocked in the driver)", self._index)
