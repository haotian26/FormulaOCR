# Stage C clipboard and Word verification

Date: 2026-08-08

## Automated checks

Historical command (run from the project root in an isolated Stage C
environment, which was removed after verification):

```bash
PYTHONPATH=. /private/tmp/formulaocr-stage-c/bin/python tools/test_stage_c.py
```

Result: PASS for superscripts, fractions, Greek letters, arrows,
thermodynamic symbols, cases and braces. `copy_latex()` produced only
`text/plain`; `copy_word()` produced `text/html`, `text/mathml` and
`application/mathml+xml`, with the exact LaTeX retained as the plain-text
fallback.

The test uses a fake clipboard for deterministic MIME inspection. A direct
Qt clipboard process launched from the restricted shell cannot access the
macOS pasteboard service, so the system-pasteboard check was performed in a
user-session browser instead.

## Word macOS verification

1. A local browser page wrote the same HTML/MathML + plain-LaTeX payload to the
   macOS clipboard through `ClipboardItem`.
2. The payload was pasted into a new unsaved Word document with `Cmd+V`.
3. Word rendered an editable equation object: the accessibility tree reported
   `Description: 公式`, the equation tab appeared, and the font changed to
   Cambria Math. The rendered expression was
   `(a²+b²)/c² → ΔG`.

This confirms that the chosen Word-oriented MIME payload is accepted by the
installed Word for macOS. No user document was opened or saved.

## Scope boundary

Automatic copy, screenshot capture, global hotkeys and the PySide6 GUI remain
out of scope until their assigned stages.
