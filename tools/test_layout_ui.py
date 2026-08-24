"""Offscreen regression checks for the modern shell and layout persistence."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QPushButton

from gui.main_window import FormulaOCRWindow
from gui.settings import LayoutRestoreMode


class EmptyProfiles:
    api_enabled = False
    active_profile_id = ""

    def load_profiles(self):
        return []

    def set_active_profile_id(self, _value):
        pass


class Settings:
    auto_copy = False
    hotkey = ""
    hide_dock_on_close = True
    history_limit = 200
    layout_restore_mode = LayoutRestoreMode.REMEMBER_CLOSED_HISTORY
    api_profiles = EmptyProfiles()

    def __init__(self):
        self.values = {}

    def set_auto_copy(self, _value):
        pass

    def set_hide_dock_on_close(self, _value):
        pass

    def set_layout_value(self, key, value):
        self.values[key] = value

    def layout_value(self, key, default=None):
        return self.values.get(key, default)

    def set_layout_restore_mode(self, value):
        self.layout_restore_mode = value

    def remove_layout_values(self):
        self.values.clear()

    def sync(self):
        pass


def main() -> None:
    app = QApplication.instance() or QApplication([])
    settings = Settings()
    window = FormulaOCRWindow(engine_factory=lambda: None, settings=settings)
    window.show()
    app.processEvents()
    try:
        initial = window.content_splitter.sizes()
        window.history_button.click()
        app.processEvents()
        assert window.history_overlay.isVisible()
        assert window.content_splitter.sizes() == initial
        window.history_overlay.hide_drawer(animate=False)
        app.processEvents()
        assert not window.history_overlay.isVisible()

        window.history_overlay.set_drawer_width(400)
        assert window.history_overlay.drawer_width == 400
        window._layout_restored = True
        window._save_layout_state()
        assert settings.values["history_width"] == 400
        assert settings.values["version"] == 3

        window.show_layout_settings()
        layout_dialog = next(
            child for child in window.findChildren(QDialog)
            if child.windowTitle() == "界面与布局"
        )
        combo = layout_dialog.findChild(QComboBox)
        combo.setCurrentIndex(combo.findData(LayoutRestoreMode.SMART_DEFAULT))
        save = next(button for button in layout_dialog.findChildren(QPushButton) if button.text() == "保存")
        save.click()
        assert settings.layout_restore_mode == LayoutRestoreMode.SMART_DEFAULT
        print("modern layout shell: PASS")
    finally:
        window.shutdown()
        app.processEvents()


if __name__ == "__main__":
    main()
