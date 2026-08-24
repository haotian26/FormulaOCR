"""Offline Stage C checks for conversion and clipboard payload construction."""

from __future__ import annotations

from PySide6.QtCore import QMimeData

from clipboard import ClipboardManager
from converter import latex_to_mathml


class FakeClipboard:
    def __init__(self) -> None:
        self.text_value = ""
        self.mime_data: QMimeData | None = None

    def setText(self, text: str) -> None:
        self.text_value = text
        self.mime_data = QMimeData()
        self.mime_data.setText(text)

    def setMimeData(self, data: QMimeData) -> None:
        self.mime_data = data
        self.text_value = data.text()

    def text(self) -> str:
        return self.text_value

    def mimeData(self) -> QMimeData:
        assert self.mime_data is not None
        return self.mime_data


class FakeApplication:
    def __init__(self) -> None:
        self._clipboard = FakeClipboard()

    def clipboard(self) -> FakeClipboard:
        return self._clipboard


def main() -> None:
    samples = {
        "superscripts": r"x^2+y_{i}",
        "fractions": r"\frac{a^2+b^2}{c^2}",
        "greek": r"\alpha+\Omega",
        "arrows": r"A\rightarrow B\leftrightarrow C",
        "thermo": r"\Delta G=\Delta H-T\Delta S",
        "cases": r"\begin{cases}x^2,&x>0\\0,&x\le0\end{cases}",
        "braces": r"\left\{x\middle|x>0\right\}",
    }
    for name, source in samples.items():
        result = latex_to_mathml(source)
        assert result.startswith("<math") and result.endswith("</math>")
        print(f"{name}: PASS")

    app = FakeApplication()
    manager = ClipboardManager(app)  # type: ignore[arg-type]
    source = r"\frac{a}{b}"
    manager.copy_latex(source)
    assert app.clipboard().text() == source
    assert app.clipboard().mimeData().formats() == ["text/plain"]
    print("copy_latex: PASS")

    mathml = manager.copy_word(source)
    mime = app.clipboard().mimeData()
    assert app.clipboard().text() == source
    assert {"text/html", "text/mathml", "application/mathml+xml"}.issubset(mime.formats())
    assert bytes(mime.data("text/mathml")).decode("utf-8") == mathml
    print("copy_word: PASS")


if __name__ == "__main__":
    main()
