# Contributing

Contributions are welcome through GitHub issues and pull requests. Changes must
preserve raw OCR output, prove recognition changes on the regression set, and
pass Python, React and Rust checks. Formatting logic may not add or remove
mathematical or chemical meaning.

Do not commit model weights, generated applications, private formula images,
history databases, API responses or secrets. Keep recognition changes separate
from presentation-only formatting changes and include before/after evidence.

Run `npm test`, `npm run build`, `npm run test:ui` (after installing Playwright
WebKit), and `python -m pytest -q`. Native checks require macOS. The current
Python suite lives in `tests/`; old PySide6 scripts in `tools/` are reference
checks for the archived GUI and require the optional `legacy-gui` dependencies.

See [the 0.4.1 review](docs/REVIEW_0.4.1.md) for test boundaries and local bundle
checks. Passing mocks or compilation does not replace native acceptance testing.
