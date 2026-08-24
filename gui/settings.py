"""Persistent GUI settings."""

from __future__ import annotations

from PySide6.QtCore import QSettings

from api.config import APIProfileStore


class LayoutRestoreMode:
    """Stable persisted values for how the main window restores its layout."""

    REMEMBER_CLOSED_HISTORY = "remember_closed_history"
    REMEMBER_ALL = "remember_all"
    SMART_DEFAULT = "smart_default"

    ALL = (REMEMBER_CLOSED_HISTORY, REMEMBER_ALL, SMART_DEFAULT)


class AppSettings:
    """Small typed wrapper around QSettings for user-visible preferences."""

    def __init__(self) -> None:
        self._settings = QSettings("FormulaOCR", "FormulaOCR")
        self.api_profiles = APIProfileStore(self._settings)

    @property
    def auto_copy(self) -> bool:
        return self._settings.value("auto_copy", False, type=bool)

    def set_auto_copy(self, enabled: bool) -> None:
        self._settings.setValue("auto_copy", bool(enabled))
        self._settings.sync()

    @property
    def hotkey(self) -> str:
        return str(self._settings.value("hotkey", "ctrl+alt+cmd+o"))

    def set_hotkey(self, value: str) -> None:
        self._settings.setValue("hotkey", value)
        self._settings.sync()

    @property
    def hide_dock_on_close(self) -> bool:
        """Whether closing the main window hides the Dock icon but keeps the menu-bar app alive."""
        return self._settings.value("hide_dock_on_close", True, type=bool)

    def set_hide_dock_on_close(self, enabled: bool) -> None:
        self._settings.setValue("hide_dock_on_close", bool(enabled))
        self._settings.sync()

    @property
    def history_limit(self) -> int:
        value = self._settings.value("history_limit", 200, type=int)
        return max(20, min(2000, int(value)))

    def set_history_limit(self, value: int) -> None:
        self._settings.setValue("history_limit", max(20, min(2000, int(value))))
        self._settings.sync()

    @property
    def layout_restore_mode(self) -> str:
        value = str(
            self._settings.value(
                "layout_restore_mode",
                LayoutRestoreMode.REMEMBER_CLOSED_HISTORY,
            )
        )
        return value if value in LayoutRestoreMode.ALL else LayoutRestoreMode.REMEMBER_CLOSED_HISTORY

    def set_layout_restore_mode(self, value: str) -> None:
        mode = value if value in LayoutRestoreMode.ALL else LayoutRestoreMode.REMEMBER_CLOSED_HISTORY
        self._settings.setValue("layout_restore_mode", mode)
        self._settings.sync()

    def layout_value(self, key: str, default=None):
        return self._settings.value(f"layout/{key}", default)

    def set_layout_value(self, key: str, value) -> None:
        self._settings.setValue(f"layout/{key}", value)

    def remove_layout_values(self) -> None:
        self._settings.beginGroup("layout")
        self._settings.remove("")
        self._settings.endGroup()
        self._settings.sync()

    def sync(self) -> None:
        self._settings.sync()
