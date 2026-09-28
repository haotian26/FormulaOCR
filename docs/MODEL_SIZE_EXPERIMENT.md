# Model size experiment and labelled OCR gate

## Decision — 2026-09-28

Keep the production PP-FormulaNet_plus-L model and preprocessing unchanged.
One isolated post-training INT8 experiment produced a smaller file, but ONNX
Runtime rejected the graph during CPU loading. The candidate is **rejected**;
it has no measured recognition accuracy and is not a deployable size saving.
No training, fine-tuning, calibration on user images, chemistry inference, or
production model replacement was performed.

## Bounded experiment

The trial used Python 3.13.15, ONNX 1.23.0 and ONNX Runtime 1.29.0 on Apple
Silicon macOS. ORT 1.29.0 and numpy 2.5.2 match the installed app inspected for
this run. Dynamic per-channel signed INT8 was applied only to constant-weight
`MatMul`, including subgraphs. Convolution and the application pipeline were
not altered. The experiment follows the runtime's public
[post-training quantization API](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html).

| Measurement | Result |
| --- | --- |
| Original model | 735,068,718 bytes (701.02 MiB) |
| Trial output file | 299,131,313 bytes (285.27 MiB) |
| Apparent file reduction | 59.31%, **not a usable model/package reduction** |
| Process elapsed | 8.519 seconds |
| Sampled peak resident memory | 3,482.3 MiB |
| Bounds | 180 seconds, 6,144 MiB sampled RSS, 16 MiB log |
| CPU load | Failed: `This is an invalid model. Error: the graph is not acyclic.` |
| Candidate OCR/latency | NOT TESTED; loading failed |
| Production model SHA256 before and after | `5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8` |

The quantizer completed file generation; runtime load validation did not.
This is an observed graph-validity failure of this configuration, not evidence
that every quantization method is unsupported. No repeated large trial or
graph-repair attempt was made. Detailed measurements are retained in
[`quantization_trial_macos_ort_1_29.json`](../tests/fixtures/ocr_accuracy/quantization_trial_macos_ort_1_29.json).
The rejected model file is not committed or bundled.

`tools/quantization_experiment.py` requires a new output directory outside the
repository and source model directory, refuses model overwrite, monitors its
child at roughly 0.2-second intervals, and kills it on time/memory/log limits.
RSS is a sampled termination threshold, not an operating-system memory quota;
brief between-sample spikes are possible. An unavailable memory monitor also
fails closed. Source and output hashes, package versions and failure details
are written to the experiment report. No candidate is automatically approved.

## Ground truth, scores and scope

The ten cases in [`manifest.json`](../tests/fixtures/ocr_accuracy/manifest.json)
are original synthetic formulas with independently explicit expected strings.
They cover `F^-`, `HF^\circ` versus `HF^0`, terminal charges on longer Nd-F and
sulfate expressions, subscripts, literal element case, a quadratic, a fraction,
and a log expression. Generated images were visually checked against all ten
labels. No private history images or source-paper screenshots are committed.
Mathtext/Computer Modern (matplotlib 3.11.2, 160 dpi, 24-point text, 16-pixel
white border) only generates input pixels; it never judges OCR correctness.

The metric compares **raw decoded OCR** against those labels. It ignores only
whitespace, an outer dollar delimiter, `\left`/`\right`, explicit spacing,
`\mathrm`/`\mathit`/`\mathnormal` styles, and optional braces around one script
atom. It preserves signs, letter case, zero versus circle, scripts, grouping,
operator order and extra content. It deliberately does not prove algebraic
equivalence, normalize every presentation wrapper, infer missing chemistry,
or award a match because MathML happens to render. Conservative exact-match
scores can therefore penalize some visually equivalent LaTeX forms.

Separate checks compare ordered charge-bearing superscripts, all subscripts,
all superscripts (including degree/circle), and literal case-sensitive letter
tokens for the seven labelled chemistry cases. The last metric is a lexical
check, not chemical parsing or validation. Component matches do not imply
whole-formula correctness; extra prose, for example, still fails exact match.
Feature-absent cases stay in whole-suite counts to detect invented scripts.
Feature-present denominators are also reported so empty cases cannot inflate
the apparent charge/subscript preservation rate.

