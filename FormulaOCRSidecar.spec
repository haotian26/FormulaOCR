"""PyInstaller recipe for the Tauri Python OCR sidecar."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

project = Path(SPECPATH).resolve()

a = Analysis(
    [str(project / "sidecar_entry.py")],
    pathex=[str(project)],
    binaries=[],
    # The production L model is a separate Tauri resource. Keeping it out of
    # PyInstaller avoids a 680 MB one-file extraction on every cold launch.
    datas=collect_data_files("latex2mathml"),
    hiddenimports=[
        "onnxruntime",
        "tokenizers",
        "latex2mathml",
        "httpx",
        "keyring.backends.macOS",
    ],
    excludes=["PySide6", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="formulaocr-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="formulaocr-sidecar",
)
