# FormulaOCR Project State

CURRENT_STAGE: I
STATUS: COMPLETE
STOP_GATE_REACHED: true
RECOMMENDED_BACKEND: ONNX
CURRENT_OFFLINE_MODEL: PP-FormulaNet_plus-L ONNX
NEXT_STAGE: PUBLIC_RELEASE

STAGE_I_TAURI_MIGRATION:
- FormulaOCR 0.3.0 migration has started with a Tauri 2 + React + TypeScript
  shell and a JSON Lines Python sidecar. The product name remains FormulaOCR.
- Development builds use an isolated data root; the production build uses
  `com.formulaocr.FormulaOCRApp` and the `FormulaOCR API` Keychain service.
- The first migration slice is in `src/`, `src-tauri/`, `sidecar/` and
  `docs/TAURI_MIGRATION.md`. The React surface is a functional layout skeleton;
  native feature parity and production replacement remain pending.
- The production 0.3.0 candidate was built and installed at
  `/Applications/FormulaOCR.app` after clearing only the old installation's
  Application Support, Preferences, Caches and crash-report residue. Existing
  0.2.0 release artifacts and source/model files remain available for rollback.
- The FormulaOCR app icon now uses a transparent, borderless standalone formula
  mark with a vector source in `resources/icons/`; the monochrome AppKit menu-bar
  symbol remains independent. The installed app remains a 0.3.0 candidate
  pending full feature-parity acceptance.
- The L-model preprocessing now applies a 1% inner safety margin only when
  source pixels show a detached small terminal script on a single-line formula.
  A 28-image replay kept 26 raw outputs identical and corrected both retained
  `HF` degree-sign samples without changing the other regression images.

NOTES:
- Stage A completed on 2026-08-08 using 16 local PNG formula samples.
- RapidDoc's PP-FormulaNet_plus-M ONNX implementation was inspected at commit
  `9704b2b63192e838627534611c369dc42141e5f8`.
- The verified ONNX model is stored separately at
  `resources/models/PP-FormulaNet_plus-M-ONNX/pp_formulanet_plus_m.onnx`.
- ONNX SHA256:
  `71b6d389cf7b857e45252a4b98cfced1a3ffca7bf24d9497d02d052a41d9493b`.
- Paddle and ONNX decoded LaTeX matched 16/16. Semantic accuracy against an
  authoritative ground-truth file is `NOT VERIFIED` because no annotations were
  supplied with the current samples.
- ONNX was faster and had a smaller packaging closure; Stage B rechecked the
  peak RSS and confirmed it remains higher than Paddle.
- Stage A artifacts: `docs/onnx_extraction_notes.md`,
  `docs/backend_benchmark.md`, `tools/benchmark_backends.py`,
  `THIRD_PARTY_NOTICES.md`.
- At the end of Stage A, no GUI, MathML, clipboard, screenshot, hotkey, or DMG
  work had been performed.
- Stage B completed on 2026-08-08: ONNX-only project skeleton, resource path
  handling, `FormulaOCRBackend`, `ONNXFormulaBackend`, `FormulaOCREngine`,
  `OCRResult`, packaging metadata and offline CLI are implemented.
- Stage B smoke test passed on all 16 local samples; the model session loaded
  once and was reused, and every sample returned non-empty LaTeX.
- Formal dependencies are ONNX Runtime, NumPy, Pillow and tokenizers only;
  PaddlePaddle remains benchmark-only.
- Stage B evidence: `docs/core_ocr_smoke_test.md`.
- Stage C completed on 2026-08-08: `latex2mathml` conversion and a PySide6
  clipboard manager are implemented. The manager exposes exact LaTeX copy and
  Word-oriented HTML/MathML MIME data with exact LaTeX plain-text fallback.
- Stage C automated checks passed for superscripts, fractions, Greek letters,
  arrows, thermodynamic symbols, cases and braces.
- Word macOS verification passed in a new unsaved document: the installed Word
  accepted the MathML payload as an editable equation object (`公式`, Cambria
  Math, equation tab). Evidence: `docs/clipboard_word_test.md`.