The unchanged model's measured baseline was:

| Metric | All applicable cases | Cases containing the reference feature |
| --- | --- | --- |
| Conservative normalized exact formula | 3/10 | — |
| Charge sequence | 9/10 | 3/4 |
| Subscript sequence | 10/10 | 3/3 |
| Superscript sequence | 7/10 | 4/7 |
| Literal element-case sequence | 5/7 chemistry cases | — |

The long Nd-F expression, sulfate expression and quadratic matched exactly.
The short standalone F-minus, HF-circle and HF-zero examples expose raw
decoder misses; the report retains them instead of treating the baseline as
truth. Other misses include extra content and a presentation wrapper. Baseline
loading took 0.561 seconds; the bounded ten-case process took 18.867 seconds
including image generation and first font-cache construction, with sampled
peak RSS 2,495.4 MiB. That total is not steady-state per-image inference latency.
Raw predictions, labels, image/tensor/model hashes, actual `[1,1,768,768]`
preprocessing shapes and individual timings are preserved in
[`baseline_macos_ort_1_29.json`](../tests/fixtures/ocr_accuracy/baseline_macos_ort_1_29.json).

These are ten synthetic smoke cases, **not an estimate of general production
accuracy**. Real screenshot layouts, diverse fonts, handwriting, matrices and
larger independently annotated sets remain necessary before any replacement.
A passing comparison only means no demonstrated regression on this set.

## Reproduction and acceptance

Run these commands from the repository in a disposable Python 3.13 environment.
The production app does not gain ONNX or matplotlib dependencies; these are
development-only experiment dependencies.

```sh
python -m pip install -e . pytest onnx==1.23.0 onnxruntime==1.29.0 numpy==2.5.2 matplotlib==3.11.2
python -m pytest -q tests/test_accuracy_benchmark.py
python -m tools.accuracy_benchmark run --model resources/models/PP-FormulaNet_plus-L-ONNX/pp_formulanet_plus_l.onnx --output /tmp/formulaocr-baseline.json
python -m tools.quantization_experiment --model resources/models/PP-FormulaNet_plus-L-ONNX/pp_formulanet_plus_l.onnx --output-dir /tmp/formulaocr-new-int8-trial --timeout 180 --max-rss-mb 6144
```

Only if the experiment completes and the candidate loads:

```sh
python -m tools.accuracy_benchmark run --model /tmp/formulaocr-new-int8-trial/candidate.onnx --output /tmp/formulaocr-candidate.json
python -m tools.accuracy_benchmark compare /tmp/formulaocr-baseline.json /tmp/formulaocr-candidate.json --output /tmp/formulaocr-comparison.json
```

The compare command recomputes scores from the manifest, not from stored score
claims. It rejects missing/duplicate/extra cases, inference errors, changed
ground truth, backend/runtime identity, input pixels or preprocessed tensors.
Every previously correct case/metric must stay correct: an improvement on one
case cannot offset a regression on another. Existing incorrect cases remain in
an explicit unresolved list. Both runs must use the same labelled manifest,
runtime, preprocessing and pixels. A passing finite gate is necessary but not
sufficient for model adoption; production replacement remains a separate
reviewed decision.

Ordinary Python tests exercise this scoring and fail-closed behavior without
loading/downloading model weights or importing the experiment dependencies.
The local `.github/workflows/checks.yml` preserves frontend/Python checks and
adds native Rust fault-handling tests with a CI-only empty bundle-resource
override. Its **opt-in** `workflow_dispatch` input `model_quality` downloads the
checksum-pinned model and runs baseline, isolated PTQ and the comparison gate.
An unloadable/unfinished candidate fails that job; only JSON/log evidence is
uploaded, never model weights. This workflow file is local source preparation,
not a claim that remote Actions or workflow publication is enabled.
