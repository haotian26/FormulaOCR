"""Application composition root for the current CLI and future GUI."""

from __future__ import annotations

from pathlib import Path

from ocr.backend import ONNXFormulaBackend
from ocr.engine import FormulaOCREngine


def build_engine(model_path: Path | None = None) -> FormulaOCREngine:
    return FormulaOCREngine(ONNXFormulaBackend(model_path=model_path))
