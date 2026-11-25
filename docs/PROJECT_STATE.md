# FormulaOCR — current state

Current version: **0.4.2**
Latest public release: **0.4.2**

Platform: Apple Silicon, macOS 14 or newer

License: MIT (third-party components retain their own licenses)

## Application

Local unreleased changes after 0.4.2: in-app destructive-action confirmations
and local Retry OCR replacing the offline badge. API controls remain separate.
Local retry preserves the existing API branch, its draft and undo history;
the resulting history record also retains API metadata and render status.
Regression coverage: 49 frontend unit tests and 29 WebKit tests, including
confirmation with browser dialogs disabled, cancellation and failed deletion.
The local arm64 app is installed and signature-verified. Native checks confirmed
the deletion dialog opens, Escape preserves all 18 existing records, and the
model field fills the available row. Destructive acceptance is tested against
synthetic records, not the user's history. These changes are not yet published.

- Tauri 2 native shell, React/TypeScript interface, Python JSON Lines sidecar.
- One bundled PP-FormulaNet_plus-L ONNX model; no runtime model download.
- Offline recognition, native MathML preview, Word/LaTeX clipboard and local history.
- Chinese/English interface; independent, per-page settings drafts.
- OpenAI-compatible and Mathpix profiles support manual recognition and opt-in API recognition for new images.
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
with workflow permission. It is not included in the release source commit.

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
recorded in [RELEASE_0.4.2.md](RELEASE_0.4.2.md).
