"""OCR worker kept outside the GUI thread."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot

from ocr.result import OCRResult


EngineFactory = Callable[[], Any]


def default_engine_factory() -> Any:
    """Import the OCR runtime only when the first GUI OCR request arrives."""
    from app.application import build_engine

    return build_engine()


class OCRWorker(QObject):
    """Lazy-load one engine and process requests on its owning QThread."""

    result_ready = Signal(str, object)
    error = Signal(str)

    def __init__(self, engine_factory: EngineFactory = default_engine_factory) -> None:
        super().__init__()
        self._engine_factory = engine_factory
        self._engine: FormulaOCREngine | None = None

    @Slot(str)
    def recognize(self, image_path: str) -> None:
        try:
            if self._engine is None:
                self._engine = self._engine_factory()
            result = self._engine.recognize(Path(image_path))
        except Exception as exc:
            self.error.emit(str(exc))
            return
        if not isinstance(result, OCRResult):
            self.error.emit("OCR backend returned an invalid result")
            return
        self.result_ready.emit(image_path, result)
