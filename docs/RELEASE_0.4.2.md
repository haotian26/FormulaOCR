# FormulaOCR 0.4.2

2026-09-28 · Apple Silicon · macOS 14+

## 中文

这次更新主要让核对图片、整理历史和恢复编辑稿更方便。识别模型与预处理没有改动。

- 原图支持缩放、100% 实际大小和拖动，方便核对小电荷与上下标。
- 历史记录可以搜索，并将所选记录的当前编辑稿导出为 LaTeX 文本。
- 常规设置增加“关于”和手动检查更新，不会在后台下载或安装。
- 保存失败的草稿保留供重试；退出前可重试、取消或明确放弃。
- 模式切换保留手动编辑和撤销记录；迟到的排版与 API 配置测试结果不会覆盖新状态。
- 后台识别进程恢复后复用当前历史记录，不自动重发收费 API 请求。

下载下方 DMG，把 FormulaOCR 拖入 Applications。更新保留历史、设置和密钥。
App 使用 ad-hoc 签名，尚未经过 Apple 公证；首次启动若被系统阻止，请先核对下载来源，
再在“系统设置 → 隐私与安全性”允许打开。

小电荷、圆圈等符号仍可能误识别，需要人工核对。本次没有更换模型，也不宣称识别率提高。

## English

This update makes source-image inspection, history management and draft recovery
more useful. The OCR model and preprocessing are unchanged.

- Zoom, pan or view source images at actual size to inspect small symbols.
- Search history and export selected active-source drafts as LaTeX text.
- Check for updates manually in General → About, without background downloads.
- Retry failed draft saves; quitting offers Retry, Cancel or explicit Discard.
- Keep manual edits and Undo across mode changes; ignore stale formatting and API test responses.
- Recover the current image after a backend restart without repeating a billable API request.

Open the DMG and drag FormulaOCR into Applications. History, settings and keys
are preserved. The app is ad-hoc signed, not Apple-notarized. If macOS blocks
the first launch, verify the source before allowing it in Privacy & Security.

Small charges and circle symbols can still be misread. Check results against the
image; this release does not claim improved recognition accuracy.

## Verification

- Local checks: 94 Python, 47 frontend unit, 20 WebKit and 6 Rust tests passed.
- Production build and installed-app image zoom, history export, settings and preview checks passed.
- Packaged OCR, concurrent settings, MathML conversion and backend recovery passed.
- arm64 architecture and deep/strict code-signature verification passed.
- CI remains local because the publishing credential lacks workflow permission.
- Paid API recognition and Word paste fidelity were not revalidated for this release.

## Download integrity

File: `FormulaOCR-v0.4.2.dmg`

- Format: compressed UDBZ; contains FormulaOCR.app and an Applications shortcut.
- DMG: **737,804,470 bytes** (737.8 MB / 703.6 MiB).
- Source and staged app: **863,984 KiB** each (843.7 MiB).
- Archive: `Software Release/2026-09-28/FormulaOCR-v0.4.2.dmg`.
- Disk-image integrity, read-only mount and contained-app signature checks passed.
- The mounted app matches the installed, tested bundle byte-for-byte.

SHA256:

```text
950545024921ff1a7af451fddfac722ee0a8766b5b4c702484d16096f2e909cd
```

Bundled PP-FormulaNet_plus-L model SHA256 (unchanged):

```text
5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8
```
