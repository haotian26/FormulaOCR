"""Compare the current transport against the released RGB input path, read-only."""
import argparse
import io
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from PIL import Image
from ocr.backend import ONNXFormulaBackend, preprocess
from ocr.postprocess import normalize_latex
from converter.latex_to_mathml import latex_to_mathml
from sidecar.server import Sidecar


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directories", type=Path, nargs="+")
    args = parser.parse_args()
    backend = ONNXFormulaBackend()
    start = perf_counter()
    backend.load()
    load_ms = (perf_counter() - start) * 1000
    samples = sorted({path for directory in args.directories for path in directory.glob("*.png")})
    records = []
    for path in samples:
        contents = path.read_bytes()
        old_image = Image.open(io.BytesIO(contents)).convert("RGB")
        new_image = Image.open(io.BytesIO(Sidecar._validated_image(contents))).convert("RGB")
        same = np.array_equal(preprocess(old_image), preprocess(new_image))
        result = backend.recognize(new_image)
        formatted = normalize_latex(result.case_refined_latex or result.raw_latex, mode="chemistry")
        error = None
        try:
            latex_to_mathml(formatted)
        except Exception as caught:
            error = str(caught)
        records.append({"name": path.name, "tensor_identical": same, "renderable": error is None, "error": error, "ms": round(result.elapsed_ms, 1)})
    print(json.dumps({"load_ms": round(load_ms,1), "count": len(records), "records": records}, indent=2))
    return 0 if all(record["tensor_identical"] for record in records) else 1

if __name__ == "__main__":
    raise SystemExit(main())
