# FormulaOCR third-party notices

FormulaOCR retains the licenses of its third-party software and model. Packaged
apps include full notice texts and a versioned inventory at
`Contents/Resources/licenses/SOURCES.json`. The inventory covers installed
production JavaScript/Python dependencies and the macOS Cargo dependency graph;
some build-time and tree-shaken dependencies are included as well.

`tools/collect_runtime_notices.py` collects installed notices and, where packages
omit them, checks the matching source archive or upstream commit at build time.
Nothing is downloaded by the application at runtime. Cargo package source is
available through each versioned crates.io link in the inventory, including the
MPL-2.0-licensed `selectors` component.

## RapidDoc

- Project: RapidAI/RapidDoc
- URL: <https://github.com/RapidAI/RapidDoc>
- Inspected commit: `9704b2b63192e838627534611c369dc42141e5f8`
- License: Apache License 2.0
- Use in FormulaOCR: reference implementation for the PP-FormulaNet_plus-L
  ONNX preprocessing, session I/O and tokenizer metadata layout. No RapidDoc
  source file is copied into the application runtime.

## PP-FormulaNet_plus-L

- Model source: PaddleOCR model README / RapidDoc ModelScope mirror
- URL: <https://www.modelscope.cn/models/RapidAI/RapidDoc/resolve/v1.0.0/formula/PP-FormulaNet_plus-L/pp_formulanet_plus_l.onnx>
- License stated by the model README: Apache License 2.0
- SHA256: `5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8`

## 0.4.1 runtime dependencies

- ONNX Runtime, NumPy, Pillow and tokenizers: see the exact version ranges in
  `pyproject.toml`; used for the offline OCR runtime.
- Tauri 2: Apache-2.0 OR MIT; native application shell, windows, tray and IPC.
  Transitive Rust packages retain their individual licenses in the inventory.
- React, CodeMirror 6 and Lucide: MIT; interactive UI, editor and icons.
- PySide6 remains only in the legacy reference GUI and is excluded from the
  production Sidecar/App bundle.
- latex2mathml: MIT (version 3.81.0); used to convert OCR LaTeX to MathML for
  Word paste while preserving the original LaTeX as plain-text fallback.
- pyobjc-framework-Cocoa / pyobjc-core: MIT (version 12.2.2); macOS-only
  bridge used for the global hotkey monitor. The dependency is conditional on
  `sys_platform == 'darwin'`.
- httpx: BSD-3-Clause; optional HTTP transport used only for explicit remote API
  requests. It is never used by the offline ONNX path.
- keyring: MIT; used to store API credentials in the macOS Keychain. A release
  package must include its dependency notices and retain the system-keychain
  behavior without a plaintext fallback.

## Development-only benchmark dependencies

PaddlePaddle, OpenCV and PyYAML remain benchmark-only dependencies. Paddle is
not installed by the formal ONNX runtime.
