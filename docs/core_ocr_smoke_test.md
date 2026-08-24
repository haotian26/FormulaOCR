# FormulaOCR Stage B — core OCR smoke test

日期：2026-08-08

## 实际验证环境

隔离环境位于 `/private/tmp/formulaocr-stage-b`，只安装了正式 ONNX
闭包所需依赖：

```text
numpy==1.26.4
onnxruntime==1.28.0
Pillow==12.3.0
tokenizers==0.23.1
```

正式源码没有 PaddlePaddle、PaddleOCR、RapidDoc、云端 API 或模型下载器。

## 已运行命令

```bash
python3 main.py tests/samples/2026-08-08_02-32-28.png --json
```

结果：

```json
{
  "raw_latex": "\\mathrm{ThO_{2}+2H^{+}\\leftrightarrow Th(OH)_{2}^{2+}}",
  "confidence": null
}
```

模型加载成功，单图 elapsed 约 192 ms。

已运行 16 张真实样本的同一 engine smoke test：

- 16 张样本均返回非空 LaTeX。
- 首次识别后 backend session 被复用，第二次识别没有重新加载模型。
- 所有结果均有正的 elapsed_ms。
- 最长样本 elapsed 约 1,484 ms。

已验证安装入口：

```bash
python -m pip install --no-deps --no-build-isolation -e .
formulaocr tests/samples/2026-08-08_02-32-28.png --json
```

editable CLI 入口运行成功。

## 离线与失败行为

将 `--model` 指向不存在的本地路径时，程序以 exit code 1 退出并明确报告：

```text
FormulaOCR does not download models automatically.
```

因此正式 runtime 不会因缺失模型而联网下载。

## 当前边界

- 输出为 `OCRResult(raw_latex, confidence=None, elapsed_ms)`。
- confidence 尚未由 PP-FormulaNet_plus-M 的 token-ID 输出提供，因此保持 `None`。
- 尚未实现 MathML、Word 剪贴板、GUI、截图或全局快捷键；这些不属于 Stage B。
