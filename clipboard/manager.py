"""Copy raw LaTeX or a Word-oriented MathML clipboard payload."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtGui import QGuiApplication

from converter.latex_to_mathml import latex_to_mathml


class ClipboardManager:
    """Own a Qt clipboard handle and expose explicit export formats."""

    def __init__(self, application: QGuiApplication | None = None) -> None:
        self._application = application or QGuiApplication.instance()
        if self._application is None:
            self._application = QGuiApplication([])
        self._clipboard = self._application.clipboard()

    def copy_latex(self, latex: str) -> None:
        """Copy only the exact LaTeX text."""
        self._clipboard.setText(latex)

    def copy_word(self, latex: str) -> str:
        """Copy MathML plus plain-LaTeX fallback for Word paste."""
        mathml = latex_to_mathml(latex)
        mime = QMimeData()
        # If a target application ignores MathML, the user still gets the
        # exact OCR text rather than a silently rewritten approximation.
        mime.setText(latex)
        mime.setHtml(f"<html><body>{mathml}</body></html>")
        payload = QByteArray(mathml.encode("utf-8"))
        mime.setData("text/mathml", payload)
        mime.setData("application/mathml+xml", payload)
        self._clipboard.setMimeData(mime)
        return mathml
