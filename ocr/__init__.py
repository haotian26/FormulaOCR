"""Offline formula OCR engine and backend interfaces."""

from .engine import FormulaOCREngine
from .result import OCRResult
from .postprocess import RecognitionMode, normalize_latex
from .validation import (
    ValidationScore,
    compare_images,
    latex_structure_valid,
    outer_wrapper_has_image_evidence,
    strip_outer_latex_wrappers,
)

__all__ = [
    "FormulaOCREngine",
    "OCRResult",
    "ValidationScore",
    "compare_images",
    "latex_structure_valid",
    "outer_wrapper_has_image_evidence",
    "strip_outer_latex_wrappers",
    "normalize_latex",
    "RecognitionMode",
]
