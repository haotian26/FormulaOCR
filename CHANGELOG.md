# 更新日志 / Change Log

## [Unreleased]

### 中文

- 项目自身许可证由 Apache-2.0 改为 MIT，第三方组件和模型继续保留各自原有许可声明。
- 新增可持久化的简体中文/英文界面切换，覆盖主窗口、设置中心、历史、API、状态提示和菜单栏。

### English

- Changed the project license from Apache-2.0 to MIT while retaining the original licenses and notices for third-party components and the bundled model.
- Added a persistent Simplified Chinese/English interface switch across the main window, settings, history, API, status messages, and menu bar.

## [0.3.0] - 2026-08-24

### 中文

- 应用图标更新为透明、无边框的独立公式符号；菜单栏继续使用独立的单色 `function` 模板图标。
- 新增默认化学/可选数学识别模式；原始模型输出、模式排版和用户草稿分开保存，排版层禁止补删电荷或物种。
- 新增 25 张真实图片回放证据，记录模型、输入张量、token 与原始/显示 LaTeX；确认两张缺少 `F^-` 电荷的历史样本属于模型原始漏识别。
- 图片改用受限临时路径传入 Sidecar并先行显示；JSON Lines改为按请求 ID并发分发，OCR不再阻塞设置和历史。
- Sidecar改为无需冷启动解压的目录结构，L模型作为独立且带SHA256校验的App资源。
- 设置中心改为顶部五分类；API表单保持单一滚动区，普通分类使用紧凑内容宽度和逐页保存状态。
- 公式预览恢复为旧版验证过的本地 LaTeX→MathML 转换与系统 MathML 排版，移除显示不稳定的 MathJax；Word复制使用macOS原生剪贴板，Tauri启用限制性CSP。
- 预览请求使用防抖和请求编号隔离，历史/来源快速切换不会被迟到结果覆盖；设置表单的文本框与下拉框统一为相同高度和字体。
- 化学模式现在也会将已识别出的纯大写多元素物种（如 `HSO_4^-`、`HF^\circ`）排为正体；不增加、删除或推断任何电荷及字符。
- 修复化学格式化错误拆分带括号物种的问题；模型原本正确的 `\mathrm{Nd(SO_{4})_{2}^{-}}` 不再被破坏。
- 修复单字母 `\mathrm{F}` 在 MathML 预览中仍显示斜体的问题；普通数学变量 `F` 保持斜体。
- 撤销/重做现在严格隔离到当前图片和当前来源；换图、载入历史或首次生成 API 结果时不会再回到上一条公式或另一来源。
- 修复 CodeMirror 长期持有首次渲染回调，导致 API 来源编辑写入内置撤销栈的问题；撤销、重做和“恢复原文”现已在当前来源内实机验证。“恢复原文”本身也可撤销。
- 处理 macOS `Reopen` 生命周期事件；主窗口关闭并留在菜单栏后，再次点击 FormulaOCR 会恢复同一窗口和 Dock 状态，不再只生成无窗口的空图标。
- 撤销/重做启用态改为蓝色强调底配白色 SVG 图标；禁用态保持小号灰色透明，深浅色模式分别适配。
- 预处理新增自适应边缘安全区：仅当单行公式末端存在独立的小型上标/下标像素时，将内容限制为画布宽度的 99%；普通公式输入保持不变。本地 28 图回放中 26 图原始输出不变，两张 `HF°` 样本由错误的 `HF^-` 恢复为 `HF^\circ`。

- 完成功能等价修复：快捷键改为即时组合键录制并只在保存后注册，设置改为独立可缩放窗口。
- 恢复 API 配置的模型获取、连接测试、OpenAI-compatible/Mathpix 表单、活动配置切换和密钥保留逻辑。
- 恢复三档布局恢复模式和重置布局，修复历史/API 草稿、图片复用释放、请求过期结果和菜单栏退出路径。
- 新增 CodeMirror LaTeX 编辑器、来源独立撤销/重做、历史覆盖抽屉和 Sidecar `api.listModels`/`api.testProfile`/`history.updateDraft` 接口。
- 重新构建并安装 arm64 0.3.0 本机候选 App；当前仅用于测试，不制作 DMG、不推送、不发布。

- 开始迁移 Tauri 2 + React + TypeScript 现代 macOS 前端，产品名称仍为 FormulaOCR。
- 新增 JSON Lines Python Sidecar 骨架，保留现有 L ONNX、API、历史和转换核心。
- 新增现代主窗口骨架、覆盖式历史抽屉、结果区分栏、深浅色适配和独立迁移开发文档。
- 完成生产 Bundle ID (`com.formulaocr.FormulaOCRApp`) 的本机候选构建并替换 `/Applications/FormulaOCR.app`；清理范围仅限旧安装残留，未清理源码、模型或发布备份。
- 更新为现代 FormulaOCR 应用图标；0.3.0 仍是未发布测试候选。
- 第二版图标改为简约的积分符号＋扫描角标；补齐结果复制、撤销/重做、恢复原文、自动复制和历史全部删除操作。
- 接入 Tauri 全局快捷键插件；截图快捷键可在运行中的 macOS App 中注册/清空。图片/结果及 LaTeX/预览分隔条现在可拖动并记住比例；历史支持多选删除与来源切换。

