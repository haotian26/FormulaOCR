"""Regression check for Command+V image/text routing in the main window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gui.main_window import FormulaOCRWindow


class EmptyProfiles:
    api_enabled = False
    active_profile_id = ""

    def load_profiles(self):
        return []

    def set_active_profile_id(self, _value):
        pass


class TestSettings:
    auto_copy = False
    hotkey = ""
    hide_dock_on_close = True
    api_profiles = EmptyProfiles()

    def set_auto_copy(self, _value):
        pass

    def set_hotkey(self, _value):
        pass

    def set_hide_dock_on_close(self, _value):
        pass


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = FormulaOCRWindow(engine_factory=lambda: None, settings=TestSettings())
    window.show()
    app.processEvents()
    captured: list[tuple[Path, bool]] = []
    window.start_ocr = lambda path, temporary=False: captured.append((Path(path), temporary))
    try:
        window.local_latex_edit.setFocus()
        app.processEvents()
        QApplication.clipboard().setText("x^2")
        window._paste_action.trigger()
        assert window.local_latex_edit.toPlainText() == "x^2"

        image = QImage(4, 4, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        QApplication.clipboard().setImage(image)
        window._paste_action.trigger()
        assert len(captured) == 1 and captured[0][1] is True

        # A real platform paste key is handled by the focused editor before
        # the main-window QAction.  The editor must route image data itself.
        QApplication.clipboard().setImage(image)
        window.local_latex_edit.setFocus()
        app.processEvents()
        QTest.keyClick(window.local_latex_edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        app.processEvents()
        assert len(captured) == 2 and captured[1][1] is True
        print("Command-V image/text routing: PASS")
    finally:
        for path, _temporary in captured:
            path.unlink(missing_ok=True)
        window.shutdown()
        app.processEvents()


if __name__ == "__main__":
    main()
