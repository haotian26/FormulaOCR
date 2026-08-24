# Settings center and toolbar UI test

Date: 2026-08-15

The offscreen regression script `tools/test_settings_center.py` verifies that:

- the permanent left navigation rail is absent;
- History remains a compact toolbar action and Settings is not a popup-menu button;
- the settings center exposes five categorized pages;
- the layout page keeps its save button disabled until a change, then disables it after saving;
- each page keeps the button label “保存”, lights it only for a valid unsaved change, and shows a temporary “✓ 已保存” feedback beside it;
- real shortcut key press/release events light the shortcut-page button without the default one-second Qt recording delay; reverting the shortcut disables it again;
- the categorized center can switch pages without losing the existing OCR window state.

The modern toolbar and overlay history drawer were also visually checked at the
default offscreen window size. The final arm64 0.2.0 candidate was rebuilt,
deep-signature verified, installed at `/Applications/FormulaOCR.app`, and
launched for manual macOS testing. No DMG or publication was made.
