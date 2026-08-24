"""Offscreen GUI smoke checks for the Stage D workflow."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QImage, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter

from gui.application import SingleInstanceGuard
from gui.main_window import FormulaOCRWindow
from ocr.result import OCRResult


class FakeEngine:
    def __init__(self, thread_ids: list[int]) -> None:
        self.thread_ids = thread_ids

    def recognize(self, image: Path) -> OCRResult:
        self.thread_ids.append(0 if QThread.currentThread() == QApplication.instance().thread() else 1)
        return OCRResult(raw_latex=r"\\frac{a}{b}", confidence=None, elapsed_ms=1.0)


class FakeClipboard:
    def __init__(self) -> None:
        self.word_calls = 0
        self.latex_calls = 0

    def copy_word(self, latex: str) -> str:
        self.word_calls += 1
        return latex

    def copy_latex(self, latex: str) -> None:
        self.latex_calls += 1


class FakeSettings:
    def __init__(self) -> None:
        self.auto_copy = False
        self.hotkey = "ctrl+alt+cmd+o"
        self.hide_dock_on_close = True
        self.saved: list[bool] = []

    def set_auto_copy(self, enabled: bool) -> None:
        self.auto_copy = enabled
        self.saved.append(enabled)

    def set_hotkey(self, value: str) -> None:
        self.hotkey = value

    def set_hide_dock_on_close(self, enabled: bool) -> None:
        self.hide_dock_on_close = enabled


def wait_for_result(window: FormulaOCRWindow) -> None:
    for _ in range(40):
        QTest.qWait(25)
        if window.latex_edit.toPlainText():
            return
    raise AssertionError("worker did not return a result")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    guard_name = f"FormulaOCR-test-{uuid.uuid4().hex}"
    first_guard = SingleInstanceGuard(guard_name)
    second_guard = SingleInstanceGuard(guard_name)
    assert first_guard.primary and not second_guard.primary
    first_guard.close()
    print("single-instance guard: PASS")

    worker_thread_ids: list[int] = []
    clipboard = FakeClipboard()
    settings = FakeSettings()

    def factory() -> FakeEngine:
        return FakeEngine(worker_thread_ids)

    window = FormulaOCRWindow(
        engine_factory=factory,  # type: ignore[arg-type]
        clipboard_manager=clipboard,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
    )
    assert not window.latex_edit.isReadOnly()
    assert window.formula_preview is not None
    assert window._paste_action.shortcut().matches(QKeySequence.StandardKey.Paste) == QKeySequence.SequenceMatch.ExactMatch
    assert window.content_splitter.orientation().name == "Vertical"
    assert window.result_splitter.orientation().name == "Horizontal"
    assert all("可编辑" not in label.text() for label in window.findChildren(type(window.status_label)))
    assert len(window.findChildren(QSplitter)) >= 2
    aligned = r"\begin{aligned}a&=b\\&=c\end{aligned}"
    assert len(window.formula_preview._to_mathml_fragments(aligned)) == 2
    window.formula_preview._set_error(r"\frac{a", ValueError("incomplete"))
    assert "尚未输入完整" in window.formula_preview._fallback.text()
    window.show()
    window.hide()
    window._show_from_tray()
    assert window.isVisible()
    window._on_application_state_changed(Qt.ApplicationState.ApplicationActive)
    print("hidden window restore: PASS")
    window.show_window_settings()
    assert window._window_settings_dialog is not None
    option = window._window_settings_dialog.findChildren(type(window.auto_copy_checkbox))[0]
    option.setChecked(False)
    assert settings.hide_dock_on_close is False
    option.setChecked(True)
    assert settings.hide_dock_on_close is True
    window._window_settings_dialog.close()
    print("Dock/menu-bar window setting: PASS")
    print("editable LaTeX, formula preview and splitters: PASS")
    sample = Path("tests/samples/2026-08-08_02-32-28.png").resolve()
    window.start_ocr(sample)
    wait_for_result(window)
    assert window.latex_edit.toPlainText() == r"\\frac{a}{b}"
    assert clipboard.word_calls == 0, "auto copy must be off by default"
    assert worker_thread_ids and worker_thread_ids[0] == 1
    print("OCR worker thread: PASS")
    print("automatic copy OFF: PASS")

    window.auto_copy_checkbox.setChecked(True)
    window.start_ocr(sample)
    wait_for_result(window)
    assert clipboard.word_calls == 1
    assert settings.saved[-1] is True
    print("automatic copy ON and settings write: PASS")

    window.copy_latex_button.click()
    assert clipboard.latex_calls == 1
    print("manual copy LaTeX: PASS")

    window.auto_copy_checkbox.setChecked(False)
    pasted = QImage(32, 24, QImage.Format.Format_RGB32)
    pasted.fill(0xFFFFFFFF)
    QApplication.clipboard().setImage(pasted)
    window.paste_image()
    wait_for_result(window)
    assert window._temporary_capture is None
    print("paste image -> OCR: PASS")
    QApplication.clipboard().clear()
    policy_calls: list[bool] = []
    original_quit = QApplication.quit
    QApplication.quit = staticmethod(lambda: None)  # type: ignore[assignment]
    window._set_dock_icon_visible = lambda visible: policy_calls.append(visible)  # type: ignore[method-assign]
    window.quit_application()
    assert policy_calls == [], "quit must not restore the Dock activation policy"
    QApplication.quit = original_quit
    print("Dock quit lifecycle: PASS")
    window.close()
    app.processEvents()


if __name__ == "__main__":
    main()
