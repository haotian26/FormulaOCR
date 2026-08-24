"""Deterministic checks for model-free OCR consistency and candidate crops."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from ocr.backend import (
    MODEL_CONTENT_OCCUPANCY,
    _add_content_safety_margin,
    _foreground_box,
    _needs_content_safety_margin,
    preprocess,
)
from ocr.validation import (
    compare_images,
    latex_structure_valid,
    outer_wrapper_has_image_evidence,
    strip_outer_latex_wrappers,
)


def _formula_image(text: str, width: int = 420, height: int = 120) -> Image.Image:
    image = Image.new("L", (width, height), 255)
    ImageDraw.Draw(image).text((50, 42), text, fill=0)
    return image


def main() -> None:
    source = _formula_image("x = y")
    same = compare_images(source, source, r"x=y")
    extra_bars = _formula_image("| x = y |")
    wrong_structure = compare_images(extra_bars, source, r"x=y")
    assert same.syntax_valid and same.score > 0.95, same
    assert wrong_structure.score < same.score - 0.08, (same, wrong_structure)
    assert latex_structure_valid(r"\left|x=y\right|")
    assert not latex_structure_valid(r"\left|x=y")
    assert strip_outer_latex_wrappers(r"\left|x=y\right|") == [r"x=y"]
    assert strip_outer_latex_wrappers(r"\boxed{x=y}") == [r"x=y"]
    assert strip_outer_latex_wrappers(r"\left|x\right|+z") == []
    assert not outer_wrapper_has_image_evidence(source, r"\left|x=y\right|")
    assert compare_images(source, source, r"\left|x=y\right|").score < 0.5

    framed = _formula_image("x = y")
    ImageDraw.Draw(framed).rectangle((0, 0, framed.width - 1, framed.height - 1), outline=184, width=1)
    box = _foreground_box(framed)
    assert box is not None and box[0] > 5 and box[1] > 5
    print("preview frame removal: PASS")
    print("visual consistency score: PASS")
    print("LaTeX structure balance: PASS")

    sample = Path("tests/samples/2026-08-08_02-32-28.png")
    baseline = preprocess(sample, variant="baseline")
    context8 = preprocess(sample, variant="context8")
    context16 = preprocess(sample, variant="context16")
    assert baseline.shape == context8.shape == context16.shape
    assert (baseline != context8).any() or (baseline != context16).any()
    print("deterministic preprocessing variants: PASS")

    edge_sample = Image.new("RGB", (1200, 120), "white")
    ImageDraw.Draw(edge_sample).rectangle((0, 20, 1199, 99), fill="black")
    safe_sample = _add_content_safety_margin(edge_sample)
    expected_width = math.ceil(edge_sample.width / MODEL_CONTENT_OCCUPANCY)
    expected_height = math.ceil(edge_sample.height / MODEL_CONTENT_OCCUPANCY)
    assert safe_sample.size == (expected_width, expected_height)
    assert expected_width - edge_sample.width >= 12
    assert expected_height - edge_sample.height >= 1
    ordinary = Image.new("RGB", (500, 100), "white")
    ordinary_draw = ImageDraw.Draw(ordinary)
    ordinary_draw.rectangle((20, 10, 470, 80), fill="black")
    assert not _needs_content_safety_margin(ordinary)
    terminal_script = ordinary.copy()
    terminal_draw = ImageDraw.Draw(terminal_script)
    terminal_draw.rectangle((486, 4, 497, 16), fill="black")
    assert _needs_content_safety_margin(terminal_script)
    print("adaptive 99% content occupancy: PASS")


if __name__ == "__main__":
    main()
