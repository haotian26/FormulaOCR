"""PyInstaller entry point for the standalone FormulaOCR macOS app."""

from main import gui_main


if __name__ == "__main__":
    raise SystemExit(gui_main())
