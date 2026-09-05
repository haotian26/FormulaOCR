# FormulaOCR — current state

Version: **0.4.1 local acceptance candidate**

Platform: Apple Silicon, macOS 14 or newer

License: MIT (third-party components retain their own licenses)

## Application

- Tauri 2 native shell, React/TypeScript interface, Python JSON Lines sidecar.
- One bundled PP-FormulaNet_plus-L ONNX model; no runtime model download.
- Offline recognition, native MathML preview, Word/LaTeX clipboard and local history.
- Chinese/English interface; independent, per-page settings drafts.
- Optional OpenAI-compatible and Mathpix profiles; API recognition is manual.
- Existing history, settings and Keychain credentials are preserved.

## 0.4.1 review

The implementation and verification are described in [REVIEW_0.4.1.md](REVIEW_0.4.1.md).
Primary fixes concern stale asynchronous results, editing/history boundaries,
atomic settings and credentials, native shortcut/quit handling, and layout.

Model weights, OCR decoding and the existing adaptive safety margin are unchanged.
Do not interpret successful rendering as recognition accuracy.

## Quality gates

- Python: production tests in `tests/` (legacy Qt scripts remain in `tools/`).
- React: interaction tests for settings, keyboard recording, drafts and layout state.
- WebKit: real frontend at minimum window size, both languages and themes, settings
  scrolling, image-first recognition, late API responses and per-image Undo.
- Native: macOS build and signed-bundle verification; manual lifecycle acceptance.
- Private reference images remain local and excluded from Git.
- GitHub Actions is not enabled yet; run the documented checks locally.

## Outstanding boundaries

A complex reference image still produces malformed LaTeX at the OCR source.
Keep that output editable and show the rendering error; do not invent a fix.
Small charges and degree symbols remain known model limitations. Native Word
paste fidelity requires checking the user's actual Word version.

A build is not a public release. This review does not publish a Git tag, GitHub
Release or DMG. Do not replace this candidate label with "final" or "zero bugs"
without the corresponding acceptance evidence.
