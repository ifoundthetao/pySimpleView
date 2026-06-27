"""Filename convention handling.

A convention is a string containing a single ``${<printf-int-spec>}`` token,
e.g. ``resistors-${%04d}.png``. The token is replaced with an auto-incrementing
counter that resumes from the highest number already present in the output dir.
"""

from __future__ import annotations

import re
from pathlib import Path

TOKEN_RE = re.compile(r"\$\{([^}]*)\}")


def has_token(pattern: str) -> bool:
    return TOKEN_RE.search(pattern) is not None


def _apply_spec(spec: str, number: int) -> str:
    """Format ``number`` with a printf int spec like ``%04d`` (default ``%d``)."""
    spec = spec.strip() or "%d"
    try:
        return spec % number
    except (TypeError, ValueError):
        return str(number)


def next_filename(pattern: str, output_dir: str | Path, start: int = 1) -> str:
    """Return the next filename for ``pattern`` inside ``output_dir``.

    Scans the directory for existing files matching the pattern, then returns the
    pattern with the token filled by ``max_existing + 1`` (or ``start`` if none).
    Patterns without a token are returned unchanged.
    """
    match = TOKEN_RE.search(pattern)
    if not match:
        return pattern

    spec = match.group(1)
    prefix = pattern[: match.start()]
    suffix = pattern[match.end() :]

    file_re = re.compile(
        "^" + re.escape(prefix) + r"(\d+)" + re.escape(suffix) + "$"
    )

    highest = 0
    found = False
    directory = Path(output_dir)
    if directory.is_dir():
        for entry in directory.iterdir():
            m = file_re.match(entry.name)
            if m:
                found = True
                highest = max(highest, int(m.group(1)))

    number = highest + 1 if found else start
    return prefix + _apply_spec(spec, number) + suffix


def resolve_single_name(name: str, image_format: str) -> str:
    """Ensure a single-shot name has an image extension."""
    name = name.strip() or "capture"
    if Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
        return name
    return f"{name}.{image_format.lstrip('.')}"
