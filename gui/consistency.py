"""Asynchronous local MathML rendering used for OCR candidate ranking."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QObject, QTimer, Qt, QUrl, Signal

from converter import MathMLConversionError, latex_to_mathml
from ocr.result import OCRResult
from ocr.validation import ValidationScore, compare_images


class FormulaConsistencyRenderer(QObject):
    """Render candidates off-screen and compare them with the source image."""

    completed = Signal(int, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._view = None
        self._source_path: Path | None = None
        self._request_id = 0
        self._queue: list[OCRResult] = []
        self._scores: list[tuple[OCRResult, ValidationScore | None]] = []
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtWebEngineWidgets import QWebEngineView

            if QApplication.instance() is not None and QApplication.platformName() != "offscreen":
                self._view = QWebEngineView()
                self._view.setWindowFlag(Qt.WindowType.Tool, True)
                self._view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
                self._view.resize(1600, 420)
                self._view.loadFinished.connect(self._on_loaded)
                self._view.show()
        except ImportError:
            self._view = None

    @property
    def available(self) -> bool:
        return self._view is not None

    def evaluate(self, request_id: int, source_path: Path, candidates: list[OCRResult]) -> None:
        self._request_id = request_id
        self._source_path = source_path
        self._queue = list(candidates)
        self._scores = []
        self._current_candidate = None
        if not self.available:
            QTimer.singleShot(0, lambda: self.completed.emit(request_id, self._scores))
            return
        self._render_next()

    def _render_next(self) -> None:
        if not self._queue:
            self.completed.emit(self._request_id, list(self._scores))
            return
        candidate = self._queue.pop(0)
        self._current_candidate = candidate
        try:
            html = self._html_for(candidate.formatted_latex)
        except (MathMLConversionError, TypeError):
            self._scores.append((candidate, None))
            QTimer.singleShot(0, self._render_next)
            return
        assert self._view is not None
        self._view.setHtml(html, QUrl("about:blank"))

    def _on_loaded(self, succeeded: bool) -> None:
        if not succeeded or self._view is None:
            if self._queue:
                candidate = self._queue.pop(0)
                self._scores.append((candidate, None))
            QTimer.singleShot(0, self._render_next)
            return
        QTimer.singleShot(90, self._capture_current)

    def _capture_current(self) -> None:
        if self._view is None or self._source_path is None:
            QTimer.singleShot(0, self._render_next)
            return
        # The queue is destructive, so the candidate being rendered is tracked
        # separately while the asynchronous page load completes.
        candidate = getattr(self, "_current_candidate", None)
        if candidate is None:
            QTimer.singleShot(0, self._render_next)
            return
        pixmap = self._view.grab()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        saved = not pixmap.isNull() and pixmap.save(buffer, "PNG")
        if not saved:
            self._scores.append((candidate, None))
        else:
            try:
                from PIL import Image

                rendered = Image.open(BytesIO(bytes(buffer.data()))).convert("L")
                score = compare_images(self._source_path, rendered, candidate.formatted_latex)
            except Exception as exc:
                score = ValidationScore(0.0, True, f"渲染校验失败：{exc}")
            self._scores.append((candidate, score))
        self._current_candidate = None
        QTimer.singleShot(0, self._render_next)

    @staticmethod
    def _html_for(latex: str) -> str:
        fragment = latex_to_mathml(latex)
        return f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
html,body {{ margin:0; padding:0; background:#fff; width:100%; height:100%; }}
body {{ font-family:'Cambria Math','STIX Two Math',serif; }}
.formula {{ box-sizing:border-box; width:100%; min-height:100%; padding:30px;
            display:flex; align-items:center; justify-content:center; }}
math {{ display:block; font-size:42px; }}
</style></head><body><div class='formula'>{fragment}</div></body></html>"""
