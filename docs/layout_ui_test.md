# Modern Layout UI Test

## Offscreen regression

```bash
QT_QPA_PLATFORM=offscreen /private/tmp/formulaocr-stage-h-venv/bin/python \
  tools/test_layout_ui.py
```

Result: `modern layout shell: PASS`.

The check covers the floating history drawer, unchanged result splitter sizes
when the drawer opens, drawer width persistence, versioned layout state, the
three-mode layout selector, and the reset path. The frozen-app visual check is
still required on the current macOS desktop after rebuilding the candidate.
