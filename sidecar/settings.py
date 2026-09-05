"""Versioned, atomic settings patches shared by both application windows."""

import json
import os
import tempfile
import threading
from pathlib import Path


DEFAULTS = {
    "auto_copy": False,
    "hide_dock_on_close": True,
    "hotkey": "ctrl+alt+cmd+o",
    "history_limit": 200,
    "layout_restore_mode": "remember_window_history_closed",
    "layout_version": 3,
    "default_recognition_mode": "chemistry",
    "language": "zh-CN",
}


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def validate_patch(values: dict) -> dict:
    if not isinstance(values, dict):
        raise ValueError("settings values must be an object")
    for key in ("auto_copy", "hide_dock_on_close"):
        if key in values and type(values[key]) is not bool:
            raise ValueError(f"{key} must be a boolean")
    for key, options in {
        "language": {"zh-CN", "en"},
        "default_recognition_mode": {"chemistry", "math"},
        "layout_restore_mode": {"remember_window_history_closed", "restore_full_state", "optimized_default"},
    }.items():
        if key in values and values[key] not in options:
            raise ValueError(f"invalid {key}")
    if "history_limit" in values and (type(values["history_limit"]) is not int or not 20 <= values["history_limit"] <= 2000):
        raise ValueError("history_limit must be between 20 and 2000")
    if "hotkey" in values and not isinstance(values["hotkey"], str):
        raise ValueError("hotkey must be a string")
    # Unknown keys are preserved on read for forward compatibility, but cannot
    # be introduced through the settings UI (in particular, never credentials).
    return {key: value for key, value in values.items() if key in DEFAULTS}


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def get(self) -> dict:
        with self.lock:
            values = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
            if not isinstance(values, dict):
                raise ValueError("Settings file is not a JSON object; the original file was preserved")
            return {**DEFAULTS, **values}

    def save(self, values: dict) -> dict:
        patch = validate_patch(values)
        with self.lock:
            result = {**self.get(), **patch}
            atomic_json(self.path, result)
            return result
