"""Image-evidenced case refinement for ambiguous parenthesized text."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .backend_types import ImageInput


_PAREN_LETTERS_RE = re.compile(r"\(\s*([A-Za-z](?:\s*[A-Za-z])*)\s*\)")


def _letters(value: str) -> str:
    return re.sub(r"\s+", "", value)


def apply_visual_case_evidence(latex: str, visual_text: str) -> str:
    """Apply only case changes supported by aligned parenthesized image text.

    Formula structure always comes from FormulaNet. The secondary recognizer
    may contribute letter case only when every parenthesized alphabetic group
    aligns case-insensitively and in order. Any missing or conflicting group
    leaves the FormulaNet output untouched.
    """

    raw_matches = list(_PAREN_LETTERS_RE.finditer(latex))
    visual_matches = list(_PAREN_LETTERS_RE.finditer(visual_text))
    if not raw_matches or len(raw_matches) != len(visual_matches):
        return latex

    raw_groups = [_letters(match.group(1)) for match in raw_matches]
    visual_groups = [_letters(match.group(1)) for match in visual_matches]
    if [value.casefold() for value in raw_groups] != [
        value.casefold() for value in visual_groups
    ]:
        return latex

    output: list[str] = []
    start = 0
    changed = False
    for match, raw_group, visual_group in zip(
        raw_matches, raw_groups, visual_groups, strict=True
    ):
        output.append(latex[start : match.start(1)])
        # This corrects the reported failure direction (s decoded as S) while
        # never promoting lowercase FormulaNet output to uppercase solely on
        # secondary OCR evidence.
        replacement = "".join(
            visual if raw.isupper() and visual.islower() else raw
            for raw, visual in zip(raw_group, visual_group, strict=True)
        )
        output.append(replacement)
        changed |= replacement != raw_group
        start = match.end(1)
    output.append(latex[start:])
    return "".join(output) if changed else latex


def _recognize_visual_text(image_path: Path) -> str | None:
    if sys.platform != "darwin" or not image_path.is_file():
        return None
    try:
        import Foundation
        import Vision

        image_url = Foundation.NSURL.fileURLWithPath_(str(image_path))
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
            image_url,
            {},
        )
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setRecognitionLanguages_(["en-US"])
        request.setUsesLanguageCorrection_(False)
        succeeded, _error = handler.performRequests_error_([request], None)
    except Exception:
        return None
    if not succeeded:
        return None

    lines: list[str] = []
    for observation in request.results() or []:
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        if float(candidate.confidence()) >= 0.8:
            recognized = str(candidate.string())
            if recognized:
                lines.append(recognized)
    return " ".join(lines) or None


def refine_latex_case(latex: str, image: ImageInput) -> str | None:
    """Return image-evidenced LaTeX, or ``None`` when no safe change exists."""

    if not isinstance(image, (str, Path)) or not _PAREN_LETTERS_RE.search(latex):
        return None
    visual_text = _recognize_visual_text(Path(image))
    if visual_text is None:
        return None
    refined = apply_visual_case_evidence(latex, visual_text)
    return refined if refined != latex else None
