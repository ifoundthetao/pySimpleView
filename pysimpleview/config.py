"""Persistent application settings, stored as JSON in the macOS app-support dir."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

APP_NAME = "pySimpleView"

DEFAULTS: dict[str, Any] = {
    "device_index": 0,
    "output_dir": str(Path.home() / "Pictures" / "pySimpleView"),
    "single_name": "capture",
    "convention": "resistors-${%04d}.png",
    "follow_convention": False,
    "image_format": "png",
    # orientation
    "flip_h": False,
    "flip_v": False,
    "rotation": 0,  # 0, 90, 180, 270
    # overlays
    "show_crosshair": False,
    "show_thirds": False,
    "burn_overlays": False,
    # crop rectangle in transformed-image coords: [x, y, w, h] or None
    "crop": None,
    # white-balance gains [b, g, r] or None
    "white_balance": None,
    # calibration
    "scale_units_per_px": None,  # float or None
    "scale_unit": "µm",
    # AI identification (API keys live in the keychain, not here)
    "vision_provider": "minimax",
    "vision_model": "",       # empty -> provider preset default
    "vision_base_url": "",    # empty -> provider preset default
    "vision_prompt": (
        "You are identifying a small electronic component or object under a USB "
        "microscope. If it is a resistor, read the colour bands and state the "
        "resistance value and tolerance, listing the band colours you see. For "
        "other components, give the type and any visible markings or part "
        "numbers. Be concise."
    ),
}


def config_dir() -> Path:
    base = Path.home() / "Library" / "Application Support" / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    return config_dir() / "settings.json"


class Config:
    """Dict-backed settings object that persists to disk on save()."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        path = config_path()
        if path.exists():
            try:
                stored = json.loads(path.read_text())
                if isinstance(stored, dict):
                    self._data.update(stored)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        try:
            config_path().write_text(json.dumps(self._data, indent=2))
        except OSError:
            pass

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)
