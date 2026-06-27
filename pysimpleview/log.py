"""Lightweight, opt-in diagnostic logging.

Logging is silent unless ``PYSIMPLEVIEW_LOG`` is set. Examples::

    PYSIMPLEVIEW_LOG=1                uv run python -m pysimpleview   # debug to stderr
    PYSIMPLEVIEW_LOG=info             uv run python -m pysimpleview   # info level
    PYSIMPLEVIEW_LOG=/tmp/psv.log     uv run python -m pysimpleview   # debug to a file

When a path is given (anything that isn't a level name / 0 / 1 / true / false),
logs go to that file as well as stderr — handy for capturing a hard crash.
"""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False
_LEVELS = {"debug", "info", "warning", "error", "critical"}


def setup() -> None:
    """Configure the ``pysimpleview`` logger from ``PYSIMPLEVIEW_LOG``."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    raw = os.environ.get("PYSIMPLEVIEW_LOG", "").strip()
    if not raw or raw.lower() in {"0", "false", "no"}:
        return

    logger = logging.getLogger("pysimpleview")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    lowered = raw.lower()
    if lowered in _LEVELS:
        logger.setLevel(getattr(logging, lowered.upper()))
    elif lowered in {"1", "true", "yes"}:
        logger.setLevel(logging.DEBUG)
    else:
        # Treat anything else as a log file path.
        try:
            fh = logging.FileHandler(raw)
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError as exc:  # pragma: no cover - bad path, fall back to stderr
            sys.stderr.write(f"pysimpleview: cannot log to {raw!r}: {exc}\n")

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.debug("logging initialised (PYSIMPLEVIEW_LOG=%r)", raw)


def get(name: str) -> logging.Logger:
    """Return a child logger; ``name`` is usually the module's ``__name__``."""
    return logging.getLogger(name if name.startswith("pysimpleview") else f"pysimpleview.{name}")
