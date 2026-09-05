"""Convert OCR LaTeX to Word-friendly MathML without semantic rewriting."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

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
    if len(source) > 50000:
        raise MathMLConversionError("Formula is too long to preview")
    depth = 0
    for token in re.findall(r"\\(?:[a-zA-Z]+|.)|[{}]", source):
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth < 0:
                raise MathMLConversionError("Unbalanced LaTeX braces")
    if depth:
        raise MathMLConversionError("Unbalanced LaTeX braces")
    environments = []
    for command, name in re.findall(r"\\(begin|end)\s*\{([^}]+)\}", source):
        if command == "begin":
            environments.append(name)
        elif not environments or environments.pop() != name:
            raise MathMLConversionError("Unbalanced LaTeX environments")
    if environments:
        raise MathMLConversionError("Unbalanced LaTeX environments")
    # latex2mathml supports align* but not the equivalent unnumbered aligned
    # environment: the latter emits literal ampersands and no table. Translate
    # only the environment name for rendering, never the editable/raw formula.
    source = re.sub(r"(?<!\\)\\(begin|end)\s*\{aligned\}", lambda match: "\\" + match.group(1) + "{align*}", source)
    try:
        result = convert(source)
    except Exception as exc:  # library exceptions vary by unsupported command
        raise MathMLConversionError("This LaTeX formula cannot be rendered; the original remains editable") from exc
    if not result.lstrip().startswith("<math"):
        raise MathMLConversionError("LaTeX converter returned invalid MathML")
    try:
        root = ET.fromstring(result)
    except ET.ParseError as exc:
        raise MathMLConversionError("LaTeX converter returned invalid MathML") from exc
    allowed = set("math mrow mi mn mo mtext mspace ms msub msup msubsup mfrac msqrt mroot mstyle merror mpadded mphantom mfenced menclose munder mover munderover mmultiscripts mprescripts none mtable mtr mtd mlabeledtr maligngroup malignmark semantics annotation".split())
    visible = False
    def inspect(node, hidden=False):
        nonlocal visible
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in allowed or tag == "merror":
            raise MathMLConversionError("Unsupported formula content")
        if any(key.lower().startswith("on") or key.rsplit("}", 1)[-1].lower() in {"href", "src", "style"} for key in node.attrib):
            raise MathMLConversionError("External links and active content are not supported in formulas")
        hidden = hidden or tag in {"mphantom", "annotation"}
        if not hidden and tag in {"mi", "mn", "mo", "mtext", "ms"} and (node.text or "").strip():
            visible = True
        for child in node:
            inspect(child, hidden)
    inspect(root)
    if not visible:
        raise MathMLConversionError("The formula has no visible content (it may be hidden by phantom)")
    return result
