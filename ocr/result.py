"""Backend-independent OCR result types."""

from __future__ import annotations

from dataclasses import dataclass

from .postprocess import RecognitionMode, normalize_latex


@dataclass(frozen=True)
class OCRResult:
    raw_latex: str
    confidence: float | None
    elapsed_ms: float
    case_refined_latex: str | None = None
    variant: str = "baseline"
    initial_raw_latex: str | None = None
    candidate_count: int = 1
    visual_consistency: float | None = None
    validation_status: str = "single_pass"
    token_ids: tuple[int, ...] = ()

    @property
    def formatted_latex(self) -> str:
        """Conservative display/copy form; ``raw_latex`` remains untouched."""

        return normalize_latex(self.case_refined_latex or self.raw_latex)

    def format_for(self, mode: RecognitionMode) -> str:
        """Format the immutable OCR output for a selected presentation mode."""

        return normalize_latex(self.case_refined_latex or self.raw_latex, mode=mode)
