# PP-FormulaNet_plus-L validation

日期：2026-08-15
状态：PARTIAL

## 模型来源

- 来源：RapidDoc ModelScope `v1.0.0`
- URL: <https://www.modelscope.cn/models/RapidAI/RapidDoc/resolve/v1.0.0/formula/PP-FormulaNet_plus-L/pp_formulanet_plus_l.onnx>
- SHA256: `5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8`
- ONNX 输入：`1 × 1 × 768 × 768`
- 许可：Apache-2.0（来源模型说明）

## 已验证

- 16 张现有样本均返回非空 LaTeX，并可转换为 MathML。
- 本次 `Nd^{3+}+3F^-=NdF_3(s)` 截图在排除预览面板边框后，L 输出不再包含整式 `\\phantom` 或外围方括号。
- 当前 Apple Silicon Mac 上 16 张样本单次推理约 0.6–2.3 秒。
- App 包内只包含 L ONNX，版本为 `0.2.0`，arm64 签名验证通过。

## 未验证

- 本机未安装 PaddlePaddle，官方 Paddle L 与 ONNX 的逐 token 对照尚未执行。
- 16 张历史样本缺少人工标注的权威 LaTeX，因此不能据此宣称语义准确率。
- 化学式状态符号的字体命令（例如 `\\mathfrak{s}` 与 `\\mathrm{s}`）仍需人工确认。
