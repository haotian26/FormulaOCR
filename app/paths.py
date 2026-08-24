"""Paths that work from a source checkout and a bundled macOS application."""

from __future__ import annotations

import sys
import os
from pathlib import Path


def project_root() -> Path:
    """Return the directory containing the application resources.

    PyInstaller exposes the unpacked application directory as ``_MEIPASS``.
    In a source checkout, this file lives below the project root.  No user
    directory is embedded in the application.
    """

    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root)
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = project_root()
RESOURCES_DIR = PROJECT_ROOT / "resources"
MODELS_DIR = RESOURCES_DIR / "models"
FORMULA_MODEL_PATH = Path(os.environ["FORMULAOCR_MODEL_PATH"]).expanduser() if os.environ.get("FORMULAOCR_MODEL_PATH") else (
    MODELS_DIR / "PP-FormulaNet_plus-L-ONNX" / "pp_formulanet_plus_l.onnx"
)


def require_file(path: Path, description: str) -> Path:
    """Validate a packaged/local resource without attempting a download."""

    if not path.is_file():
        raise FileNotFoundError(
            f"{description} not found at {path}. "
            "FormulaOCR does not download models automatically."
        )
    return path
