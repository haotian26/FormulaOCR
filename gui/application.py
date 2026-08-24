"""GUI application entry point."""

from __future__ import annotations

import sys

from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths
from PySide6.QtWidgets import QApplication

from .main_window import FormulaOCRWindow


SINGLE_INSTANCE_NAME = "FormulaOCR-SingleInstance"


class SingleInstanceGuard:
    """Prevent duplicate GUI processes with a recoverable OS lock file."""

    def __init__(self, name: str = SINGLE_INSTANCE_NAME) -> None:
        self.name = name
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        lock_dir = Path(base or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation))
        try:
            lock_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            lock_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)) / "FormulaOCR"
            lock_dir.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(lock_dir / f"{name}.lock"))
        self.primary = self.lock.tryLock(0)
        if not self.primary and self.lock.error() != QLockFile.LockError.LockFailedError:
            fallback_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)) / "FormulaOCR"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.lock = QLockFile(str(fallback_dir / f"{name}.lock"))
            self.primary = self.lock.tryLock(0)
        if not self.primary:
            self.lock.removeStaleLockFile()
            self.primary = self.lock.tryLock(0)

    def close(self) -> None:
        if self.primary:
            self.lock.unlock()


def run_gui(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setOrganizationName("FormulaOCR")
    app.setApplicationName("FormulaOCR")
    guard = SingleInstanceGuard()
    if not guard.primary:
        return 0
    window = FormulaOCRWindow()
    app.setQuitOnLastWindowClosed(not window.has_tray_menu)
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    try:
        return app.exec()
    finally:
        guard.close()