- Stage C did not implement screenshots, global hotkeys or the PySide6 GUI;
  those items were deferred to Stage D/E.
- Stage D completed on 2026-08-08: minimal PySide6 GUI, image picker, preview,
  OCR worker thread, LaTeX result display, Word/LaTeX copy buttons and
  persistent automatic-Word-copy setting are implemented. Automatic copy is
  OFF by default.
- Stage D offscreen checks passed: single-instance lock, OCR outside the GUI
  thread, automatic-copy OFF/ON behavior, settings write and manual LaTeX
  copy. Evidence: `docs/gui_smoke_test.md`.
- Real macOS GUI verification passed with a local sample: opened the image,
  returned non-empty OCR LaTeX in the GUI, copied Word format, and Word
  accepted it as an editable equation object. Screenshot/global-hotkey work is
  not part of Stage D.
- Stage E implementation is present: macOS global hotkey bridge, multi-display
  Retina-aware capture/crop, Esc-cancellable selection overlay, Screen
  Recording permission checks, OCR worker integration, temporary capture
  cleanup, menu-bar tray behavior and a user-editable QKeySequence hotkey
  setting with QSettings persistence.
- Stage E offscreen checks passed for the hotkey bridge, multi-display Retina
  crop, screenshot selection to OCR worker, Esc cancellation and custom hotkey
  save/roundtrip. Evidence:
  `docs/screen_capture_hotkey_test.md`.
- Real macOS GUI verification passed for recording and saving a custom
  `Control+Option+Command+P` hotkey, then restoring the default. The GUI
  displayed the saved binding after applying it.
- Real macOS permission-path verification passed: the GUI detected missing
  Screen Recording permission and displayed the required System Settings
  instruction. After permission was granted to the Python.app host, a direct
  authorized Python.app process reported `CGPreflightScreenCaptureAccess =
  true`, opened the real selection overlay, captured one display at
  `1512x982`, and produced a real Retina-aware `840x520` crop from a
  `420x260` logical selection. Stage E is complete; the next gate is Stage F.
- Stage F completed on 2026-08-08: conservative syntax-only LaTeX formatting is
  implemented in `ocr/postprocess.py`. It braces unbraced subscripts and
  charge superscripts, canonicalizes reaction arrows and harmless command
  spacing, while preserving `OCRResult.raw_latex` and protected text payloads.
  No balancing, coefficient, valence, species or reaction-direction edits are
  performed. Evidence: `docs/chemical_postprocess_test.md`.
- Stage C, D and E regression suites passed after Stage F integration, and the
  Stage F suite passed for idempotence, raw-result preservation and CLI audit
  fields. Stage F is complete; the next gate is Stage G.
- Post-stage usability refinements were verified without advancing the gate:
  the main window now accepts clipboard-image paste, screenshot-hotkey editing
  lives under the `设置` secondary menu, and Esc clears/saves an empty global
  shortcut. Stage F remains complete; Stage G follows as the current release
  stage.
- Screenshot-trigger robustness was then verified: repeated key-down events are
  ignored, a second overlay cannot be created while one is active, and the
  main window is hidden during capture and restored after selection or cancel.
- The production macOS screenshot path now uses the native interactive
  `/usr/sbin/screencapture -i -s -c` selector and reads its clipboard image;
  the custom overlay remains only as a test/non-macOS fallback. This keeps the
  Stage F gate unchanged.
- The result area now uses a horizontal splitter with editable LaTeX on the
  left and an offline Qt WebEngine MathML preview on the right. Preview updates
  are debounced by 100 ms while typing; no network or stage advancement is
  involved.
- The result UI now has a draggable vertical splitter with handles above and
  below the result panes, plus the existing draggable horizontal LaTeX/preview
  splitter. The LaTeX heading is concise, aligned formulas render row-by-row,
  and incomplete versus unsupported preview input receives a distinct
  explanatory message. Stage F remains complete; Stage G is now partial pending
  the second-Mac migration gate.
