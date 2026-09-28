# FormulaOCR 0.4.2 verification

Locally verified build, 28 September 2026. Distribution checks are recorded in
[RELEASE_0.4.2.md](RELEASE_0.4.2.md). Existing user data is retained.

## Changes

- Source images have Fit, 100%, zoom and bounded mouse/keyboard panning.
- History search covers local/API text and profile names. Export writes the
  selected records, or the filtered results, as UTF-8 LaTeX snippets using
  each record's active-source draft. Empty drafts stay empty.
- General settings includes About and an explicit GitHub update check. No
  checks, downloads or installs occur in the background.
- Failed history writes remain retryable. Quit waits for them or asks for an
  explicit discard. Queued edits and retries preserve the last selected source.
- Mode switching preserves manually entered text and Undo. New edits made
  during formatting or mode persistence cannot be overwritten by old values.
- API profile edits invalidate in-flight tests/model lists. Backend recovery
  restores the current image/history association without replaying OCR or API.

## Automated checks

| Check | Result |
| --- | --- |
| Python, `python -m pytest -q` | 94 passed |
| Frontend, `npm test` | 47 passed |
| Real WebKit, `npm run test:ui` | 20 passed |
| Native, `cargo test --locked --manifest-path src-tauri/Cargo.toml` | 6 passed |
| TypeScript and production frontend | Passed |
| `git diff --check` | Passed |

Native tests also passed with the CI-only `TAURI_CONFIG` resource list empty;
that permits protocol/native tests without downloading the model. It is not a
substitute for the signed-bundle checks below. The workflow remains local,
pending GitHub workflow permission; it is not included in this source push.

## Packaged runtime

The bundled executable and sidecar are arm64, version 0.4.2, targeting macOS
14+. The ad-hoc signature passes deep/strict verification; it is not notarized.
The bundle contains one L model and no matplotlib, evaluation-only ONNX package
or PySide6. The 363-component notice inventory has 600 verified notice hashes.

A disposable-storage packaged test performed real offline OCR, MathML
conversion, image release and clean shutdown. Settings returned while OCR was
running. A separate frozen-process restart test retained the history ID and
edited draft, restored the same image, and created no duplicate record or
automatic OCR/API call. These tests did not use user images or credentials.

Installed-app checks confirmed startup, settings/About, a manual GitHub update
check, history restoration, zoom and complete formula preview. Native export
Cancel re-enabled the button; Save wrote 16 record blocks as UTF-8 LaTeX with
owner-only file permissions. The temporary export was removed after checking.
The existing 16 history records remain intact. The old app is kept as a
recoverable copy in Trash; history, settings and Keychain are not reset.

The app uses approximately 844 MiB of allocated disk space, only about 200 KiB
more than the preceding installed build. See the release notes for DMG size.

## Recognition and size boundaries

Model weights, preprocessing, decoding and chemistry formatting are unchanged.
The model SHA256 remains
`5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8`.

The bounded INT8 experiment produced a smaller file but failed runtime graph
validation. It was rejected and removed, not bundled. The ten-case synthetic
baseline exposes existing symbol misses; it does not establish general OCR
accuracy. See [MODEL_SIZE_EXPERIMENT.md](MODEL_SIZE_EXPERIMENT.md) for raw
predictions, labels, measurements and acceptance rules.

Real paid API recognition, this user's Word-paste fidelity, screen-recording
permissions and every external-display configuration were not revalidated.
Small charges and degree symbols remain model limitations, not automatically
corrected chemistry.
