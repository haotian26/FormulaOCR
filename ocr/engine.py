"""Backend-independent OCR engine."""

from __future__ import annotations

from .backend import FormulaOCRBackend, ONNXFormulaBackend, ImageInput
from .result import OCRResult


class FormulaOCREngine:
    """Own one backend instance and reuse its loaded model."""

    def __init__(self, backend: FormulaOCRBackend | None = None):
        self.backend = backend or ONNXFormulaBackend()

    def load(self) -> None:
        self.backend.load()

    def recognize(self, image: ImageInput) -> OCRResult:
        return self.backend.recognize(image)

    def recognize_variants(
        self,
        image: ImageInput,
        variants: tuple[str, ...] = ("context8", "context16"),
    ) -> list[OCRResult]:
        recognize_variants = getattr(self.backend, "recognize_variants", None)
        if callable(recognize_variants):
            return list(recognize_variants(image, variants))
        return [self.backend.recognize(image)]

    def is_loaded(self) -> bool:
        return self.backend.is_loaded()
