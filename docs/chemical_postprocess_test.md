# Stage F conservative chemical formatting

Date: 2026-08-08

Stage F keeps the model output in `OCRResult.raw_latex` and exposes a separate
`formatted_latex` value for the GUI, clipboard and normal CLI output. The
formatter performs syntax-only rewrites:

- braces unbraced element subscripts and charge superscripts;
- removes FormulaNet token-separator spaces and repairs spaced scripts such as
  `_ { 2 }` and `^ { - }`;
- renders unambiguous chemical terms in an equation with upright `\\mathrm{}`
  glyphs without changing the raw OCR result;
- canonicalizes textual and Unicode reaction arrows to LaTeX commands;
- removes harmless whitespace between LaTeX commands and their arguments;
- preserves `\\text{...}` payloads and already-braced structures;
- is idempotent.

Case refinement is a separate image-evidence step. When FormulaNet emits an
uppercase parenthesized token such as `(S)`, macOS Vision checks the original
image. A lowercase correction is applied only when all parenthesized alphabetic
groups align case-insensitively and in order, and Vision's candidate confidence
is at least 0.8. Legitimate uppercase image text, mismatches, unavailable Vision
results, and non-macOS runs keep FormulaNet's original case. `raw_latex` is
always preserved.

It does not balance reactions, change coefficients, infer valence or species,
consult a chemical database, or reverse an arrow. The CLI JSON includes both
`raw_latex` and formatted `latex` fields for auditability.

## Verification

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/formulaocr-stage-f/bin/python tools/test_stage_f.py
```

Results: PASS for element subscripts, charge superscripts, reaction arrows,
reaction-condition command spacing, protected text payloads, raw-result
preservation, idempotence and CLI raw/formatted fields. Stage C, D and E
regression suites also passed after the formatter was connected to the GUI.