### English

- Replaced the application icon with a transparent, borderless standalone formula mark while keeping the independent monochrome `function` menu-bar template.
- Added chemistry-default and optional math presentation modes while separating immutable model output, formatted output, and user drafts; formatting cannot invent or remove charges or species.
- Added a 25-image replay evidence set with model/input/token/raw/display hashes and confirmed that two missing `F^-` history cases are raw model misses.
- Moved image ingress to a scoped temporary path with immediate preview and concurrent request-ID Sidecar dispatch.
- Split the onedir Sidecar runtime from the SHA256-verified L model resource to avoid cold-start extraction.
- Rebuilt Settings around five top categories and per-page save state, with one scroll owner for API profiles.
- Restored the proven local LaTeX-to-MathML preview path and removed the unstable MathJax renderer; Word copy uses the native macOS pasteboard and Tauri retains a restrictive CSP.
- Added debouncing and request isolation to preview conversion so stale history/source results cannot overwrite the current formula; text fields and selects share one control height and font.
- Chemistry mode now sets already-recognized all-uppercase multi-element species such as `HSO_4^-` and `HF^\circ` upright without adding, deleting, or inferring any charge or character.
- Fixed chemistry formatting that incorrectly split parenthesized species; a correct model result such as `\mathrm{Nd(SO_{4})_{2}^{-}}` is now preserved.
- Fixed single-letter `\mathrm{F}` rendering italic in the MathML preview while preserving italic plain math variables.
- Scoped undo/redo to the current image and source; opening an image, restoring history, or creating the first API result can no longer undo into another formula or source.
- Fixed CodeMirror retaining its first-render callback, which routed API edits into the local undo stack. Undo, redo and reset-original are now live-verified within the active source, and reset-original is itself undoable.
- Handled the macOS `Reopen` lifecycle event so clicking FormulaOCR after a close-to-menu-bar restores the existing window and Dock state instead of showing a windowless icon.
- Made enabled undo/redo controls immediately visible with white SVG icons on a system-blue accent fill while retaining compact borderless gray disabled states in both appearances.
- Added an adaptive edge safety area: only single-line formulas with a detached small terminal script are limited to 99% canvas occupancy, while ordinary inputs remain unchanged. In the 28-image local replay, 26 raw outputs were identical and two `HF°` cases were corrected from `HF^-` to `HF^\circ`.

- Completed the functional-parity repair: immediate chord recording, save-only shortcut registration, and a separate resizable settings window.
- Restored model discovery, connection testing, OpenAI-compatible/Mathpix forms, active-profile switching, and secret-preserving Keychain saves.
- Restored the three layout-restore modes and reset action; fixed history/API drafts, image reuse/release, stale requests, and menu-bar quit handling.
- Added the CodeMirror LaTeX editor, source-specific undo/redo, overlay history drawer, and Sidecar `api.listModels`, `api.testProfile`, and `history.updateDraft` endpoints.
- Rebuilt and installed an arm64 0.3.0 local candidate; DMG creation, push and publication remain deferred.

- Started the Tauri 2 + React + TypeScript macOS front-end migration; the product remains FormulaOCR.
- Added a JSON Lines Python sidecar foundation while retaining the L ONNX, API, history and conversion core.
- Added the modern main-window skeleton, overlay history drawer, result split panes and light/dark tokens.
- Built and installed the production-bundle 0.3.0 candidate at `/Applications/FormulaOCR.app`; cleanup was limited to old installation residue, and source, models and release backups were retained.
- Replaced the app icon with a modern FormulaOCR mark; 0.3.0 remains unpublished.
- Replaced the first icon concept with a minimal integral-and-scan-corner mark and restored result copy, undo/redo, reset-original, automatic copy and delete-all history actions.
- Added native Tauri global-shortcut registration, draggable image/result and LaTeX/preview splitters with persisted ratios, multi-select history deletion and local/API source switching.

## [0.2.0] - 2026-08-15

### 中文

