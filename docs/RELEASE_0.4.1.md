# FormulaOCR 0.4.1

2026-09-08 · Apple Silicon · macOS 14+

## 中文

这个版本主要修复日常使用中的状态和界面问题，识别模型没有更换。

- 修复换图后旧结果覆盖新图片、撤销串到其他公式，以及历史编辑稿恢复错误。
- 改善设置保存、快捷键录制和 API 配置验证，保存失败时保留当前草稿。
- 图片先显示，再后台识别；支持原生 PNG/TIFF 剪贴板输入。
- 修复部分多行公式预览，调整中英文界面、设置表单和深色模式。
- 完善后台恢复和退出清理，补齐安装包中的第三方许可文本。

下载下方 DMG，打开后把 FormulaOCR 拖入 Applications。更新不会主动清空
历史记录、API 配置或 Keychain 密钥。

App 使用 ad-hoc 签名，尚未经过 Apple 公证。首次启动如被系统阻止，请先
核实下载来源，再到“系统设置 → 隐私与安全性”允许打开。

小电荷、圆圈等细小符号仍可能误识别，请核对结果。化学模式不推断缺失的
电荷。个别复杂公式的原始 LaTeX 仍可能无法渲染，原文会保留供编辑。

## English

This release fixes everyday editing, settings and interface issues. The OCR
model and preprocessing are unchanged.

- Fixed stale results after changing images, Undo crossing formula boundaries,
  and incorrect restoration of history drafts.
- Improved settings saves, shortcut recording and API profile validation.
- Show images before background recognition and support native PNG/TIFF paste.
- Fixed some multiline previews and refined bilingual layouts and dark mode.
- Improved background-window recovery and shutdown; bundled third-party notices.

Open the DMG and drag FormulaOCR into Applications. Updating does not intentionally
reset history, API profiles or Keychain credentials.

The app is ad-hoc signed, not Apple-notarized. If macOS blocks the first launch,
verify the download source before allowing it in System Settings → Privacy &
Security.

Small charges and circle symbols can still be misread. Chemistry mode does not
infer missing charges. Some complex model outputs remain unrenderable; the raw
LaTeX stays available for editing.

## Verification

- 39 Python tests, 26 frontend unit tests and 8 WebKit interaction tests passed.
- Production build, arm64 architecture and deep/strict code-signature checks passed.
- Packaged sidecar: real OCR, concurrent settings request, MathML conversion,
  image release and clean shutdown passed in temporary storage.
- The release app opened its main/settings windows and exited without leaving
  either its main process or sidecar running.
- DMG verification and read-only mount checks passed; the image contains the app
  and an Applications symlink, one ONNX model and one sidecar executable.
- Third-party notice inventory and its file hashes were checked.
- Real API requests and Word paste fidelity were not retested for this packaging
  run. GitHub Actions is not enabled; the checks above ran locally.

## Download integrity

File: `FormulaOCR-v0.4.1.dmg`

- Format: compressed UDBZ
- DMG: **740,749,731 bytes** (740.7 MB / 706.4 MiB)
- Source and staged app: **868,756 KiB** each (about 889.6 MB)
- Local archive: `Software Release/2026-09-08/FormulaOCR-v0.4.1.dmg`
- The local DMG and archive copy are byte-for-byte identical.

SHA256:

```text
d489c6fd8782eac22515a14a1e750abcf103cda036c5e72ac2155b92a6e9829e
```

The bundled model remains `PP-FormulaNet_plus-L`, SHA256:

```text
5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8
```
