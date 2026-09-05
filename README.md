<p align="center">
  <img src="resources/icons/formulaocr-modern.svg" width="88" alt="FormulaOCR icon">
</p>

<h1 align="center">FormulaOCR</h1>

<p align="center">
  Turn a formula image into editable LaTeX or a Word equation on macOS.
</p>

<p align="center">
  English · <a href="README.zh-CN.md">简体中文</a>
</p>

FormulaOCR is a small desktop tool built for the part that usually interrupts
writing: copying a formula out of a screenshot, paper, slide, or PDF. Drop in an
image, check the result, make any corrections, then copy it as LaTeX or as an
editable Word equation.

Recognition runs locally. The optional API feature is separate and only sends
the current image when you click **API re-recognize**.

## What it can do

- Open, paste, or capture a formula from the screen.
- Recognize formulas offline with PP-FormulaNet_plus-L.
- Switch between chemistry formatting and ordinary mathematics formatting.
- Edit LaTeX and see the rendered result beside it.
- Copy LaTeX or an editable Word equation.
- Keep local recognition history and separate local/API drafts.
- Run from the menu bar and use a configurable screenshot shortcut.
- Switch the complete interface between English and Simplified Chinese.
- Connect to OpenAI-compatible or Mathpix APIs when local recognition needs a
  second opinion.

## Install

Download the latest DMG from [Releases](https://github.com/haotian26/FormulaOCR/releases/latest),
open it, and drag FormulaOCR into Applications.

The current build is for Apple Silicon (`arm64`) with macOS 14 or newer. It is ad-hoc signed but not
Apple-notarized, so macOS may ask you to Control-click the app and choose
**Open** the first time. Screenshot OCR also needs Screen Recording permission.

## A few things worth knowing

- OCR is not infallible. Small charges, degree symbols, closely spaced scripts,
  and low-resolution images may still need a manual correction.
- The bundled L model makes the installed app fairly large. The model is kept
  out of Git and included only in the packaged application.
- Chemistry mode changes presentation, such as keeping chemical species
  upright. It does not invent missing elements, charges, or coefficients.
- Local OCR, editing, preview, copying, and history work without a network
  connection. See [PRIVACY.md](PRIVACY.md) for the API boundary.

## Build from source

You will need Apple Silicon macOS 14+, Xcode Command Line Tools, Rust, Node.js 20+
and Python 3.10–3.13.

```bash
npm ci
python3 -m venv /private/tmp/formulaocr-venv
/private/tmp/formulaocr-venv/bin/python -m pip install -e . PyInstaller pytest
/private/tmp/formulaocr-venv/bin/python tools/download_model.py
FORMULAOCR_PYTHON=/private/tmp/formulaocr-venv/bin/python tools/build_tauri_app.sh
```

`tools/download_model.py` downloads the fixed model version and verifies its
SHA256 before use. FormulaOCR never downloads a model while the app is running.

Basic checks:

```bash
npm run build
PYTHONPATH=. /private/tmp/formulaocr-venv/bin/python -m pytest -q tests
PYTHONPATH=. /private/tmp/formulaocr-venv/bin/python tools/test_consistency.py
cargo check --manifest-path src-tauri/Cargo.toml
```

## Project layout

- `src/` — React interface
- `src-tauri/` — macOS integration and Sidecar lifecycle
- `sidecar/` — local JSON Lines service
- `ocr/` — preprocessing, ONNX inference, and result formatting
- `converter/` — LaTeX to MathML conversion used for Word equations

## Contributors

FormulaOCR is maintained by [Haotian](https://github.com/haotian26), with
development assistance from OpenAI Codex. See [CONTRIBUTORS.md](CONTRIBUTORS.md).

Issues and pull requests are welcome. If you report a recognition problem,
please use a small non-private image and include the raw LaTeX output.

## License

MIT. Third-party components and model attribution are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