#### 变更
- 离线默认模型切换为 PP-FormulaNet_plus-L ONNX；仅内置一套本地模型，模型 SHA256 为 `5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8`。
- 恢复单次本地识别：移除同一 M 模型的自动多候选推理、MathML 评分和外层定界符自动重排。
- 预处理仅忽略贯穿截图边界的细线框，避免把应用预览面板边框识别成公式括号；真实公式中的绝对值和括号不做删除。
- 主窗口改为现代 macOS 布局：左侧导航栏、悬浮历史抽屉、结果区标题操作和固定状态栏；历史抽屉不再压缩公式预览。
- 新增三档布局恢复设置，保存窗口尺寸、图片/结果比例、LaTeX/预览比例和历史抽屉宽度，并提供立即重置布局。

#### 修复
- 识别结果含 `\\phantom` 或无法转换为 MathML 时，不再显示空白预览或自动复制空结果；原始 LaTeX 保留在编辑框中并显示明确错误。
- 修复同时上下标的模型输出层级：规范化空脚本占位符和字体组内嵌套脚本，原始 LaTeX 仍可恢复。
- 修复从 Dock 退出后重新出现空 Dock 图标的问题。
- 设置页保存按钮始终显示“保存”，未修改时灰色、修改后亮起，成功后在按钮旁短暂显示“✓ 已保存”；关闭时确认放弃会销毁未保存草稿。

#### 新增
- 新增本机识别历史，默认保留 200 条；支持内置/API 结果合并、编辑稿恢复、单条/批量/全部删除和上限设置。
- 设置窗口新增“界面与布局”入口；统一主窗口、历史抽屉和设置提示的 macOS 风格样式。
- 导航栏进一步收窄为透明图标条；设置按钮现在打开完整设置菜单，不再只显示窗口行为一项。
- 移除常驻左侧导航栏，将历史移至顶部工具栏并重做为覆盖式抽屉入口。
- 新增带分类侧栏的设置中心；常规、布局、快捷键、API 和历史记录分别保存。
- API 重识别拆分为执行按钮和配置胶囊；识别结果操作统一到单行工具栏，并改用内部线性图标。

#### 依据
- L 模型来自 RapidDoc ModelScope `v1.0.0` 预转换文件；官方 Paddle L 运行时未在本机安装，Paddle↔ONNX 逐 token 对照标记为 NOT VERIFIED。

### English

#### Changed
- Switched the offline default to PP-FormulaNet_plus-L ONNX; the app bundles one local model only. SHA256: `5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8`.
- Restored single-pass local recognition by removing automatic same-model candidate inference, MathML scoring, and outer-delimiter reranking.
- Preprocessing now ignores only thin lines spanning the screenshot boundary, preventing preview-panel borders from becoming formula brackets; genuine absolute-value and bracket glyphs are not deleted.
- Reworked the main window with a modern macOS shell: a compact navigation rail, floating history drawer, result-header actions, and a fixed status footer. History no longer shrinks the formula preview.
- Added three layout-restore modes and persistence for window geometry, splitters, and history-drawer width, with an explicit reset action.

#### Fixed
- Results containing `\\phantom` or failing MathML conversion no longer show a blank preview or trigger automatic Word copy; the original LaTeX remains editable with a clear error message.
- Fixed malformed simultaneous-script output by normalizing empty script placeholders and nested font-group scripts while preserving the raw LaTeX.
- Fixed the empty Dock icon that could reappear after choosing Quit from the Dock.
- Settings pages keep a consistent “Save” button that becomes enabled only for valid changes, show a temporary “✓ Saved” feedback beside it, and discard confirmation really drops drafts.

#### Added
- Added local recognition history with a default limit of 200 records, merged local/API sources, draft restoration, and single/batch/all deletion.
- Added the “Interface & Layout” settings entry and unified macOS-style surfaces for the main window, history drawer, and settings prompts.
- Tightened the navigation rail into a transparent icon strip; the settings button now opens the complete settings menu instead of only window behavior.
- Removed the permanent left rail, moved History into the top toolbar, and kept the history list as an overlay drawer.
- Added a categorized settings center with independent saves for General, Layout, Shortcuts, API, and History.
- Split API execution from profile selection and consolidated result actions into one toolbar with app-owned line icons.

#### Evidence
- The L model is the RapidDoc ModelScope `v1.0.0` converted artifact. Official Paddle L runtime is not installed locally, so Paddle↔ONNX token-level parity remains NOT VERIFIED.

## [0.2.0] - 2026-08-14

### 中文

#### 新增
- 新增可选的用户主动 API 重识别：默认仍使用本地 ONNX，只有点击 API 按钮才上传当前图片。
- 支持多个 OpenAI-compatible 与 Mathpix 配置、模型列表获取、独立 API 线程和 API/内置结果切换。
- 设置中提供异步“获取模型”按钮和可编辑模型下拉框；保留手动模型 ID，获取失败不会清空原配置。
- 本地 OCR 增加离线视觉一致性校验：仅在首个结果结构可疑时，用同一 ONNX 模型的两种上下文预处理生成候选并自动重排，不增加模型或网络请求。

