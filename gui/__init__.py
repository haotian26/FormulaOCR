"""Legacy PySide6 GUI package.

The Tauri sidecar imports shared history code from this package.  Keep the
Qt window lazy so the headless sidecar does not require PySide6 just to answer
health, image, or history protocol requests.
"""

__all__ = ["FormulaOCRWindow"]


def __getattr__(name: str):
    if name == "FormulaOCRWindow":
        from .main_window import FormulaOCRWindow
        return FormulaOCRWindow
    raise AttributeError(name)
