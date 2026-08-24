# FormulaOCR offline consistency validation

日期：2026-08-15
状态：PARTIAL

## 已通过

```bash
cd FormulaOCR
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/formulaocr-stage-h-venv/bin/python tools/test_consistency.py
```

- 截图预览面板的贯穿边界细框会被预处理排除，真实公式内容保留。
- baseline、context8、context16 预处理函数仍保持可重复，用于开发诊断，生产流程不再自动调用候选重排。
- PP-FormulaNet_plus-L 的 16 张样本均能转换为 MathML；本次 `Nd` 案例不再产生整式 `\\phantom` 或外围方括号。
- Stage C–F、Stage H GUI、Command+V 和截图快捷键 offscreen 回归通过。

## 未验证

- 当前 offscreen 测试环境不加载 Qt WebEngine，因此只验证图像评分和预处理，
  没有伪造渲染结果冒充真实 GUI 验收。
- 真实 macOS Qt WebEngine 隐藏渲染器、用户提供的无竖线案例和真实绝对值
  公式需要在已安装的 0.2.0 App 中人工确认。
- 官方 Paddle L 与 RapidDoc ONNX 的逐 token 对照尚未完成；本机没有 Paddle
  运行时，不能把当前结果标记为 Paddle parity 已验证。