#### 修复
- 修复主界面 `Command+V` 在 LaTeX 编辑框有焦点时无法粘贴图片的问题；文本剪贴仍保持原有行为。
- 增加外层 LaTeX 定界符的离线视觉校验候选；只有原图证据支持去除时才移除模型误加的 `\\left...\\right` / `\\boxed` 包装，真实绝对值和括号保持不变。
- 将“复制 Word”和“复制 LaTeX”移动到结果区下方，缩短与结果内容的距离。
- API 密钥使用 macOS Keychain 保存；本地与 API 结果分别保留编辑稿、撤销历史和原始结果恢复。

#### 说明
- 当前版本不启用自动回退或置信度阈值；本地 ONNX 仍没有可校准 confidence。
- 视觉一致性分数只用于本地候选排序，不代表数学识别正确率；所有候选都不理想时保留首个结果。
- 真实供应商凭据测试：NOT VERIFIED。

### English

#### Added
- Optional user-triggered remote re-recognition; local ONNX remains the default and images are uploaded only after clicking the API button.
- Multiple OpenAI-compatible and Mathpix profiles, model discovery, a dedicated API worker, and local/API result switching.
- The settings dialog provides asynchronous model discovery with an editable model dropdown; manual IDs are preserved when discovery fails.
- Offline visual consistency checks now rerank up to two same-model preprocessing candidates only when the initial structure is suspicious; no model or network request is added.

#### Fixed
- Fixed image paste via `Command+V` when the LaTeX editor has focus while preserving ordinary text paste.
- Added an offline visual repair candidate for accidental outer LaTeX delimiters or `\\boxed` wrappers; genuine absolute-value and bracket glyphs are retained when supported by the source image.
- Moved the “Copy Word” and “Copy LaTeX” buttons below the result area for easier access.
- API secrets are stored in macOS Keychain; local and remote drafts retain separate undo histories and original-result restore.

#### Notes
- Automatic fallback and confidence thresholds remain deferred because the local ONNX backend has no calibrated confidence.
- Visual consistency is a local candidate-ranking signal, not a correctness confidence; the first result is retained when no candidate is clearly better.
- Live provider credential testing: NOT VERIFIED.

## [0.1.1] - 2026-08-08

### 中文

#### 修复
- 修复普通字母和化学式 OCR 输出中的 token 分隔空格、脚本空格和多余换行，保持有效 LaTeX。
- 对化学反应式使用直立 `\\mathrm{}` 表示，避免普通字母被错误渲染为数学斜体。
- 发布格式改为仅提供包含可运行 App 的 DMG。

### English

#### Fixed
- Removed token-separator spaces, spaced scripts, and stray line breaks from ordinary-letter and chemistry OCR output while preserving valid LaTeX.
- Rendered unambiguous chemical reaction terms upright with `\\mathrm{}` instead of accidental math italics.
- Personal software releases now provide only a runnable DMG.

## [0.1.0] - 2026-08-08

### 中文

#### 新增
- 提供 Apple Silicon macOS 离线公式 OCR、LaTeX 编辑、MathML 预览和 Word/LaTeX 复制。
- 支持打开图片、粘贴图片、原生 macOS 截图选择器和可自定义全局截图快捷键。
- 提供菜单栏状态项、单实例保护、关闭窗口后保留菜单栏运行，以及可拖动的结果分栏。
- 内置 PP-FormulaNet_plus-M ONNX 模型资源和自定义 FormulaOCR 应用图标。

#### 修复
- 深色截图自动进行前景反色，避免白色普通文字被误识别为重复分式。
- macOS 26 菜单栏注册使用独立 bundle identifier，FormulaOCR 会出现在系统设置的菜单栏列表中。

#### 兼容性
- 当前发布目标为 Apple Silicon macOS；模型权重仅在确认允许再分发时随发布 DMG 提供。
- 无破坏性变更。

### English

#### Added
- Offline formula OCR for Apple Silicon macOS with editable LaTeX, MathML preview, and Word/LaTeX copying.
- Image open, image paste, the native macOS screenshot selector, and a customizable global screenshot shortcut.
- A menu-bar status item, single-instance protection, close-to-menu-bar operation, and draggable result splitters.
- The PP-FormulaNet_plus-M ONNX model resource and a custom FormulaOCR application icon.

#### Fixed
- Dark screenshots are polarity-normalized so white ordinary text is not decoded as repeated fractions.
- macOS 26 menu-bar registration uses a dedicated bundle identifier, so FormulaOCR appears in the system menu-bar settings list.

#### Compatibility
- The current release targets Apple Silicon macOS; model weights are included in the release DMG only when redistribution is confirmed.
- No breaking changes.
