# FormulaOCR Stage A — ONNX extraction notes

状态：`COMPLETE`（Stage A 调研和后端基准已完成）

## 调研结论

RapidAI/RapidDoc 已经提供可直接由 ONNX Runtime 执行的
`PP-FormulaNet_plus-M` 单文件模型。RapidDoc 的公式模块没有依赖
PaddlePaddle 做正式推理；它只保留了公式图像预处理、ONNX Runtime
推理、tokenizer 解码和少量 LaTeX 后处理。这符合 FormulaOCR 的最小
运行闭包目标。

参考实现：

- RapidDoc repository: <https://github.com/RapidAI/RapidDoc>
- Formula ONNX handler: `rapid_doc/model/formula/rapid_formula_self/`
- 模型配置：`rapid_doc/model/formula/rapid_formula_self/configs/default_models.yaml`
- RapidDoc 提供的 M 模型：
  `https://www.modelscope.cn/models/RapidAI/RapidDoc/resolve/v1.0.0/formula/PP-FormulaNet_plus-M/pp_formulanet_plus_m.onnx`

The source checkout inspected for this note was RapidDoc commit
`9704b2b63192e838627534611c369dc42141e5f8` (2026-08-04).

RapidDoc 的配置记录了模型 SHA256：

```text
71b6d389cf7b857e45252a4b98cfced1a3ffca7bf24d9497d02d052a41d9493b
```

## 最小运行闭包

```text
Pillow/OpenCV image decode
→ crop non-white margin
→ resize and center-pad to 384×384
→ UniMERNet normalization and 16-pixel padding
→ PP-FormulaNet_plus-M ONNX Runtime session
→ token IDs from the single output
→ tokenizer embedded in ONNX model metadata
→ LaTeX text
```

ONNX model metadata contains the tokenizer JSON under the `character` key,
so a separate vocabulary/model package is not required. The ONNX session has
one image input and one token-ID output; FormulaOCR does not need RapidDoc's
layout detection, PDF, table, OCR, web or server components.

## Paddle benchmark baseline

The existing Paddle model remains untouched at
`resources/models/PP-FormulaNet_plus-M/` and is used only as the Stage A
baseline. Its `inference.yml` supplies the same pre/post-process definition;
the benchmark tool uses Paddle static inference directly and does not add
PaddleOCR to the eventual application architecture.

## Implementation made for this stage

`tools/benchmark_backends.py` is a development-only benchmark tool. It keeps
Paddle and ONNX behind the same preprocessing and tokenizer decode, measures
load/warm-up/per-image time, records model size and prints backend exact-match
parity. It resolves project paths relative to the script and never embeds a
user-specific project path.

## License review

- RapidDoc source: Apache-2.0 (`LICENSE` in the repository).
- PP-FormulaNet_plus-M model README: Apache-2.0.
- PaddlePaddle/PaddleOCR references: Apache-2.0 project licenses.
- FormulaOCR's benchmark tool is an independent development tool; no RapidDoc
  source file is copied into the application package.

Any code or model retained in the formal runtime must be listed in
`THIRD_PARTY_NOTICES.md` before packaging.

## Current verification

- [x] RapidDoc ONNX implementation and model URL identified.
- [x] Paddle baseline model loads on this Apple Silicon Python 3.12 environment.
- [x] Paddle baseline run completed on all 16 local formula samples.
- [x] ONNX file SHA256 verified.
- [x] ONNX benchmark completed on the same 16 samples.
- [x] Final backend recommendation: `ONNX` (see `backend_benchmark.md`).
