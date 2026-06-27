"""Background thread that runs an image analysis without blocking the UI."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .vision.base import VisionProvider


class VisionThread(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        provider: VisionProvider,
        images: list[tuple[bytes, str]],
        prompt: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._provider = provider
        self._images = images
        self._prompt = prompt

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            result = self._provider.analyze(self._images, self._prompt)
            self.succeeded.emit(result)
        except Exception as exc:  # surfaced to the UI
            self.failed.emit(str(exc))
