#!/usr/bin/env python3
"""Download the fixed FormulaOCR L model and verify its SHA256."""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path


URL = "https://www.modelscope.cn/models/RapidAI/RapidDoc/resolve/v1.0.0/formula/PP-FormulaNet_plus-L/pp_formulanet_plus_l.onnx"
SHA256 = "5ef81a0b197ea2c8c1463b31c3eb2ad0ae1eb655fb1ff3b550858c7d85bc84e8"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "resources/models/PP-FormulaNet_plus-L-ONNX/pp_formulanet_plus_l.onnx"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    if OUTPUT.is_file() and digest(OUTPUT) == SHA256:
        print(f"Model already verified: {OUTPUT}")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="formulaocr-model-", suffix=".onnx", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        print(f"Downloading {URL}")
        with urllib.request.urlopen(URL) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = digest(temporary)
        if actual != SHA256:
            raise RuntimeError(f"Model SHA256 mismatch: expected {SHA256}, got {actual}")
        temporary.replace(OUTPUT)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Model verified: {OUTPUT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FormulaOCR model download failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
