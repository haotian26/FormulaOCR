# FormulaOCR 0.3.0 Tauri migration

This document records the completed React/Tauri migration contract.
The product name remains **FormulaOCR**. During development, builds use the
internal identifier `com.formulaocr.FormulaOCRApp.dev`, an empty data root and
the `FormulaOCR API Dev` Keychain service. The production identifier is restored
only after acceptance.

## Boundaries

- The Python ONNX/API/conversion/history core remains authoritative.
- The UI communicates with a long-running Python sidecar over JSON Lines; no
  localhost HTTP service is introduced.
- API upload remains an explicit user action. No automatic remote fallback is
  added by the migration.
- The installed `/Applications/FormulaOCR.app` is not modified during
  development.

## Protocol

Every request is `{id, method, params}`. Every response is either
`{id, ok:true, result}` or `{id, ok:false, error:{code,message,retryable}}`.
Images are retained in sidecar memory by `imageId` and are released explicitly.
Supported method names are documented in the migration plan and must remain
backwards compatible within 0.3.x.

## Functional parity

The top toolbar, image/result split, LaTeX/preview split, result toolbar,
history drawer, five settings pages, Command–V, native screenshot, API button,
Word/LaTeX copy, menu-bar behavior, Dock lifecycle and layout persistence must
remain available. React visual changes may improve spacing and accessibility,
but may not remove an existing workflow.

## Acceptance gates

1. Sidecar contract and existing Stage C–H Python tests pass.
2. React/Tauri UI passes light/dark, minimum-size and keyboard interaction tests.
3. macOS manual tests pass for paste, screenshot, Word copy, global shortcut,
   menu bar, Dock quit, history and API re-recognition.
4. The release build is arm64, signed, contains one L model and one sidecar,
   and is verified before any replacement or publication.

## Data compatibility

Application upgrades replace only the app bundle. History, settings, layout,
API profiles and Keychain secrets remain local and are not cleared by normal
installation or upgrade. macOS TCC permissions are not reset automatically.
