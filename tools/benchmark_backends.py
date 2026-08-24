#!/usr/bin/env python3
"""Stage A benchmark for the FormulaOCR backends.

This is a development-only tool.  It intentionally keeps the Paddle and ONNX
implementations behind the same image pre-processing and tokenizer decode so
that backend parity can be measured without adding UI or application code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from PIL import Image, ImageOps
from tokenizers import Tokenizer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "resources" / "models" / "PP-FormulaNet_plus-M"
SAMPLES_DIR = PROJECT_ROOT / "tests" / "samples"
ONNX_MODEL = Path(
    os.environ.get(
        "FORMULAOCR_ONNX_MODEL",
        str(
            PROJECT_ROOT
            / "resources"
            / "models"
            / "PP-FormulaNet_plus-M-ONNX"
            / "pp_formulanet_plus_m.onnx"
        ),
    )
)


def preprocess(path: Path, size: int = 384) -> np.ndarray:
    """Match RapidDoc's PP-FormulaNet_plus preprocessing exactly."""

    image = Image.open(path).convert("RGB")
    data = np.asarray(image.convert("L"), dtype=np.uint8)
    max_val, min_val = int(data.max()), int(data.min())
    if max_val != min_val:
        scaled = (data - min_val) / (max_val - min_val) * 255
        mask = 255 * (scaled < 200).astype(np.uint8)
        coords = cv2.findNonZero(mask)
        if coords is not None:
            left, top, width, height = cv2.boundingRect(coords)
            image = image.crop((left, top, left + width, top + height))

    width, height = image.size
    short_edge = min(width, height)
    if height <= width:
        new_height, new_width = short_edge, int(short_edge * width / height)
    else:
        new_height, new_width = int(short_edge * height / width), short_edge
    image = image.resize((new_width, new_height), resample=2)
    image.thumbnail((size, size))
    delta_width, delta_height = size - image.width, size - image.height
    image = ImageOps.expand(
        image,
        (
            delta_width // 2,
            delta_height // 2,
            delta_width - delta_width // 2,
            delta_height - delta_height // 2,
        ),
    )

    array = np.asarray(image)
    mean = np.asarray([0.7931] * 3, dtype="float32").reshape(1, 1, 3)
    std = np.asarray([0.1738] * 3, dtype="float32").reshape(1, 1, 3)
    array = (array.astype("float32") / 255.0 - mean) / std
    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
    array = cv2.merge([gray] * 3)[:, :, 0]
    height = math.ceil(array.shape[0] / 16) * 16
    width = math.ceil(array.shape[1] / 16) * 16
    array = np.pad(
        array,
        ((0, height - array.shape[0]), (0, width - array.shape[1])),
        constant_values=(1, 1),
    )
    return array[None, None].astype("float32", copy=False)


class FormulaDecoder:
    def __init__(self, character_metadata: dict[str, Any]):
        tokenizer_json = json.dumps(character_metadata["fast_tokenizer_file"])
        self.tokenizer = Tokenizer.from_str(tokenizer_json)

    def decode(self, token_ids: np.ndarray) -> list[str]:
        results: list[str] = []
        for row in np.asarray(token_ids):
            ids = [int(value) for value in row]
            if 2 in ids:
                ids = ids[: ids.index(2) + 1]
            results.append(self.tokenizer.decode(ids, skip_special_tokens=True))
        return results


class PaddleBackend:
    name = "paddle"

    def __init__(self, model_dir: Path):
        from paddle import inference

        self.inference = inference
        config = inference.Config(
            str(model_dir / "inference.json"),
            str(model_dir / "inference.pdiparams"),
        )
        config.disable_gpu()
        config.disable_glog_info()
        self.predictor = inference.create_predictor(config)
        import yaml

        config = yaml.safe_load((model_dir / "inference.yml").read_text())
        self.decoder = FormulaDecoder(config["PostProcess"]["character_dict"])

    def recognize(self, batch: np.ndarray) -> list[str]:
        handle = self.predictor.get_input_handle("x")
        handle.copy_from_cpu(batch)
        self.predictor.run()
        output = self.predictor.get_output_handle("fetch_name_0").copy_to_cpu()
        return self.decoder.decode(output)


