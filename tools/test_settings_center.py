"""Offscreen checks for the categorized settings center and toolbar actions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.main_window import FormulaOCRWindow


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = FormulaOCRWindow(engine_factory=lambda: None)
    window.show()
    app.processEvents()
    try:
        assert not hasattr(window, "nav_rail")
        assert window.settings_button.menu() is None
        window.show_settings_center("general")
        center = window._settings_center
        assert center is not None
        assert center.sidebar.count() == 5
        assert center.stack.count() == 5
        center.show_page("layout")
        assert center.sidebar.currentItem().data(Qt.ItemDataRole.UserRole) == "layout"
        page = center._pages["layout"]
        assert page.save_button.isEnabled() is False
        page.mode.setCurrentIndex((page.mode.currentIndex() + 1) % page.mode.count())
        assert page.save_button.isEnabled() is True
        page.save_button.click()
        assert page.save_button.isEnabled() is False
        assert page.save_button.text() == "保存"
        assert page.save_feedback.text() == "✓ 已保存"
        center.show_page("hotkey")
        hotkey = center._pages["hotkey"]
        hotkey.edit.setFocus()
        original_sequence = hotkey.edit.keySequence()
        modifiers = (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        QTest.keyPress(hotkey.edit, Qt.Key.Key_P, modifiers)
        QTest.keyRelease(hotkey.edit, Qt.Key.Key_P, modifiers)
        QTest.qWait(50)
        assert hotkey.save_button.text() == "保存"
        assert hotkey.save_button.isEnabled() is True
        hotkey.edit.setKeySequence(original_sequence)
        assert hotkey.save_button.isEnabled() is False
        general = center._pages["general"]
        original = general.auto_copy.isChecked()
        general.auto_copy.setChecked(not original)
        assert general.save_button.isEnabled() is True
        assert general.save_button.text() == "保存"
        old_question = QMessageBox.question
        QMessageBox.question = staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
        try:
            center.close()
            app.processEvents()
        finally:
            QMessageBox.question = old_question
        window.show_settings_center("general")
        app.processEvents()
        assert window._settings_center._pages["general"].auto_copy.isChecked() == original
        window._settings_center.close()
        app.processEvents()
        print("settings center: PASS")
    finally:
        window.shutdown()
        app.processEvents()


if __name__ == "__main__":
    main()
