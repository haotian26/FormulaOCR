import copy
import hashlib
import json

import pytest

from tools.accuracy_benchmark import (
    DEFAULT_MANIFEST, POLICY, compare_reports, load_manifest,
    normalized_formula, score, summarize,
)


@pytest.mark.parametrize(("left", "right"), [
    (r"\mathrm{F}^-", "F^{-}"),
    (r"$ \mathrm{HF}^{\circ} $", r"HF^\circ"),
    (r"H_2 O", "H_{2}O"),
    (r"\left(x^{2}\right)", r"(x^2)"),
])
def test_only_presentation_normalization(left, right):
    assert normalized_formula(left) == normalized_formula(right)


@pytest.mark.parametrize(("expected", "predicted", "metric"), [
    ("F^-", "F", "charges"),
    ("F^-", "F^+", "charges"),
    (r"HF^\circ", "HF^0", "superscripts"),
    (r"HF^\circ", "HF", "superscripts"),
    ("H_2O", "H_3O", "subscripts"),
    ("Cl^-", "CI^-", "elements"),
    ("NaCl", "Nacl", "elements"),
    ("Nd^{3+}", "Nd^{2+}", "charges"),
])
def test_critical_literal_changes_are_not_normalized_away(expected, predicted, metric):
    values = score(expected, predicted, chemistry=True)
    assert values["exact"] is False
    assert values[metric] is False


def test_renderability_is_not_an_accuracy_metric():
    assert score("F^-", "F", chemistry=True)["exact"] is False
    assert score("x^2", "x^3")["exact"] is False


@pytest.mark.parametrize("prediction", ["F^{", "F}", "F^"])
def test_malformed_predictions_fail_metrics(prediction):
    assert all(value is False for value in score("F^-", prediction, chemistry=True).values())


def report(manifest):
    return {
        "schema": 1, "metric_policy": POLICY,
        "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
        "backend_sha256": "backend",
        "environment": {"onnxruntime": "test"},
        "records": [{"id": case["id"], "raw_latex": case["expected_latex"],
                     "image_sha256": case["id"], "preprocess_sha256": "tensor-" + case["id"],
                     "preprocess_shape": [1, 1, 768, 768]} for case in manifest["cases"]],
    }


def test_committed_manifest_is_nonprivate_and_has_sensitive_cases():
    manifest = load_manifest(DEFAULT_MANIFEST)
    assert len(manifest["cases"]) == 10
    assert {case["id"] for case in manifest["cases"]} >= {"fluoride", "hf_standard", "hf_zero"}
    assert all("image" not in case for case in manifest["cases"])


def test_identical_reports_pass():
    manifest = load_manifest(DEFAULT_MANIFEST)
    baseline = report(manifest)
    result = compare_reports(manifest, baseline, copy.deepcopy(baseline))
    assert result["passed"] is True
    assert result["unresolved_exact_cases"] == []


def test_one_improvement_cannot_offset_one_regression():
    manifest = load_manifest(DEFAULT_MANIFEST)
    baseline = report(manifest)
    candidate = copy.deepcopy(baseline)
    baseline["records"][0]["raw_latex"] = "F"
    candidate["records"][1]["raw_latex"] = "HF"
    result = compare_reports(manifest, baseline, candidate)
    assert result["passed"] is False
    assert {item["id"] for item in result["improvements"]} == {"fluoride"}
    assert {item["id"] for item in result["regressions"]} == {"hf_standard"}


def test_scores_are_recomputed_from_labels_not_trusted_from_report():
    manifest = load_manifest(DEFAULT_MANIFEST)
    baseline = report(manifest)
    candidate = copy.deepcopy(baseline)
    candidate["records"][0].update(raw_latex="F", scores={"exact": True})
    assert compare_reports(manifest, baseline, candidate)["passed"] is False


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "tensor", "image", "shape", "error", "policy", "manifest", "backend", "environment"])
def test_fail_closed_on_incomplete_or_incomparable_runs(mutation):
    manifest = load_manifest(DEFAULT_MANIFEST)
    baseline = report(manifest)
    candidate = copy.deepcopy(baseline)
    if mutation == "missing":
        candidate["records"].pop()
    elif mutation == "duplicate":
        candidate["records"].append(candidate["records"][0])
    elif mutation == "extra":
        candidate["records"].append({"id": "extra"})
    elif mutation == "error":
        candidate["records"][0]["error"] = "inference failed"
    elif mutation in {"tensor", "image", "shape"}:
        key = {"tensor": "preprocess_sha256", "image": "image_sha256", "shape": "preprocess_shape"}[mutation]
        candidate["records"][0][key] = "different"
    else:
        key = {"policy": "metric_policy", "manifest": "manifest_sha256", "backend": "backend_sha256", "environment": "environment"}[mutation]
        candidate[key] = "different"
    assert compare_reports(manifest, baseline, candidate)["passed"] is False


def test_missing_scores_are_not_counted_as_correct_and_elements_are_scoped():
    scores = score("x^2", "x^2")
    assert scores["elements"] is None
    summary = summarize([{"scores": scores}])
    assert summary["exact"] == {"correct": 1, "total": 1, "fraction": 1.0}
    assert summary["elements"] == {"correct": 0, "total": 0, "fraction": None}


def test_existing_miss_remains_visible_even_in_a_nonregressing_comparison():
    manifest = load_manifest(DEFAULT_MANIFEST)
    baseline = report(manifest)
    baseline["records"][0]["raw_latex"] = "F"
    result = compare_reports(manifest, baseline, copy.deepcopy(baseline))
    assert result["passed"] is True
    assert result["unresolved_exact_cases"] == ["fluoride"]


def test_changed_ground_truth_cannot_reuse_old_reports():
    manifest = load_manifest(DEFAULT_MANIFEST)
    baseline = report(manifest)
    manifest["cases"][0]["expected_latex"] = "F^+"
    assert compare_reports(manifest, baseline, baseline)["passed"] is False


def test_memory_monitor_failure_terminates_worker(tmp_path, monkeypatch):
    import subprocess
    import sys
    from tools.quantization_experiment import bounded_command
    def denied(*args, **kwargs):
        raise PermissionError("process information unavailable")
    monkeypatch.setattr(subprocess, "check_output", denied)
    result = bounded_command([sys.executable, "-c", "import time; time.sleep(10)"], tmp_path, 2, 256)
    assert result["termination_reason"] == "memory_monitor_unavailable"
    assert result["returncode"] != 0


def test_quantization_worker_refuses_repo_or_existing_candidate(tmp_path):
    from tools.quantization_experiment import ROOT, worker
    with pytest.raises(ValueError, match="cannot overwrite"):
        worker(tmp_path / "source.onnx", ROOT)
    output = tmp_path / "experiment"
    output.mkdir()
    (output / "candidate.onnx").write_bytes(b"do not overwrite")
    with pytest.raises(ValueError, match="cannot overwrite"):
        worker(tmp_path / "source.onnx", output)
    assert (output / "candidate.onnx").read_bytes() == b"do not overwrite"
