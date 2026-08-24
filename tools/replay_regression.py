#!/usr/bin/env python3
"""Capture reproducible OCR evidence for regression comparisons.

The report intentionally separates image/model/preprocess identity, raw model
tokens, and presentation formatting.  It never edits a history record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from app.paths import FORMULA_MODEL_PATH
from ocr.backend import ONNXFormulaBackend, preprocess
from ocr.postprocess import normalize_latex


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def replay(path: Path, backend: ONNXFormulaBackend) -> dict[str, object]:
    image_bytes = path.read_bytes()
    image = Image.open(path).convert("RGB")
    tensor = preprocess(image)
    result = backend.recognize(image)
    return {
        "path": str(path),
        "image_sha256": sha256_bytes(image_bytes),
        "model_sha256": sha256_bytes(Path(backend.model_path).read_bytes()),
        "preprocess_sha256": sha256_bytes(tensor.tobytes()),
        "preprocess_shape": list(tensor.shape),
        "token_ids": list(result.token_ids),
        "raw_latex": result.raw_latex,
        "case_refined_latex": result.case_refined_latex,
        "chemistry_latex": normalize_latex(result.case_refined_latex or result.raw_latex, mode="chemistry"),
        "math_latex": normalize_latex(result.case_refined_latex or result.raw_latex, mode="math"),
        "elapsed_ms": result.elapsed_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--model", type=Path, default=FORMULA_MODEL_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    backend = ONNXFormulaBackend(args.model)
    backend.load()
    payload = {"schema": 1, "records": [replay(path, backend) for path in args.images]}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
