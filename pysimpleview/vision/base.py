"""Vision provider interface."""

from __future__ import annotations

import abc


class VisionError(Exception):
    """Raised when an image analysis request cannot be completed."""


class VisionProvider(abc.ABC):
    name = "base"

    @abc.abstractmethod
    def analyze(self, images: list[tuple[bytes, str]], prompt: str) -> str:
        """Return the model's text response describing the image(s).

        ``images`` is a list of ``(image_bytes, media_type)`` pairs — one entry
        for a single shot, or several (e.g. different angles/lighting of the
        same subject) for the model to reason over together.
        """
        raise NotImplementedError
