"""Vision provider interface."""

from __future__ import annotations

import abc


class VisionError(Exception):
    """Raised when an image analysis request cannot be completed."""


class VisionProvider(abc.ABC):
    name = "base"

    @abc.abstractmethod
    def analyze(self, image_bytes: bytes, media_type: str, prompt: str) -> str:
        """Return the model's text response describing the image."""
        raise NotImplementedError