- Stage G local release build is partial: an arm64 ad-hoc-signed
  `FormulaOCR.app` and a UDZO `FormulaOCR.dmg` were built with PyInstaller,
  including the ONNX model and `latex2mathml` symbol data. The packaged app
  launched offline, recognized a sample, copied Word MathML and produced an
  editable Word equation. The native screenshot selector was invoked, but the
  current Computer Use bridge cannot complete a drag while that system
  selector has no accessibility window. The close-to-menu-bar behavior is now
  configurable under 设置 → 窗口行为: by default, closing the main window
  hides its Dock icon while the menu-bar item keeps the app running; reopening
  restores the Dock icon and window. The macOS bundle now uses a native
  AppKit status item and embeds the FormulaOCR app icon; Qt's tray remains the
  test/non-macOS fallback. A second Apple Silicon Mac migration test remains
  required before STOP G. The standalone bundle now uses the dedicated
  identifier `com.formulaocr.FormulaOCRApp`; this keeps macOS 26 Control Center
  from grouping the status item under Codex. System Settings lists FormulaOCR
  under “允许在菜单栏显示” and the local ledger reports it allowed.
- The ONNX preprocessing now detects a dark screenshot background and inverts
  it before inference. This prevents white UI text from being decoded as
  repeated fractions; the FormulaOCR wordmark regression now returns
  `\\mathsf { F o r m u l a O C R }`.
- Stage G second-Apple-Silicon migration was completed and confirmed by the
  user; this is recorded as USER VERIFIED rather than independently rerun in
  this invocation. Stage H is now active.
- Stage H adds optional, user-triggered API re-recognition. Local ONNX OCR
  remains the default and remains offline; automatic API fallback and quality
  thresholds are deferred because local confidence is still `None`.
- Stage H provider/config tests, static compilation and offscreen GUI smoke
  tests pass; evidence is in `docs/api_test.md`. A local arm64 `FormulaOCR.app`
  was rebuilt and installed as version `0.2.0` for user testing; it is not a
  DMG or published release. Real-provider credentials and frozen-app Keychain
  behavior remain `NOT VERIFIED`, so Stage H remains `PARTIAL`.
- The API settings dialog now has an asynchronous “获取模型” action and an
  editable model dropdown for OpenAI-compatible profiles. Manual model IDs are
  preserved when discovery fails or the endpoint returns no list; Mathpix hides
  the model controls. GUI regression evidence covers duplicate removal, stale
  response isolation and error preservation.
- The main-window `Command+V` route now sends image clipboard data to OCR even
  when a LaTeX editor has focus, while preserving ordinary text paste. The
  rebuilt 0.2.0 arm64 test App is installed locally; no DMG or publication was
  performed.
- Offline local candidate validation is now implemented as a Stage H
  refinement: the first ONNX result is compared with a local MathML rendering
  using tolerant image structure features; only low-scoring results trigger up
  to two deterministic context-crop candidates from the same loaded model.
- OCR results retain the selected variant, initial raw output, candidate count,
  visual consistency score and validation status. The visual score is not a
  confidence value and never triggers API or other network activity.
- Core consistency and preprocessing tests pass, and Stage C-F/H offscreen
  regressions pass. A rebuilt arm64 `FormulaOCR.app` 0.2.0 test candidate is
  installed in `/Applications/FormulaOCR.app`; no DMG or publication was made.
  Real macOS WebEngine candidate rendering and threshold calibration against a
  manually annotated set remain `NOT VERIFIED`; Stage H remains `PARTIAL`.
- A user-provided regression image showed the ONNX model adding an outer paired
  delimiter to formulas that had no such strokes. The app now evaluates generic
  outer-wrapper candidates (`\\left...\\right` and `\\boxed`) against the source
  image and only selects a stripped candidate when visual consistency improves;
  this does not unconditionally remove absolute-value or bracket notation.
- The focused-editor image `Command+V` path now has a real key regression test,
  while ordinary text paste remains native. The repaired 0.2.0 arm64 app was
  rebuilt, code-signature verified, installed in `/Applications/FormulaOCR.app`,
  and opened for user testing; no DMG or publication was made.
