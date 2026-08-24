"""Model-free visual consistency checks for OCR candidates.

The validator does not infer LaTeX or claim semantic correctness.  It compares
the rendered shape of a candidate with the source image and is deliberately
used only to decide whether a second preprocessing pass is worthwhile.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True)
class ValidationScore:
    score: float
    syntax_valid: bool
    reason: str = ""


_OUTER_DELIMITER_PAIRS = {
    "(": ")",
    "[": "]",
    "\\{": "\\}",
    "\\lbrace": "\\rbrace",
    "\\langle": "\\rangle",
    "|": "|",
    "\\vert": "\\vert",
    "\\|": "\\|",
}


def _matching_brace_end(source: str, opening: int) -> int | None:
    """Return the closing brace index for a LaTeX group."""

    depth = 0
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if char == "{" and not escaped:
            depth += 1
        elif char == "}" and not escaped:
            depth -= 1
            if depth == 0:
                return index
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    return None


def strip_outer_latex_wrappers(latex: str) -> list[str]:
    """Return candidates without an outer visual wrapper.

    OCR may decode the whitespace around a displayed formula as
    ``\\boxed{...}`` or a balanced ``\\left...\\right`` pair.  The caller
    must compare these candidates with the source image before selecting one;
    this is not an unconditional symbol-removal rule.
    """

    if not isinstance(latex, str):
        return []
    source = latex.strip()
    candidates: list[str] = []

    boxed = re.match(r"^\\boxed\s*\{", source)
    if boxed:
        end = _matching_brace_end(source, boxed.end() - 1)
        if end == len(source) - 1:
            inner = source[boxed.end() : end].strip()
            if inner:
                candidates.append(inner)

    left = re.match(r"^\\left\s*(\\[A-Za-z]+|\\.|[()[\]{}|.])", source)
    if left:
        opening = left.group(1)
        closing = _OUTER_DELIMITER_PAIRS.get(opening)
        if closing is not None:
            right = re.search(r"\\right\s*(\\[A-Za-z]+|\\.|[()[\]{}|.])\s*$", source)
            if right and right.group(1) == closing:
                inner = source[left.end() : right.start()].strip()
                if inner:
                    candidates.append(inner)

    # FormulaNet sometimes adds an alignment container around the same
    # accidental wrapper.  Accept it only when the delimiter spans the whole
    # meaningful body; a genuine delimiter inside a multi-line expression is
    # left untouched.
    container = re.fullmatch(
        r"\\begin\{(aligned|alignedat\*?|gathered|array)\}(.*?)\\end\{\1\}",
        source,
        flags=re.DOTALL,
    )
    if container:
        body = container.group(2).strip()
        nested = re.match(
            r"^&?\s*\\left\s*(\\[A-Za-z]+|\\.|[()[\]{}|.])"
            r"(.*?)\\right\s*(\\[A-Za-z]+|\\.|[()[\]{}|.])\s*(?:\\\\)?$",
            body,
            flags=re.DOTALL,
        )
        if nested and _OUTER_DELIMITER_PAIRS.get(nested.group(1)) == nested.group(3):
            inner = nested.group(2).strip()
            if inner:
                candidates.append(inner)

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen and candidate != source:
            unique.append(candidate)
            seen.add(candidate)
    return unique


def _longest_true_run(values: np.ndarray) -> int:
    longest = current = 0
    for value in values.tolist():
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _has_edge_stroke(mask: np.ndarray, side: str) -> bool:
    """Whether a source formula has a long stroke at one outer edge."""

    height, width = mask.shape
    band = max(2, int(round(width * 0.08)))
    edge = mask[:, :band] if side == "left" else mask[:, width - band :]
    minimum_run = max(5, int(round(height * 0.35)))
    for column in edge.T:
        if _longest_true_run(column) >= minimum_run and float(column.mean()) >= 0.22:
            return True
    return False


def outer_wrapper_has_image_evidence(source: Any, latex: str) -> bool:
    """Return whether an outer wrapper has matching edge strokes in ``source``."""

    if not strip_outer_latex_wrappers(latex):
        return False
    try:
        mask = _foreground_mask(source)
    except (TypeError, ValueError):
        return True
    if not mask.any():
        return False
    return _has_edge_stroke(mask, "left") and _has_edge_stroke(mask, "right")


def _gray_array(image: Any) -> np.ndarray:
    if isinstance(image, (str, Path)):
        image = Image.open(image)
    if isinstance(image, Image.Image):
        image = np.asarray(image.convert("L"))
    else:
        array = np.asarray(image)
        if array.ndim == 3:
            if array.shape[2] == 4:
                array = array[:, :, :3]
            image = np.asarray(Image.fromarray(array.astype(np.uint8)).convert("L"))
        else:
            image = array
    gray = np.asarray(image, dtype=np.uint8)
    if gray.ndim != 2 or gray.size == 0:
        raise ValueError("Validation image must be a non-empty grayscale image")
    return gray


def _foreground_mask(image: Any) -> np.ndarray:
    gray = _gray_array(image)
    if gray.shape[0] > 2 and gray.shape[1] > 2:
        border = np.concatenate((gray[0], gray[-1], gray[1:-1, 0], gray[1:-1, -1]))
        if float(np.median(border)) < 128:
            gray = np.asarray(ImageOps.invert(Image.fromarray(gray)))
    minimum, maximum = int(gray.min()), int(gray.max())
    if minimum == maximum:
        return np.zeros_like(gray, dtype=bool)
    threshold = min(220, max(96, minimum + int((maximum - minimum) * 0.45)))
    mask = gray < threshold
    if not mask.any():
        mask = gray < min(245, maximum)
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return np.zeros_like(gray, dtype=bool)
    return mask[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]


def _canonical_mask(mask: np.ndarray, height: int = 128) -> np.ndarray:
    if not mask.any():
        return np.zeros((height, height), dtype=bool)
    source = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8))
    width = max(1, round(source.width * height / source.height))
    resized = source.resize((width, height), Image.Resampling.NEAREST)
    return np.asarray(resized) > 0


def _center_pair(left: np.ndarray, right: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    width = max(left.shape[1], right.shape[1]) + 12
    canvas_left = np.zeros((left.shape[0], width), dtype=bool)
    canvas_right = np.zeros((right.shape[0], width), dtype=bool)
    left_start = (width - left.shape[1]) // 2
    right_start = (width - right.shape[1]) // 2
    canvas_left[:, left_start : left_start + left.shape[1]] = left
    canvas_right[:, right_start : right_start + right.shape[1]] = right
    return canvas_left, canvas_right


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    left = left.astype(float).ravel()
    right = right.astype(float).ravel()
    left_norm, right_norm = float(np.linalg.norm(left)), float(np.linalg.norm(right))
    if left_norm == 0 or right_norm == 0:
        return 1.0 if left_norm == right_norm else 0.0
    return max(0.0, min(1.0, float(np.dot(left, right) / (left_norm * right_norm))))


def _dilated_overlap(source: np.ndarray, target: np.ndarray, radius: int = 3) -> float:
    if not source.any() or not target.any():
        return 1.0 if not source.any() and not target.any() else 0.0
    near = np.zeros_like(target, dtype=bool)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            source_y = slice(max(0, dy), min(source.shape[0], source.shape[0] + dy))
            source_x = slice(max(0, dx), min(source.shape[1], source.shape[1] + dx))
            target_y = slice(max(0, -dy), min(target.shape[0], target.shape[0] - dy))
            target_x = slice(max(0, -dx), min(target.shape[1], target.shape[1] - dx))
            near[target_y, target_x] |= source[source_y, source_x]
    precision = float(np.logical_and(target, near).sum()) / float(target.sum())
    near_source = np.zeros_like(source, dtype=bool)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            source_y = slice(max(0, dy), min(source.shape[0], source.shape[0] + dy))
            source_x = slice(max(0, dx), min(source.shape[1], source.shape[1] + dx))
            target_y = slice(max(0, -dy), min(target.shape[0], target.shape[0] - dy))
            target_x = slice(max(0, -dx), min(target.shape[1], target.shape[1] - dx))
            near_source[source_y, source_x] |= target[target_y, target_x]
    recall = float(np.logical_and(source, near_source).sum()) / float(source.sum())
    return max(0.0, min(1.0, 0.5 * (precision + recall)))


def _aspect_score(source: np.ndarray, target: np.ndarray) -> float:
    source_ratio = source.shape[1] / max(1, source.shape[0])
    target_ratio = target.shape[1] / max(1, target.shape[0])
    return math.exp(-abs(math.log(max(source_ratio, 1e-6) / max(target_ratio, 1e-6))))


def latex_structure_valid(latex: str) -> bool:
    """Check only delimiter and environment balance; never change LaTeX."""

    if not isinstance(latex, str) or not latex.strip():
        return False
    escaped = re.sub(r"\\[{}]", "", latex)
    if escaped.count("{") != escaped.count("}"):
        return False
    begins = re.findall(r"\\begin\{([^}]+)\}", latex)
    ends = re.findall(r"\\end\{([^}]+)\}", latex)
    if begins != ends:
        return False
    return len(re.findall(r"\\left\b", latex)) == len(re.findall(r"\\right\b", latex))


def compare_images(source: Any, rendered: Any, latex: str) -> ValidationScore:
    """Return a tolerant structural similarity score in the range [0, 1]."""

    if not latex_structure_valid(latex):
        return ValidationScore(0.0, False, "LaTeX 结构不完整")
    try:
        source_mask = _canonical_mask(_foreground_mask(source))
        rendered_mask = _canonical_mask(_foreground_mask(rendered))
    except (TypeError, ValueError):
        return ValidationScore(0.0, True, "图像无法分析")
    source_mask, rendered_mask = _center_pair(source_mask, rendered_mask)
    vertical = _cosine(source_mask.sum(axis=0), rendered_mask.sum(axis=0))
    horizontal = _cosine(source_mask.sum(axis=1), rendered_mask.sum(axis=1))
    overlap = _dilated_overlap(source_mask, rendered_mask)
    aspect = _aspect_score(source_mask, rendered_mask)
    score = 0.45 * overlap + 0.20 * vertical + 0.20 * horizontal + 0.15 * aspect
    reason = ""
    if strip_outer_latex_wrappers(latex) and not outer_wrapper_has_image_evidence(source, latex):
        # A model-generated outer pair adds two long edge strokes.  If the
        # source crop has no matching strokes, do not let a centered/bbox-only
        # comparison treat that wrapper as a good visual match.
        score *= 0.35
        reason = "外层定界符与原图边缘笔画不一致"
    return ValidationScore(round(max(0.0, min(1.0, score)), 6), True, reason)
