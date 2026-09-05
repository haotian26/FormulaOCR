# 0.4.1 review and acceptance

This candidate focuses on reliability and everyday usability. It does not change
the OCR model or claim an increase in recognition accuracy.

## Findings and changes

| Area | Problem | Change |
| --- | --- | --- |
| Recognition | A late API response could overwrite a newer image | Request identity is checked on success, failure and completion |
| Clipboard | Slow automatic conversion could copy an older image after navigation | Recheck request identity and the current edit before copying |
| Input | Clipboard handling depended on browser clipboard support | Native PNG/TIFF paste; image preview appears before inference |
| Input | Transparent backgrounds could turn into black ink | Alpha is composited onto white; EXIF orientation is respected |
| Editing | The first rapid edit could fail to enable Undo | The first edit always begins a group; source/image histories stay separate |
| History | Empty drafts could be replaced with OCR text on reload | Empty is distinguished from missing; both source branches are restored |
| History | API after restoring history could create disconnected state | The reopened image retains its existing history record ID |
| History | Concurrent access used one unprotected SQLite connection | History operations serialize with a reentrant lock |
| History | Delayed saves could race with navigation | A cancellable draft queue flushes on source/image changes and quit |
| Settings | Whole-settings writes could overwrite another window's update | Validated, atomic per-page patches |
| Settings | Shortcut registration and saved state could disagree | Register on Save; preserve the old shortcut on failure |
| Settings | Option-modified keys were recorded as composed characters | Record physical key codes and finish on key release |
| API | Fetch/test feedback was confused with saved feedback | Separate transient result messages from successful Save |
| API | Failed credential saves could leave partial changes | Keychain rollback and atomic metadata replacement |
| API | Invalid endpoints or incomplete enabled profiles were accepted by the UI | Inline validation; HTTPS required except localhost |
| Preview | Unsupported aligned environments rendered literal ampersands | Render-only aligned-to-align* adapter, with table-structure tests |
| Preview | Invalid/hidden formulas could appear successful | Validate balanced structure, visible content and safe MathML |
| Layout | Percentages plus divider thickness exceeded the available area | Dividers have fixed width; panes divide only the remaining space |
| Layout | Long names and fixed-size controls squeezed one another | Truncated profile labels, consistent fields and bounded compact controls |
| Appearance | Disabled Save remained blue; dark selects lost their arrow | Explicit disabled colors and component-specific dark styles |
| Lifecycle | Dynamic shortcuts and quit cleanup had inconsistent ownership | Central native handler, recording suppression and idempotent shutdown |
| Lifecycle | Hidden WebKit views could suspend screenshot event processing | Disable background throttling on the supported macOS runtime |
| Packaging | Tauri metadata allowed macOS 13 while the bundled ONNX dylib required 14 | Set the effective minimum to macOS 14 |
| Maintenance | UI and settings were one large module, with sparse regression coverage | Separate settings, state, events, types and validation; add automated test suites |

## Verification

- 39 Python regression cases cover settings, Keychain rollback, history, invalid
  images, rendering, aligned formulas and mocked API HTTP failures.
- 26 Vitest cases cover settings Save/discard, physical shortcut recording,
  draft queues, layout restoration and localization.
- Eight WebKit tests exercise actual React/CSS/CodeMirror in both languages,
  light/dark themes and a 900×650 main window. The settings test checks aligned
  field heights, wheel scrolling and an always-visible Save footer.
- Development dependency audit reports zero known vulnerabilities at review time.
- Native Rust compilation succeeds. There is no automated claim that a Rust
  compile alone proves Dock, tray, screenshot or Word behavior.

### Packaged macOS application

- Version 0.4.1, arm64, ad-hoc code signature verified with deep/strict checks.
- One model and one sidecar, without PySide6. Allocated bundle size increased by
  about 1.1 MiB compared with the previously installed app (about 0.13%).
- The packaged sidecar completed a real recognition in 668 ms while a concurrent
  settings request returned in 0.2 ms. Shutdown exited successfully. Its cold
  health response took about 4 seconds; the frontend opens independently, so this
  is not a claim that the backend is ready immediately on launch.
- In the actual app: settings opened, unsaved close prompted, Discard removed
  the draft, API scrolling worked, all 16 existing history records remained,
  and restoring a record produced native MathML with superscripts/subscripts.
- Native Word copy reported success. Paste fidelity in Word remains a separate
  human acceptance check.
- Closing the main window kept the main and sidecar processes alive. Opening the
  same app from Finder restored its window. Command–Q then ended both processes.
- Installed at `/Applications/FormulaOCR.app` and launched from that location.
  Version, signature and both process paths were checked again; the original
  16 history records were still present. The prior app bundle is retained in a
  temporary rollback directory. No settings or credentials were reset.

### Offline reference replay

The 16 original samples and 16 local-history images were read without modifying
the history database. All 32 tensors match the previous RGB input path exactly.
The same model, tokenizer, preprocessing and decoding code are retained.

Model load in the local replay took 958 ms. Individual inference times ranged
from 560 to 2938 ms on this Mac; these are observations, not universal guarantees.
After the aligned-environment adapter, 31 of 32 results can be converted. The
remaining sample has malformed grouping in the model output and is reported as
an error. These numbers measure input consistency and rendering, **not accuracy**.

Model SHA256:
`5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8`

## Repeat the checks

```sh
npm ci
npm test
npm run build
npx playwright install webkit
npm run test:ui
python -m pytest -q
cargo check --locked --manifest-path src-tauri/Cargo.toml
# Optional, local private reference images:
PYTHONPATH=. python tools/check_input_regression.py path/to/reference/images
python tools/check_packaged_sidecar.py path/to/FormulaOCR.app path/to/sample.png
```

The browser suite mocks only native transport; Python tests separately exercise
the backend. The packaged sidecar check uses temporary, empty storage. Tests do
not contact a real recognition API or modify production keys.

## Remaining acceptance

- A human should check copied equations in their installed version of Word.
- Real API tests are opt-in because they use credentials and contact a service.
- Multi-monitor recovery needs a physical multi-monitor acceptance run.
- The L model can still omit or confuse small symbols. Improving that requires
  a separately labelled benchmark, not heuristic charge correction.
- Apple notarization is not supplied by ad-hoc signing.

No public release or DMG is created by this review.
