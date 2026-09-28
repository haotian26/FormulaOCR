#!/usr/bin/env python3
"""One bounded, opt-in post-training INT8 trial, never a model installer.

Dynamic quantization touches constant-weight MatMul operations (including
subgraphs), not convolution, preprocessing, tokenization or chemistry rules.
The parent kills a worker that exceeds wall time or sampled resident memory.
All outputs must live in a new directory outside the repository/model folder.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def worker(source: Path, output: Path) -> int:
    source, output = source.resolve(), output.resolve()
    if (output == ROOT or ROOT in output.parents or output == source.parent or source.parent in output.parents
            or (output / "candidate.onnx").exists()):
        raise ValueError("Worker cannot overwrite a candidate or write into the repository/source-model directory")
    import onnx
    import onnxruntime
    from onnxruntime.quantization import QuantType, quantize_dynamic
    started = time.perf_counter()
    report = {"schema": 1, "method": "dynamic-int8-constant-MatMul-subgraphs",
              "training": False, "onnx": onnx.__version__, "onnxruntime": onnxruntime.__version__}
    try:
        quantize_dynamic(source, output / "candidate.onnx", op_types_to_quantize=["MatMul"],
                         per_channel=True, weight_type=QuantType.QInt8,
                         extra_options={"EnableSubgraph": True, "MatMulConstBOnly": True})
        report["quantization"] = "completed"
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2
        session = onnxruntime.InferenceSession(str(output / "candidate.onnx"), options, providers=["CPUExecutionProvider"])
        report.update(cpu_load="passed", input_shape=session.get_inputs()[0].shape,
                      tokenizer_metadata_present="character" in session.get_modelmeta().custom_metadata_map)
        result = 0
    except Exception as exc:
        report.update(error_type=type(exc).__name__, error=str(exc), cpu_load="not_passed")
        result = 1
    report["elapsed_seconds"] = time.perf_counter() - started
    (output / "worker-result.json").write_text(json.dumps(report, indent=2) + "\n")
    return result


def bounded_command(command: list[str], output: Path, timeout: float, max_rss_mb: int) -> dict:
    """Monitor one child, retaining a bounded log and explicit termination reason."""
    started = time.monotonic()
    peak_rss = 0
    reason = None
    env = {**os.environ, "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "VECLIB_MAXIMUM_THREADS": "2",
           "MPLCONFIGDIR": str(output / "matplotlib-cache")}
    with (output / "worker.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
        try:
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    reason = "wall_time_limit"
                    break
                try:
                    rss = subprocess.check_output(["ps", "-o", "rss=", "-p", str(process.pid)], text=True, stderr=subprocess.DEVNULL, timeout=2)
                    peak_rss = max(peak_rss, int(rss.strip() or 0))
                except (OSError, subprocess.SubprocessError, ValueError):
                    # Process may have exited between poll() and ps.
                    if process.poll() is None:
                        reason = "memory_monitor_unavailable"
                        break
                if peak_rss > max_rss_mb * 1024:
                    reason = "resident_memory_limit"
                    break
                if (output / "worker.log").stat().st_size > 16 * 1024 * 1024:
                    reason = "log_size_limit"
                    break
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                process.kill()
            returncode = process.wait(timeout=10)
    return {"returncode": returncode, "termination_reason": reason,
            "elapsed_seconds": round(time.monotonic() - started, 3), "sampled_peak_rss_mib": round(peak_rss / 1024, 1)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--max-rss-mb", type=int, default=6144)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args.model, args.output_dir)
    from tools.accuracy_benchmark import digest
    source, output = args.model.resolve(), args.output_dir.resolve()
    if not source.is_file() or source.stat().st_size > 1024 ** 3:
        parser.error("Input must be an existing model no larger than 1 GiB")
    if output == ROOT or ROOT in output.parents or source.parent == output or source.parent in output.parents:
        parser.error("Experiment outputs must be outside the repository and source-model directory")
    if output.exists():
        parser.error("Output directory must not already exist; no files will be overwritten")
    if not 1 <= args.timeout <= 600 or not 256 <= args.max_rss_mb <= 8192:
        parser.error("Bounds: 1–600 seconds, 256–8192 MiB resident memory")
    output.mkdir(parents=True)
    if shutil.disk_usage(output).free < source.stat().st_size * 5:
        parser.error("Insufficient free space for the isolated trial")
    source_hash = digest(source)
    report = {"schema": 1, "model_sha256": source_hash, "source_bytes": source.stat().st_size,
              "platform": platform.platform(), "python": platform.python_version(),
              "limits": {"wall_seconds": args.timeout, "rss_mib": args.max_rss_mb, "log_mib": 16},
              "production_model_changed": False, "candidate_approved": False,
              "accuracy": "NOT TESTED; run the separate labelled benchmark before considering a candidate"}
    report["process"] = bounded_command([sys.executable, "-m", "tools.quantization_experiment", "--worker", "--model", str(source), "--output-dir", str(output)], output, args.timeout, args.max_rss_mb)
    details = output / "worker-result.json"
    if details.is_file():
        report["worker"] = json.loads(details.read_text())
    candidate = output / "candidate.onnx"
    if candidate.is_file():
        report.update(candidate_bytes=candidate.stat().st_size, candidate_sha256=digest(candidate),
                      size_reduction_fraction=1 - candidate.stat().st_size / report["source_bytes"])
    report["production_model_changed"] = digest(source) != source_hash
    report["completed"] = (
        report["process"]["returncode"] == 0
        and report.get("worker", {}).get("cpu_load") == "passed"
        and report.get("worker", {}).get("tokenizer_metadata_present") is True
        and not report["production_model_changed"]
    )
    (output / "experiment.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