- The offline default has now been moved to PP-FormulaNet_plus-L ONNX for the
  0.2.0 test candidate. The verified model SHA256 is
  `5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8`; its
  fixed input is `768x768` and ordinary samples complete in roughly 0.6–2.3 s
  on the current Apple Silicon Mac. The M ONNX remains development-only.
- The GUI local path is single-pass again. Automatic same-model candidates,
  MathML visual reranking and outer-wrapper stripping are no longer part of
  the recognition flow. Results containing a whole-expression `\\phantom` or
  failing MathML conversion remain editable but are not auto-copied to Word.
- Preprocessing ignores a thin frame only when it touches both opposing image
  boundaries. This prevents a screenshot of the FormulaOCR preview panel from
  turning its border into `\\left[...\\right]`; actual formula delimiters are
  not deleted. The recent `Nd` chemistry case becomes a single expression after
  the frame is removed, although its state glyph still needs semantic review.
- The L file is the RapidDoc ModelScope `v1.0.0` pre-converted artifact. The
  official Paddle L runtime is not installed on this Mac, so Paddle↔ONNX
  token-level parity remains `NOT VERIFIED`; the installed app is a local test
  candidate only and no DMG or publication was made.
- The 0.2.0 candidate now applies balanced-group LaTeX script normalization for
  malformed simultaneous subscript/superscript output. Raw model/API LaTeX is
  preserved; the normalized display form is shared by MathML preview and Word
  copy. No chemistry symbols or case are inferred by this change.
- Dock Quit and `aboutToQuit` cleanup no longer restore Regular activation
  policy, preventing a transient empty Dock icon. Window close-to-menu-bar
  behavior continues to use Accessory policy and remains configurable.
- A local SQLite-backed recognition history is implemented with copied PNGs,
  default limit 200, merged local/latest-API branches, draft persistence, and
  single/batch/all deletion. History is local-only and loading a record does
  not invoke OCR or API. Store and offscreen GUI smoke evidence is recorded in
  `docs/history_test.md`; manual frozen-App Dock/history verification remains
pending, so Stage H is still `PARTIAL`.
- The main window now uses a modern macOS shell with a narrow navigation rail
  and an overlay history drawer that does not consume result width. The footer
  is fixed outside the image/result splitter, and copy actions sit beside the
  formula preview.
- Layout persistence stores geometry, both splitter states, drawer width and
  the selected restore mode. The default mode restores sizes while starting
  with history closed; full restore and optimized-default modes are available,
  together with an immediate reset action.
- `tools/test_layout_ui.py` and the existing Stage D, paste, history and Stage H
  GUI checks pass offscreen. Frozen-App visual verification of the redesigned
  shell remains pending; Stage H remains `PARTIAL`.
- The modern shell was rebuilt after adding theme/fallback navigation icons and
  installed as the 0.2.0 arm64 test candidate at `/Applications/FormulaOCR.app`.
  The bundle passes deep code-signature verification; no DMG or publication was
  made. Frozen-App manual visual verification remains a user-test step.
- The navigation rail was tightened to a transparent 44 px icon strip so it no
  longer appears as a full-height bordered panel. Its settings button now opens
  the complete five-section settings menu (API, shortcut, window behavior,
  layout, and history) instead of only the Dock-close option.
- The permanent rail has now been removed from the main layout entirely. History
  is a compact top-toolbar action before Open Image, while Settings opens a
  resizable categorized center with independent page saves. API execution and
  profile selection are separate controls, and result actions use one toolbar
  with app-owned line icons. New offscreen evidence is in
  `tools/test_settings_center.py` and `docs/settings_center_test.md`. The final
  arm64 0.2.0 bundle was rebuilt, deep-signature verified, installed at
  `/Applications/FormulaOCR.app`, and launched; no DMG or publication was made.
- Settings pages now keep a fixed “保存” label, use disabled/enabled visual
  state for clean/dirty values, and show temporary “✓ 已保存” feedback beside
  the button. Dirty state compares normalized page snapshots, so reverting a
  value turns the button off again. Shortcut recording is limited to one chord
  and completes immediately after the main key is released; invalid or failed
  registrations retain the draft. The corrected arm64 0.2.0 bundle was rebuilt,
  signed, installed and launched on 2026-08-15; no DMG, push or publication was
  made.
