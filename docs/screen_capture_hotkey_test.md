# Stage E screen capture and hotkey verification

Date: 2026-08-08

## Automated offscreen checks

Historical command (the isolated environment was removed after verification):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. \
  /private/tmp/formulaocr-stage-e/bin/python tools/test_stage_e.py
```

Results: PASS for the Cocoa global-hotkey bridge, custom hotkey parse/roundtrip,
QSettings persistence, multi-display Retina crop, duplicate-capture guarding,
selection overlay fallback to OCR worker, and Esc cancellation. Repeated
key-down events are ignored. On macOS, the production path now invokes the
system interactive `screencapture -i -s -c` selector and reads the returned
clipboard image; the custom overlay remains only as a non-macOS/test fallback.
The fake capture used
two display geometries, including a negative-origin display, and retained a
2× crop scale.

## Real macOS check

One GUI instance was launched and `截图 OCR` was clicked. The application
called the macOS CoreGraphics Screen Recording preflight/request path and
displayed:

```text
需要 macOS 屏幕录制权限：请在系统设置中允许 FormulaOCR
```

After Screen Recording permission was granted to the Python.app host, the
authorized Python.app process reported `CGPreflightScreenCaptureAccess = true`.
The GUI now invokes macOS's native interactive selector
`/usr/sbin/screencapture -i -s -c` rather than drawing a custom full-screen
selection layer. A live selector run returned a cropped clipboard image to the
GUI, which passed it to OCR; the FormulaOCR window itself was not included in
the crop.

## Scope and gate

The global hotkey is user-editable in the GUI; the default is
Control-Option-Command-O. The tray menu contains open, 截图 OCR and quit
actions. The app uses a worker thread for OCR and removes temporary screenshot
files after completion or cancellation. Stage E is `COMPLETE`; Stage F is the
next gated stage.
