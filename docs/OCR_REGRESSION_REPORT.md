# OCR regression evidence — 2026-08-20

- Candidate model: PP-FormulaNet_plus-L ONNX
- Model SHA256: `5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8`
- Set replayed: 16 repository samples plus 9 current local-history images
- Single-pass inference: mean 700.7 ms; maximum 1939.3 ms on the current Mac
- Evidence file: `/private/tmp/formulaocr-regression-current.json`

Two history images containing `NdF_3 = Nd^{3+} + 3F^-` produced raw model output
ending in `+3F`, without the negative charge. The formatter correctly leaves the
charge absent: it does not guess or repair model semantics. Other images of the
related reaction produced raw `3F^{-}` and chemistry mode rendered it upright as
`3\mathrm{F}^{-}`.

The replay report records image, model and preprocessed-tensor SHA256 values,
token IDs, raw output, case-refined output, chemistry formatting and math
formatting. Replacing the model remains blocked until a candidate is better on
the same annotated set without regressions.

## Terminal charge follow-up — 2026-08-23

The current `Nd^{3+}+2SO_4^{2-}=Nd(SO_4)_2^-` history image was replayed through
the installed L model. The terminal minus is present in the original PNG, the
detected foreground box and the normalized 768×768 tensor. The baseline token
sequence nevertheless ends after the final subscript and omits the charge, so
this case is a decoder miss rather than a formatter deletion or literal crop.

Keeping 2% additional right-side context recovered the minus for this image,
but a 27-image comparison changed multiple unrelated formulas, including
matrix, long-form and chemistry outputs. The global preprocessing change was
therefore rejected. The application continues to preserve the raw output and
does not synthesize a charge without model evidence.