class OnnxBackend:
    name = "onnx"

    def __init__(self, model_path: Path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(model_path), options, providers=["CPUExecutionProvider"]
        )
        metadata = self.session.get_modelmeta().custom_metadata_map
        self.decoder = FormulaDecoder(json.loads(metadata["character"]))
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def recognize(self, batch: np.ndarray) -> list[str]:
        output = self.session.run([self.output_name], {self.input_name: batch})[0]
        return self.decoder.decode(output)


@dataclass
class SampleResult:
    sample: str
    latex: str
    elapsed_ms: float


@dataclass
class BackendResult:
    backend: str
    load_ms: float
    warmup_ms: float
    samples: list[SampleResult]
    model_bytes: int
    dependencies: list[str]
    max_rss_mb: float | None = None


def benchmark_backend(backend: Any, images: list[tuple[str, np.ndarray]], model_bytes: int, dependencies: list[str]) -> BackendResult:
    warmup_name, warmup_image = images[0]
    warmup_start = time.perf_counter()
    backend.recognize(warmup_image)
    warmup_ms = (time.perf_counter() - warmup_start) * 1000

    sample_results: list[SampleResult] = []
    for name, image in images:
        start = time.perf_counter()
        latex = backend.recognize(image)[0]
        sample_results.append(
            SampleResult(sample=name, latex=latex, elapsed_ms=(time.perf_counter() - start) * 1000)
        )
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    rss_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    return BackendResult(
        backend=backend.name,
        load_ms=0.0,
        warmup_ms=warmup_ms,
        samples=sample_results,
        model_bytes=model_bytes,
        dependencies=dependencies,
        max_rss_mb=rss_mb,
    )


def build_backend(factory: Any, name: str, *args: Any) -> tuple[Any, float]:
    start = time.perf_counter()
    backend = factory(*args)
    return backend, (time.perf_counter() - start) * 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Only benchmark the first N samples")
    parser.add_argument("--skip-paddle", action="store_true")
    parser.add_argument("--skip-onnx", action="store_true")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs" / "backend_benchmark.json")
    args = parser.parse_args()

    sample_paths = sorted(SAMPLES_DIR.glob("*.png"))
    if args.limit:
        sample_paths = sample_paths[: args.limit]
    images = [(path.name, preprocess(path)) for path in sample_paths]
    results: list[BackendResult] = []

    if not args.skip_paddle:
        backend, load_ms = build_backend(PaddleBackend, "paddle", MODEL_DIR)
        result = benchmark_backend(
            backend,
            images,
            (MODEL_DIR / "inference.pdiparams").stat().st_size,
            ["paddlepaddle", "Pillow", "opencv-python-headless", "tokenizers"],
        )
        result.load_ms = load_ms
        results.append(result)

    if not args.skip_onnx:
        if not ONNX_MODEL.is_file():
            raise FileNotFoundError(f"ONNX model not found: {ONNX_MODEL}")
        backend, load_ms = build_backend(OnnxBackend, "onnx", ONNX_MODEL)
        result = benchmark_backend(
            backend,
            images,
            ONNX_MODEL.stat().st_size,
            ["onnxruntime", "Pillow", "opencv-python-headless", "tokenizers"],
        )
        result.load_ms = load_ms
        results.append(result)

    payload = {
        "project": str(PROJECT_ROOT),
        "model": "PP-FormulaNet_plus-M",
        "sample_count": len(images),
        "results": [asdict(result) for result in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    for result in results:
        print(f"[{result.backend}] load_ms={result.load_ms:.1f} warmup_ms={result.warmup_ms:.1f}")
        for sample in result.samples:
            print(f"{sample.sample}\t{sample.elapsed_ms:.1f} ms\t{sample.latex}")

    if len(results) == 2:
        left = {item.sample: item.latex for item in results[0].samples}
        right = {item.sample: item.latex for item in results[1].samples}
        equal = sum(left[name] == right[name] for name in left)
        print(f"backend_exact_match={equal}/{len(left)}")


if __name__ == "__main__":
    main()
