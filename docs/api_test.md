# Stage H API verification

日期：2026-08-15
状态：PARTIAL

## 已通过

命令：

```bash
PYTHONPATH=FormulaOCR python3 FormulaOCR/tools/test_stage_h.py
PYTHONPYCACHEPREFIX=/private/tmp/formulaocr-pycache python3 -m py_compile \
  FormulaOCR/gui/main_window.py FormulaOCR/gui/api_settings.py \
  FormulaOCR/gui/macos_status_item.py FormulaOCR/api/*.py \
  FormulaOCR/gui/api_worker.py FormulaOCR/tools/test_stage_h.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=FormulaOCR \
  /private/tmp/formulaocr-stage-h-venv/bin/python FormulaOCR/tools/test_stage_h_gui.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=FormulaOCR \
  /private/tmp/formulaocr-stage-h-venv/bin/python FormulaOCR/tools/test_paste_shortcut.py
```

结果：

- Stage H provider/config checks: PASS
- 配置元数据不包含 API 密钥；Keychain 使用 fake store 的保存、读取和删除路径通过。
- Keychain 读取异常时仍可加载非敏感配置，内存中的密钥保持为空，不会导致主窗口崩溃。
- OpenAI-compatible `/models`、图片 data URL、Bearer header、LaTeX 响应解析和一次 5xx 重试通过。
- Mathpix `/v3/text`、`latex_styled`、`rm_spaces`、`rm_fonts`、`improve_mathpix=false` 和 confidence 解析通过。
- 远程 HTTP 被拒绝；本机 loopback HTTP 允许，HTTPS 允许。
- Python 静态编译通过，`git diff --check` 通过。
- 使用临时 Python 3.12 arm64 环境完成 GUI offscreen 冒烟测试：窗口可构造关闭；API 总开关、当前图片/本地结果依赖的按钮显示与启用状态通过。
- 设置对话框冒烟测试通过：初始保存按钮为禁用，产生改动后启用，保存成功后恢复禁用；配置元数据仍不含密钥。
- 模型获取/选择 GUI 测试通过：异步获取、去重、可编辑下拉框、旧模型保留、错误保留、Mathpix 隐藏模型控件和迟到响应隔离均通过。
- 主窗口 offscreen 构造/关闭回归通过，包含已有 API 配置但 Keychain 读取失败的路径。
- 主窗口 `Command+V` 回归通过：编辑框焦点下文本正常粘贴，图片进入 OCR。

## 未验证

- 已重新构建并安装包含模型获取和 `Command+V` 修复的 arm64 `FormulaOCR.app` 0.2.0 测试版，代码签名校验通过；模型获取界面的人工交互仍待用户验收。
- 尚未使用真实 OpenAI-compatible 凭据验证视觉模型响应。
- 尚未使用真实 Mathpix 凭据验证生产端点和 Keychain 权限提示。
- 未重新构建或发布 DMG；Stage H 仍为 `PARTIAL`。
