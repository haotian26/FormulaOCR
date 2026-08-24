# -*- mode: python ; coding: utf-8 -*-
"""Reproducible arm64 macOS bundle definition for FormulaOCR."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


ROOT = Path(SPECPATH).resolve()
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

datas = [
    (str(ROOT / "resources/icons/FormulaOCR.icns"), "resources/icons"),
    (str(ROOT / "resources/models/PP-FormulaNet_plus-L-ONNX"), "resources/models/PP-FormulaNet_plus-L-ONNX"),
]
datas += collect_data_files("latex2mathml")


a = Analysis(
    [str(ROOT / "packaged_gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "httpx",
        "keyring",
        "keyring.backends.macOS",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FormulaOCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / "resources/icons/FormulaOCR.icns")],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FormulaOCR",
)
app = BUNDLE(
    coll,
    name="FormulaOCR.app",
    icon=str(ROOT / "resources/icons/FormulaOCR.icns"),
    version=VERSION,
    bundle_identifier="com.formulaocr.FormulaOCRApp",
    info_plist={"CFBundleVersion": VERSION},
)
