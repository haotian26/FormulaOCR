# FormulaOCR Stage A — backend benchmark

日期：2026-08-08

## 测试范围

- 模型：`PP-FormulaNet_plus-M`
- 平台：当前 Apple Silicon macOS，Python 3.12 arm64
- 输入：`tests/samples/` 中现有 16 张 PNG 公式图片
- 内容覆盖：热力学、化学反应、可逆箭头、上下标、根式、分式、积分、偏导、矩阵、多行 `aligned/array`
- 推理：CPU，单图 batch，首次推理单独记录为 warm-up
- 预处理和 tokenizer 解码：两个 backend 共用 `tools/benchmark_backends.py`

实际运行命令：

```bash
/private/tmp/formulaocr-stage-a/venv/bin/python \
  tools/benchmark_backends.py --skip-onnx \
  --output /private/tmp/formulaocr-stage-a/paddle.json

/private/tmp/formulaocr-stage-a/venv/bin/python \
  tools/benchmark_backends.py --skip-paddle \
  --output /private/tmp/formulaocr-stage-a/onnx-project.json
```

ONNX 模型在运行前已复制到：

```text
resources/models/PP-FormulaNet_plus-M-ONNX/pp_formulanet_plus_m.onnx
```

并验证 SHA256：

```text
71b6d389cf7b857e45252a4b98cfced1a3ffca7bf24d9497d02d052a41d9493b
```

## 结果

| 指标 | Paddle baseline | ONNX Runtime | 观察 |
|---|---:|---:|---|
| 模型目录大小 | 595 MB | 566 MB | ONNX 小约 29 MB |
| 推理模型文件 | `inference.pdiparams` 617,064,962 B | 593,915,961 B | ONNX 小约 3.8% |
| 加载时间 | 2,143.7 ms | 441.0 ms | ONNX 更快 |
| warm-up | 663.4 ms | 179.4 ms | ONNX 更快 |
| 16 图平均热推理 | 705.5 ms | 332.3 ms | ONNX 约 2.1× 更快 |
| 16 图中位数 | 615.9 ms | 279.5 ms | ONNX 更快 |
| 峰值 RSS | 约 1,416 MB | 约 1,946 MB | ONNX 约高 530 MB |
| 解码后 LaTeX 完全一致 | — | 16/16 | backend parity 通过 |

内存是独立进程中读取 `resource.getrusage(RUSAGE_SELF).ru_maxrss` 的结果；
不同运行可能有小幅波动。Paddle 与 ONNX 的运行库目录在同一隔离环境中
分别约为 399 MB 与 74 MB（不含共同依赖），因此 ONNX 的正式打包闭包明显
更小，但其 ORT 全图优化带来的峰值内存更高。

## 准确率解释

当前测试图片没有随附机器可读 ground truth，因此不能把模型输出与权威
标注逐字符比较；语义准确率记为：`NOT VERIFIED`。本阶段实际验证的是：

1. 两个 backend 都能在本地断网条件下使用已存在的本地模型文件运行。
2. 同一预处理和 tokenizer 下，16/16 张图片的解码后 LaTeX 完全一致。
3. 输出覆盖了化学式、可逆反应、热力学、多行公式、矩阵、积分等冻结测试类型。

人工查看表明复杂样本中存在相同的模型识别问题（例如第一张偏导式和
第二张 cases 图片），因此 ONNX 并没有悄悄改变 Paddle 的识别结果；这些
问题应在后续真实标注回归集中处理，而不是在 Stage A 改化学语义。

## 推荐后端

```text
RECOMMENDED_BACKEND = ONNX
```

理由：16/16 backend parity，加载和 CPU 热推理明显更快，模型目录和正式
运行时更小，且不需要把 PaddlePaddle/PaddleOCR 带入最终 `.app/.dmg`。

保留的风险：ONNX Runtime 当前峰值 RSS 较高，Stage B 首次核心 OCR 实现
必须再次做单图和长公式内存验证；若在真实 GUI 流程中不可接受，应回到
Paddle 重新评估。当前没有证据表明 ONNX 的精度低于 Paddle。

## 依赖与许可证

Stage A 隔离环境实际使用：`paddlepaddle==3.0.0`（仅 baseline）、
`onnxruntime==1.28.0`、`Pillow==12.3.0`、`opencv-python-headless==4.11.0.86`、
`tokenizers==0.23.1`、`PyYAML==6.0.3`。这些版本不是最终发布依赖冻结。

RapidDoc 参考代码和 PP-FormulaNet_plus-M 模型 README 均标示 Apache-2.0；
详情见 `THIRD_PARTY_NOTICES.md`。

## 未解决问题

- 没有机器可读 ground truth，语义准确率仍为 `NOT VERIFIED`。
- ONNX 的峰值 RSS 高于 Paddle，需要在 Stage B 的正式 engine 中复测。
- 尚未做 GUI、MathML、剪贴板、截图、快捷键或 DMG；按 Taskbook 这些全部留到后续 Stage。
