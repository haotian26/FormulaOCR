# Stage D GUI smoke test

Date: 2026-08-08

## Automated offscreen checks

Historical command (the isolated environment was removed after verification):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. \
  /private/tmp/formulaocr-stage-d/bin/python tools/test_stage_d.py
```

Results: PASS for the single-instance lock, OCR worker thread, automatic copy
OFF by default, automatic copy ON/settings write, manual LaTeX copy, and
clipboard-image paste into OCR. The fake engine recorded OCR on a non-GUI
QThread.

The main window has a `粘贴图片` button and the standard paste shortcut. The
global screenshot shortcut is edited from the `设置` secondary menu, not in
the main content area. Its editor accepts an empty sequence: pressing Esc and
saving disables the global screenshot shortcut.

The content area has a vertical splitter with draggable handles above and below
the result area, so the source-image preview, result panes and footer can each
be resized. The result area has a second draggable horizontal splitter: the
left LaTeX editor is writable and the right pane renders the current LaTeX as
MathML in the local Qt WebEngine view. Aligned OCR formulas are rendered
row-by-row so long multi-line results remain visible in the preview.
Updates are debounced by 100 ms while typing and do not require network access.
If an edit is temporarily incomplete, the preview explains that the brackets
or environment must be completed; unsupported commands are reported separately
and do not affect the editable LaTeX or Word-copy path.

## Real macOS GUI check

Using one temporary app launch:

1. `打开图片` selected `tests/samples/2026-08-08_02-34-15.png`.
2. The GUI preview appeared and the OCR result field returned non-empty LaTeX
   in about 417 ms.
3. `复制 Word` changed the status to `已复制 Word 格式（含 LaTeX fallback）`.
4. Pasting into a new unsaved Word document produced an editable equation
   object; Word's accessibility tree reported `Description: 公式`.

The GUI uses a recoverable lock file, so a second process exits immediately.
No screenshot capture or global shortcut is included in this stage.
