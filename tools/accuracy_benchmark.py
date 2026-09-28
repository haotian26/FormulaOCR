#!/usr/bin/env python3
"""Ground-truth OCR scores; no semantic repair and no renderer-as-accuracy proxy.

Run from the repository with ``python -m tools.accuracy_benchmark --help``.
The scoring/compare code uses only the standard library. Model inference and
synthetic typesetting dependencies are imported only by the ``run`` command.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "tests/fixtures/ocr_accuracy/manifest.json"
METRICS = ("exact", "charges", "subscripts", "superscripts", "elements")
POLICY = "raw-latex-conservative-v1"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def normalized_formula(source: str) -> str:
    """Ignore only documented presentation differences, not scientific content.

    Preserve case, signs, script placement, order, symbols, and ordinary groups.
    This deliberately is not an algebra/chemistry equivalence checker. In
    particular degree, zero, neutral charge, and an absent charge stay distinct.
    """
    source = source.strip()
    if source.startswith("$$") and source.endswith("$$"):
        source = source[2:-2]
    elif source.startswith("$") and source.endswith("$"):
        source = source[1:-1]
    tokens = re.findall(r"\\[A-Za-z]+|\\.|[^\s]", source)
    position = 0
    styles = {r"\mathrm", r"\mathit", r"\mathnormal"}
    spacing = {r"\,", r"\;", r"\:", r"\!", r"\ ", r"\quad", r"\qquad", r"\left", r"\right"}

    def atom() -> str:
        nonlocal position
        if position >= len(tokens):
            raise ValueError("Missing LaTeX atom")
        token = tokens[position]
        position += 1
        if token == "{":
            return "{" + sequence(group=True) + "}"
        if token == "}":
            raise ValueError("Unmatched closing brace")
        if token in styles:
            value = atom()
            return value[1:-1] if value.startswith("{") else value
        if token in {"^", "_"}:
            value = atom()
            return token + (value if value.startswith("{") else "{" + value + "}")
        if token in spacing:
            return ""
        return token

    def sequence(group: bool = False) -> str:
        nonlocal position
        result = []
        while position < len(tokens):
            if tokens[position] == "}":
                if not group:
                    raise ValueError("Unmatched closing brace")
                position += 1
                return "".join(result)
            result.append(atom())
        if group:
            raise ValueError("Unclosed brace")
        return "".join(result)

    return sequence()


def signatures(normalized: str) -> dict[str, list[str]]:
    scripts: dict[str, list[str]] = {"^": [], "_": []}
    for match in re.finditer(r"(?<!\\)([\^_])\{", normalized):
        depth, end = 1, match.end()
        while end < len(normalized) and depth:
            if normalized[end] == "{" and normalized[end - 1] != "\\":
                depth += 1
            elif normalized[end] == "}" and normalized[end - 1] != "\\":
                depth -= 1
            end += 1
        scripts[match[1]].append(normalized[match.end():end - 1])
    # Literal case-sensitive letter tokens, only enabled for labelled chemistry
    # cases. No periodic-table lookup, valence, balancing, or charge inference.
    letters = re.sub(r"\\[A-Za-z]+|\\.", " ", normalized)
    elements = re.findall(r"[A-Z][a-z]?|[a-z]+", letters)
    return {
        "charges": [value for value in scripts["^"] if re.fullmatch(r"[0-9]*[+-]|[+-][0-9]*", value)],
        "subscripts": scripts["_"],
        "superscripts": scripts["^"],
        "elements": elements,
    }


def score(expected: str, predicted: str, chemistry: bool = False) -> dict[str, bool | None]:
    reference = normalized_formula(expected)
    try:
        actual = normalized_formula(predicted)
    except ValueError:
        return {metric: None if metric == "elements" and not chemistry else False for metric in METRICS}
    want, got = signatures(reference), signatures(actual)
    return {
        "exact": bool(actual) and reference == actual,
        **{key: want[key] == got[key] for key in ("charges", "subscripts", "superscripts")},
        "elements": want["elements"] == got["elements"] if chemistry else None,
    }


def load_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    ids = [case.get("id") for case in cases]
    if payload.get("schema") != 1 or not cases or len(ids) != len(set(ids)):
        raise ValueError("Manifest must contain nonempty, uniquely identified schema-1 cases")
    for case in cases:
        if not isinstance(case["id"], str) or not re.fullmatch(r"[a-z0-9_-]+", case["id"]):
            raise ValueError("Unsafe or missing case id")
        if not normalized_formula(case["expected_latex"]):
            raise ValueError("Ground truth cannot be empty")
        if bool(case.get("image")) == bool(case.get("synthetic_mathtext")):
            raise ValueError("Each case needs exactly one image source")
    return payload


def summarize(records: list[dict]) -> dict:
    result = {}
    for metric in METRICS:
        values = [record["scores"][metric] for record in records if record["scores"][metric] is not None]
        result[metric] = {"correct": sum(values), "total": len(values), "fraction": sum(values) / len(values) if values else None}
        if metric in {"charges", "subscripts", "superscripts"}:
            present = [record["scores"][metric] for record in records
                       if record.get("expected_latex") and signatures(normalized_formula(record["expected_latex"]))[metric]]
            result[metric]["reference_feature_present"] = {"correct": sum(present), "total": len(present),
                                                          "fraction": sum(present) / len(present) if present else None}
    result["errors"] = sum(bool(record.get("error")) for record in records)
    return result


def compare_reports(manifest: dict, baseline: dict, candidate: dict) -> dict:
    """Fail closed on absent cases, incomparable tensors, errors or regression.

    A correct baseline metric may never become incorrect, even if another case
    improves. Existing misses remain explicitly unresolved, not accepted truth.
    """
    reasons, regressions, improvements, unresolved = [], [], [], []
    for key in ("schema", "metric_policy", "manifest_sha256", "backend_sha256", "environment"):
        if key not in baseline or baseline.get(key) != candidate.get(key):
            reasons.append(f"incomparable {key}")
    if baseline.get("schema") != 1 or baseline.get("metric_policy") != POLICY:
        reasons.append("unsupported report schema or metric policy")
    manifest_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    if baseline.get("manifest_sha256") != manifest_hash:
        reasons.append("reports do not match the supplied labelled manifest")
    expected_ids = {case["id"] for case in manifest["cases"]}
    indexed = []
    for label, report in (("baseline", baseline), ("candidate", candidate)):
        records = report.get("records", [])
        index = {record["id"]: record for record in records}
        if len(index) != len(records) or set(index) != expected_ids:
            reasons.append(f"{label} case coverage differs")
        indexed.append(index)
    for case in manifest["cases"]:
        before, after = [index.get(case["id"]) for index in indexed]
        if before is None or after is None:
            continue
        for key in ("image_sha256", "preprocess_sha256", "preprocess_shape"):
            if not before.get(key) or before.get(key) != after.get(key):
                reasons.append(f"{case['id']}: incomparable {key}")
        if before.get("error") or after.get("error"):
            reasons.append(f"{case['id']}: inference error")
        scores = [score(case["expected_latex"], item.get("raw_latex", ""), case.get("chemistry", False)) for item in (before, after)]
        for metric in METRICS:
            if scores[0][metric] is True and scores[1][metric] is False:
                regressions.append({"id": case["id"], "metric": metric})
            if scores[0][metric] is False and scores[1][metric] is True:
                improvements.append({"id": case["id"], "metric": metric})
        if not scores[1]["exact"]:
            unresolved.append(case["id"])
    return {
        "schema": 1, "passed": not reasons and not regressions,
        "reasons": reasons, "regressions": regressions, "improvements": improvements,
        "unresolved_exact_cases": unresolved,
        "scope": "Only this labelled set; not proof of general accuracy or approval to replace the bundled model.",
    }


def image_for_case(case: dict, manifest_path: Path):
    from PIL import Image, ImageOps
    if case.get("image"):
        path = manifest_path.parent / case["image"]
        with Image.open(path) as image:
            return image.convert("RGB")
    import matplotlib
    from matplotlib.font_manager import FontProperties
    from matplotlib.mathtext import math_to_image
    buffer = io.BytesIO()
    with matplotlib.rc_context({"mathtext.fontset": "cm", "font.family": "serif"}):
        math_to_image("$" + case["synthetic_mathtext"] + "$", buffer, prop=FontProperties(size=case.get("font_size", 24)), dpi=160, format="png", color="black")
    buffer.seek(0)
    with Image.open(buffer) as rendered:
        return ImageOps.expand(rendered.convert("RGB"), border=16, fill="white")


def run_model(manifest_path: Path, model_path: Path, images_dir: Path | None = None) -> dict:
    import matplotlib
    import numpy as np
    import onnxruntime
    from ocr.backend import ONNXFormulaBackend, preprocess
    manifest = load_manifest(manifest_path)
    backend = ONNXFormulaBackend(model_path)
    started = time.perf_counter()
    backend.load()
    load_seconds = time.perf_counter() - started
    records = []
    if images_dir:
        images_dir.mkdir(parents=True, exist_ok=True)
    for case in manifest["cases"]:
        image = image_for_case(case, manifest_path)
        if images_dir:
            image.save(images_dir / (case["id"] + ".png"))
        # Use the model's actual 768-square input, not preprocess's default 384.
        tensor = preprocess(image, size=backend._input_size, variant="baseline")
        record = {"id": case["id"], "expected_latex": case["expected_latex"],
                  "image_sha256": hashlib.sha256(image.tobytes() + str(image.size).encode()).hexdigest(),
                  "preprocess_sha256": hashlib.sha256(tensor.tobytes()).hexdigest(),
                  "preprocess_shape": list(tensor.shape)}
        try:
            result = backend.recognize(image)
            record.update(raw_latex=result.raw_latex, token_ids=list(result.token_ids), elapsed_ms=result.elapsed_ms)
        except Exception as exc:
            record.update(raw_latex="", error=f"{type(exc).__name__}: {exc}")
        record["scores"] = score(case["expected_latex"], record["raw_latex"], case.get("chemistry", False))
        records.append(record)
    return {"schema": 1, "metric_policy": POLICY,
            "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "backend_sha256": digest(ROOT / "ocr/backend.py"), "model_sha256": digest(model_path),
            "model_bytes": model_path.stat().st_size, "model_load_seconds": load_seconds,
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "onnxruntime": onnxruntime.__version__, "numpy": np.__version__, "matplotlib": matplotlib.__version__},
            "records": records, "summary": summarize(records)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Recognize the labelled set with an explicit local model")
    run.add_argument("--model", required=True, type=Path)
    run.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    run.add_argument("--images-dir", type=Path)
    run.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("compare", help="Fail on any per-case metric regression")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        payload = run_model(args.manifest, args.model, args.images_dir)
        passed = payload["summary"]["errors"] == 0
    else:
        payload = compare_reports(load_manifest(args.manifest), json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
        passed = payload["passed"]
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload.get("summary", payload), indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
