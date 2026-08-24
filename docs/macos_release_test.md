# Stage G macOS release test

Date: 2026-08-08

## Local Apple Silicon build

The standalone app was built with PyInstaller 6.21.0 from the ONNX-only
environment using `packaged_gui.py` as the double-click GUI entry point. The
model was added as application data, and `latex2mathml` data was explicitly
included because its `unimathsymbols.txt` file is required at import time.

The resulting bundle is arm64 and ad-hoc signed:

```text
/private/tmp/formulaocr-stage-g-build/dist/FormulaOCR.app
```

The reproducible `FormulaOCR.spec` reads the project root `VERSION` file.
For this release, `Contents/Info.plist` contains both
`CFBundleShortVersionString=0.1.1` and `CFBundleVersion=0.1.1`.

The DMG was created with macOS `hdiutil`:

```text
~/Downloads/FormulaOCR-v0.1.1.dmg
```

The DMG contains the arm64 `FormulaOCR.app` and only the selected
`PP-FormulaNet_plus-M-ONNX` weight. The legacy Paddle `PP-FormulaNet_plus-M`
directory remains in the source tree for audit/reference but is not bundled in
the application or DMG.

The app bundle launched without Python, pip or Homebrew on the host. Its
accessibility tree showed the FormulaOCR window, the splitters and the
editable LaTeX editor. The app loaded the local ONNX model and recognized a
sample image offline; the status reported completion and enabled both copy
buttons.

The refreshed bundle was also launched after replacing the application-wide
Python event filter with Qt's application-state signal. This avoids the
startup crash seen in the earlier frozen build while retaining Dock/menu-bar
window restoration. The live accessibility tree exposed `设置 → 窗口行为`
and the checkbox toggled successfully between enabled and disabled states.

The final bundle uses a native AppKit `NSStatusItem` for the menu bar, with the
Qt tray implementation retained as the non-macOS/offscreen fallback. The
custom FormulaOCR app icon is embedded as `FormulaOCR.icns`. The bundle
identifier is `com.formulaocr.FormulaOCRApp`; using a dedicated identifier is
important on macOS 26 because launching the earlier `com.formulaocr.FormulaOCR`
build from the Codex environment caused Control Center to group the item under
Codex and mark it unavailable.

After reinstalling and launching the dedicated bundle through LaunchServices,
System Settings → 菜单栏 → 允许在菜单栏显示 lists `FormulaOCR` with the
toggle on. The local Control Center ledger contains a separate
`com.formulaocr.FormulaOCRApp` entry with `isAllowed: true`.

The packaged build also includes polarity normalization for dark screenshots.
For the white-on-dark `FormulaOCR` wordmark regression, inference now returns
the text form `\\mathsf { F o r m u l a O C R }` instead of repeated fractions.

`复制 Word` from the packaged app was pasted into a new Word document. Word
created an equation object, reported `公式`, and used Cambria Math, matching
the Stage C clipboard verification.

The packaged screenshot button entered the native macOS interactive selector.
The selector could not be completed through the current Computer Use bridge
because it exposes no accessibility window while active; the same native
capture path and real Retina crop were already verified in the Stage E macOS
test.

## Window close behavior

The standalone app keeps its menu-bar item alive when the main window is
closed. In `设置 → 窗口行为`, the default option `关闭主窗口后隐藏 Dock 图标
（菜单栏继续运行）` hides the Dock icon on close; turning the option off keeps
the Dock icon visible. The menu-bar `打开 FormulaOCR` action restores the
window and the regular Dock activation policy.

On the local desktop, clicking the title-bar close button left the FormulaOCR
process running with no FormulaOCR window visible; activating the bundle again
restored the main window.

## Remaining migration gate

The required second Apple Silicon Mac test has not been performed in this
workspace. Stage G therefore remains partial until the bundle is copied to a
different Apple Silicon Mac and tested disconnected with no Python, pip or
Homebrew:

```text
启动 → 截图 → OCR → 复制 → Word 粘贴
```
