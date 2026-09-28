# FormulaOCR — current state

Development version: **0.4.2** (local verification; not published)
Latest public release: **0.4.1**

Platform: Apple Silicon, macOS 14 or newer

License: MIT (third-party components retain their own licenses)

## Application

- Tauri 2 native shell, React/TypeScript interface, Python JSON Lines sidecar.
- One bundled PP-FormulaNet_plus-L ONNX model; no runtime model download.
- Offline recognition, native MathML preview, Word/LaTeX clipboard and local history.
- Chinese/English interface; independent, per-page settings drafts.
- Optional OpenAI-compatible and Mathpix profiles; API recognition is manual.
- Existing history, settings and Keychain credentials are preserved.
- Fit/actual-size image zoom and pan, history search and LaTeX export.
- Manual GitHub update check under General → About; no background update traffic.

## 0.4.2 work

Failed draft writes remain queued and block quit unless explicitly discarded.
Mode changes preserve manual input and ignore outdated formatting responses.
API profile edits invalidate in-flight test/model responses. Current images can
be rehydrated after a sidecar restart without replaying a paid recognition call.

The production model and preprocessing are unchanged. A separate INT8 trial
created a smaller file but failed to load; it must not be bundled. See
[MODEL_SIZE_EXPERIMENT.md](MODEL_SIZE_EXPERIMENT.md) for the labelled baseline,
measurement definitions and rejected candidate.

The CI workflow is prepared locally, including native fault tests and an
opt-in model benchmark. It is not active on GitHub until explicitly pushed
with workflow permission. This development update does not create a Release.

Local acceptance and remaining limitations are recorded in
[REVIEW_0.4.2.md](REVIEW_0.4.2.md).

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

Distribution uses a compressed UDBZ DMG, an arm64 application and ad-hoc signing.
The application is not Apple-notarized. Release checks and known limitations are
recorded in [RELEASE_0.4.1.md](RELEASE_0.4.1.md).