- A release DMG was generated and published on 2026-08-16 after fixing the
  packager to preserve framework symlinks; this keeps the 1.38 GB App from
  expanding to a multi-GB staging image. The published
  `FormulaOCR-v0.2.0.dmg` is about 875 MB, and GitHub Release `2026-08-16`
  contains only this DMG (SHA256
  `73966583f0bac7eab7a742fed465a510379a043790dc3207fa3bf4f254faec1f`).
  Stage H remains `PARTIAL` because the documented real-provider and frozen-App
  manual checks are still not claimed as verified.

- The 0.3.0 parity repair now uses `src/MainApp.tsx` as the Tauri/React entry.
  Settings are a separate resizable window, shortcut recording is immediate,
  API profiles expose model discovery and connection testing, and the Sidecar
  supports history draft updates, API history merging and image release.
- The candidate uses a single-pass image-id OCR flow with stale-request guards,
  CodeMirror editing, source-specific undo/redo, overlay history management and
  tray settings/screenshot entries. The latest Sidecar was rebuilt from source.
- A local 0.3.0 arm64 App is installed at `/Applications/FormulaOCR.app`; it is
  approximately 698 MB, contains one 680 MB Sidecar/model resource, and passes
  deep ad-hoc signature verification. DMG creation and publication remain
  deferred.
- Manual frozen-App verification of shortcut recording, real API credentials,
  native Word clipboard behavior and Dock close/quit semantics remains pending;
  these items are not marked as passed by this implementation.
- The 0.3.0 product-closure pass now separates immutable OCR output from
  chemistry/math presentation and user drafts. A 25-image replay captured
  image/model/tensor hashes and token IDs; two missing-fluoride-charge cases
  are confirmed raw L-model misses, so no formatter patch invents the charge.
- The bridge now accepts only scoped staged PNG paths, routes responses by
  request ID, and permits settings/history/API tasks while OCR runs. The
  Sidecar is packaged onedir and the L model is a separate SHA256-verified App
  resource, eliminating the old 680 MB one-file startup extraction.
- Settings uses top categories, preview uses the local LaTeX-to-MathML converter, Word copy uses
  the native pasteboard, and Tauri has an explicit CSP. Current status remains
  `PARTIAL` until the rebuilt frozen App and real configured API are manually
  verified; no DMG, push, repository publication or public release is allowed.
- The installed 0.3.0 candidate now renders LaTeX through the same local
  LaTeX-to-MathML conversion used by the earlier interface, with debounced and
  request-isolated updates. The MathJax experiment was removed after it showed
  literal script markers and inconsistent clipping in the frozen App. API text inputs
  and selects now use one 40 px control specification. Stage F regression also
  covers upright `HSO_4^-`, `H^+`, and `HF^\circ` formatting while preserving
  all recognized characters and charges. React and Rust currently compile but
  still have no real automated test cases, so product status remains `PARTIAL`.
- History evidence showed that the L model's raw acid-reaction output was
  complete while chemistry formatting broke `\mathrm{Nd(SO_{4})_{2}^{-}}`.
  The group parser now lifts scripts only from a simple base followed entirely
  by balanced scripts; compound parenthesized species remain intact.
- The MathML converter now works around an upstream single-glyph `\mathrm`
  conversion defect without modifying editable LaTeX. Undo/redo stacks are
  reset on new-image and history-session boundaries, and the first API result
  starts a separate source history instead of inheriting the local formula.
- The installed 0.3.0 candidate now handles Tauri's macOS `RunEvent::Reopen`.
  A frozen-App close-to-menu-bar/reopen test restored the same in-memory window
  and edit state. CodeMirror now dispatches through the latest source callback;
  live API-source edit/undo/redo and undoable reset-original checks passed.
- A new terminal-charge replay confirmed that the final minus remained present
  in the source image, foreground box and model tensor, but was omitted by the
  L model's decoded token sequence. A global context-margin change was rejected
  after changing many unrelated regression outputs; no charge is inferred by
  the formatter.
