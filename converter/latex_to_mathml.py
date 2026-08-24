"""Convert OCR LaTeX to Word-friendly MathML without semantic rewriting."""

from __future__ import annotations

import re

from latex2mathml.converter import convert


class MathMLConversionError(ValueError):
    """Raised when a LaTeX string cannot be converted to MathML."""


def _strip_math_delimiters(latex: str) -> str:
    text = latex.strip()
    for opening, closing in (("$$", "$$"), ("$", "$"), ("\\[", "\\]"), ("\\(", "\\)")):
        if text.startswith(opening) and text.endswith(closing) and len(text) >= len(opening) + len(closing):
            return text[len(opening) : -len(closing)].strip()
    return text


def _stabilize_single_glyph_mathrm(latex: str) -> str:
    r"""Work around ``latex2mathml`` dropping upright style on one glyph.

    ``latex2mathml`` currently converts ``\mathrm{HF}`` with
    ``mathvariant=normal`` but emits a plain italic ``<mi>`` for
    ``\mathrm{F}``.  The legacy TeX spelling ``{\rm F}`` is semantically
    equivalent and the converter handles it correctly.  This rewrite is used
    only for rendering; the OCR output and editable LaTeX remain unchanged.
    """

    return re.sub(
        r"\\mathrm\s*\{\s*([A-Za-z])\s*\}",
        lambda match: r"{\rm " + match.group(1) + "}",
        latex,
    )


def latex_to_mathml(latex: str) -> str:
    """Return MathML for OCR output, retaining the original expression's meaning."""
    if not isinstance(latex, str) or not latex.strip():
        raise MathMLConversionError("LaTeX input must be a non-empty string")
    source = _stabilize_single_glyph_mathrm(_strip_math_delimiters(latex))
    try:
        result = convert(source)
    except Exception as exc:  # library exceptions vary by unsupported command
        raise MathMLConversionError(f"Cannot convert LaTeX to MathML: {source}") from exc
    if not result.lstrip().startswith("<math"):
        raise MathMLConversionError("LaTeX converter returned invalid MathML")
    return result
