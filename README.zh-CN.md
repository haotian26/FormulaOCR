<p align="center">
  <img src="resources/icons/formulaocr-modern.svg" width="88" alt="FormulaOCR 图标">
</p>

<h1 align="center">FormulaOCR</h1>

<p align="center">
  在 macOS 上把公式图片转换成可编辑的 LaTeX 或 Word 公式。
</p>

<p align="center">
  <a href="README.md">English</a> · 简体中文
</p>

FormulaOCR 是一个用来处理公式截图的小工具。你可以从论文、幻灯片、PDF
或网页中截取公式，检查识别结果，必要时直接修改 LaTeX，然后复制到 LaTeX
编辑器或 Word 中继续使用。

默认识别完全在本机进行。API 是单独的可选功能，只有主动点击“API 重识别”
时，当前图片才会发送到你配置的服务。

## 主要功能

- 打开图片、粘贴图片或直接截取屏幕区域。
- 使用 PP-FormulaNet_plus-L 在本机离线识别公式。
- 提供化学和数学两种排版模式。
- 一边编辑 LaTeX，一边查看公式预览。
- 复制 LaTeX，或复制成可继续编辑的 Word 公式。
- 在本机保存识别历史，并分别保留本地和 API 结果草稿。
- 支持菜单栏运行和可自定义的截图快捷键。
- 可在设置中切换完整的简体中文或英文界面。
- 在本地结果不理想时，可以手动调用 OpenAI-compatible 或 Mathpix API
  再识别一次。

## 安装

从 [Releases](https://github.com/haotian26/FormulaOCR/releases/latest)
下载最新 DMG，打开后把 FormulaOCR 拖入“应用程序”文件夹。

当前版本仅支持 Apple Silicon（`arm64`）。安装包经过 ad-hoc 签名，但尚未
进行 Apple 公证；第一次启动时，可能需要按住 Control 点击 App，再选择
“打开”。截图 OCR 还需要在系统设置中授予屏幕录制权限。

## 使用前需要知道的事

- OCR 不可能保证每次都完全正确。很小的电荷、度数符号、靠得很近的上下标，
  以及分辨率较低的图片，仍可能需要手动修正。
- 内置 L 模型体积较大，因此安装后的 App 也比较大。模型权重不放在 Git
  仓库中，只包含在正式安装包里。
- 化学模式只负责排版，例如把化学式显示为正体；它不会凭空补充元素、
  电荷或系数。
- 本地识别、编辑、预览、复制和历史记录都不需要联网。API 的数据边界见
  [PRIVACY.md](PRIVACY.md)。

## 从源码构建

需要 Apple Silicon Mac、Xcode Command Line Tools、Rust、Node.js 20+，
以及 Python 3.10–3.13。

```bash
npm ci
python3 -m venv /private/tmp/formulaocr-venv
/private/tmp/formulaocr-venv/bin/python -m pip install -e . PyInstaller pytest
/private/tmp/formulaocr-venv/bin/python tools/download_model.py
FORMULAOCR_PYTHON=/private/tmp/formulaocr-venv/bin/python tools/build_tauri_app.sh
```

`tools/download_model.py` 会下载固定版本的模型并检查 SHA256。FormulaOCR
运行时不会自行下载模型。

基本检查命令：

```bash
npm run build
PYTHONPATH=. /private/tmp/formulaocr-venv/bin/python -m pytest -q tests
PYTHONPATH=. /private/tmp/formulaocr-venv/bin/python tools/test_consistency.py
cargo check --manifest-path src-tauri/Cargo.toml
```

## 目录说明

- `src/`：React 界面
- `src-tauri/`：macOS 原生能力和 Sidecar 生命周期
- `sidecar/`：本地 JSON Lines 服务
- `ocr/`：图片预处理、ONNX 推理和结果排版
- `converter/`：Word 公式所需的 LaTeX 到 MathML 转换

## 贡献者

FormulaOCR 由 [Haotian](https://github.com/haotian26) 维护，开发过程中使用了
OpenAI Codex 协助。完整说明见 [CONTRIBUTORS.md](CONTRIBUTORS.md)。

欢迎提交 Issue 或 Pull Request。报告识别问题时，请尽量使用不含隐私的
小图片，并附上原始 LaTeX 输出。

## 许可证

本项目采用 MIT 许可证。第三方组件和模型来源见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
