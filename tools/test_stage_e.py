"""Offscreen checks for Stage E capture, cancel and hotkey plumbing."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QThread
from PySide6.QtGui import QImage, QKeySequence, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from gui.hotkey import GlobalHotkey, HotkeyBinding
from gui.main_window import FormulaOCRWindow
from gui.settings import AppSettings
from gui.screen_capture import (
    DesktopCapture,
    DisplaySnapshot,
    ScreenRecordingPermission,
)
from ocr.result import OCRResult


class FakeEngine:
    def recognize(self, image: Path) -> OCRResult:
        return OCRResult(r"x^2", None, 1.0)


class FakeClipboard:
    def copy_word(self, latex: str) -> str:
        return latex

    def copy_latex(self, latex: str) -> None:
        return None


class FakeSettings:
    auto_copy = False
    hotkey = HotkeyBinding.DEFAULT

    def set_auto_copy(self, enabled: bool) -> None:
        self.auto_copy = enabled

    def set_hotkey(self, value: str) -> None:
        self.hotkey = value


class FakePermission:
    def __init__(self, authorized: bool) -> None:
        self.authorized = authorized
        self.requested = False

    def is_authorized(self) -> bool:
        return self.authorized

    def request(self) -> bool:
        self.requested = True
        return self.authorized


def fake_capture() -> DesktopCapture:
    image_a = QImage(100, 100, QImage.Format.Format_RGBA8888)
    image_a.fill(Qt.GlobalColor.white)
    image_b = QImage(100, 100, QImage.Format.Format_RGBA8888)
    image_b.fill(Qt.GlobalColor.lightGray)
    return DesktopCapture(
        [
            DisplaySnapshot(QRect(0, 0, 100, 100), QPixmap.fromImage(image_a), 2.0),
            DisplaySnapshot(QRect(100, 0, 100, 100), QPixmap.fromImage(image_b), 1.0),
        ]
    )


def wait_for_latex(window: FormulaOCRWindow) -> None:
    for _ in range(40):
        QTest.qWait(25)
        if window.latex_edit.toPlainText():
            return
    raise AssertionError("screenshot OCR worker did not return")


def wait_for_overlay(window: FormulaOCRWindow) -> None:
    for _ in range(20):
        QTest.qWait(25)
        if window._overlay is not None:
            return
    raise AssertionError("screenshot overlay did not open")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    hotkey = GlobalHotkey()
    assert hotkey.available and hotkey.start()
    hotkey.stop()
    print("global hotkey bridge: PASS")

    custom = HotkeyBinding.from_storage("ctrl+shift+cmd+p")
    assert HotkeyBinding.from_qt_sequence(custom.qt_sequence()).storage == "ctrl+shift+cmd+p"
    print("custom hotkey parse/roundtrip: PASS")
    persisted = AppSettings()
    old_hotkey = persisted.hotkey
    persisted.set_hotkey(custom.storage)
    assert AppSettings().hotkey == custom.storage
    persisted.set_hotkey(old_hotkey)
    print("QSettings hotkey persistence: PASS")

    permission = ScreenRecordingPermission()
    print(f"screen recording preflight: {permission.is_authorized()}")

    capture = fake_capture()
    crop = capture.crop(QRect(50, 10, 100, 20))
    assert crop.width() == 200 and crop.height() == 40
    print("multi-display Retina crop: PASS")

    settings = FakeSettings()
    runtime_hotkey = GlobalHotkey()
    window = FormulaOCRWindow(
        engine_factory=lambda: FakeEngine(),  # type: ignore[arg-type]
        clipboard_manager=FakeClipboard(),  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
        capture_factory=fake_capture,
        screen_permission=FakePermission(True),  # type: ignore[arg-type]
        hotkey=runtime_hotkey,
    )
    assert any(action.text() == "设置" for action in window.menuBar().actions())
    print("hotkey settings secondary menu: PASS")
    window.show_hotkey_settings()
    assert window.hotkey_edit is not None and window.hotkey_save_button is not None
    assert not window.hotkey_save_button.isEnabled()
    window.hotkey_edit.setKeySequence(custom.qt_sequence())
    assert window.hotkey_save_button.isEnabled()
    window.hotkey_save_button.click()
    assert not window.hotkey_save_button.isEnabled()
    assert settings.hotkey == "ctrl+shift+cmd+p"
    assert runtime_hotkey.binding.storage == "ctrl+shift+cmd+p"
    print("GUI custom hotkey save: PASS")
    window.hotkey_edit.setFocus()
    QTest.keyClick(window.hotkey_edit, Qt.Key.Key_Escape)
    assert window.hotkey_edit.keySequence().isEmpty()
    assert window.hotkey_save_button.isEnabled()
    window.hotkey_save_button.click()
    assert not window.hotkey_save_button.isEnabled()
    assert settings.hotkey == ""
    assert runtime_hotkey.binding is None
    print("Esc clears hotkey: PASS")
    window._hotkey_dialog.close()
    window.capture_screen()
    wait_for_overlay(window)
    first_overlay = window._overlay
    window.capture_screen()
    assert first_overlay is not None and window._overlay is first_overlay
    first_overlay.cancel()
    print("duplicate capture guard: PASS")
    window.capture_screen()
    wait_for_overlay(window)
    assert window._overlay is not None
    overlay = window._overlay
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    QTest.mouseMove(overlay, QPoint(70, 40), delay=10)
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(70, 40))
    wait_for_latex(window)
    assert window.latex_edit.toPlainText() == r"x^{2}"
    assert window._temporary_capture is None
    print("screen selection -> OCR worker: PASS")

    window.capture_screen()
    wait_for_overlay(window)
    assert window._overlay is not None
    QTest.keyClick(window._overlay, Qt.Key.Key_Escape)
    assert "取消" in window.status_label.text()
    print("Esc cancel: PASS")

    window.shutdown()
    window.deleteLater()
    app.processEvents()


if __name__ == "__main__":
    main()
