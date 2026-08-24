"""Conservative, chemistry-aware LaTeX formatting after OCR.

The postprocessor deliberately performs syntax-only rewrites.  It never
looks up elements, balances reactions, changes coefficients, or infers a
chemical species.  The model output remains available as ``raw_latex``.
"""

from __future__ import annotations

import re
from typing import Literal


RecognitionMode = Literal["chemistry", "math"]


_ARROW_REPLACEMENTS = (
    ("<=>", r"\rightleftharpoons"),
    ("<->", r"\leftrightarrow"),
    ("=>", r"\Rightarrow"),
    ("->", r"\rightarrow"),
    ("⇌", r"\rightleftharpoons"),
    ("⇄", r"\rightleftarrows"),
    ("↔", r"\leftrightarrow"),
    ("⟷", r"\longleftrightarrow"),
    ("→", r"\rightarrow"),
)

_COMMAND_BRACE_RE = re.compile(r"(\\[A-Za-z]+)\s+([\[{])")
_WHITESPACE_RE = re.compile(r"[\t\r\n ]+")
_FONT_COMMANDS = {"mathrm", "mathsf", "mathbf", "mathit", "mathbb", "mathcal", "operatorname"}


def _protect_text_commands(source: str) -> tuple[str, dict[str, str]]:
    """Temporarily protect ``\\text{...}`` payloads from formula rewrites."""

    protected: dict[str, str] = {}
    output: list[str] = []
    index = 0
    while index < len(source):
        match = re.match(r"\\text\s*\{", source[index:])
        if match is None:
            output.append(source[index])
            index += 1
            continue
        start = index
        body_start = index + match.end() - 1
        depth = 0
        cursor = body_start
        while cursor < len(source):
            if source[cursor] == "{" and (cursor == 0 or source[cursor - 1] != "\\"):
                depth += 1
            elif source[cursor] == "}" and (cursor == 0 or source[cursor - 1] != "\\"):
                depth -= 1
                if depth == 0:
                    cursor += 1
                    break
            cursor += 1
        if depth != 0:
            output.append(source[index])
            index += 1
            continue
        token = f"\x00TEXT{len(protected)}\x00"
        protected[token] = source[start:cursor]
        output.append(token)
        index = cursor
    return "".join(output), protected


def _format_scripts(source: str) -> str:
    """Brace unbraced one-token scripts without changing their contents."""

    output: list[str] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char not in "_^" or index + 1 >= len(source) or source[index + 1] == "{":
            output.append(char)
            index += 1
            continue

        start = index + 1
        if source[start] == "\\":
            match = re.match(r"\\[A-Za-z]+|\\.", source[start:])
            if match is None:
                output.append(char)
                index += 1
                continue
            token = match.group(0)
            output.append(f"{char}{{{token}}}")
            index = start + len(token)
            continue

        if char == "^":
            charge = re.match(r"(?:\d+[+-]|[+-])", source[start:])
            if charge is not None:
                token = charge.group(0)
            else:
                token = source[start]
        else:
            digits = re.match(r"\d+", source[start:])
            token = digits.group(0) if digits is not None else source[start]
        output.append(f"{char}{{{token}}}")
        index = start + len(token)
    return "".join(output)


def _balanced_group(source: str, start: int) -> tuple[str, int] | None:
    """Return a balanced brace group and its exclusive end position."""

    if start >= len(source) or source[start] != "{":
        return None
    depth = 0
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if char == "{" and not escaped:
            depth += 1
        elif char == "}" and not escaped:
            depth -= 1
            if depth == 0:
                return source[start + 1 : index], index + 1
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    return None


def _merge_empty_script_groups(source: str) -> str:
    """Repair the model's empty-script placeholder without guessing symbols.

    FormulaNet occasionally emits ``X_{}{sub}^{sup}`` when the subscript and
    superscript belong to the same base.  Only an immediately following,
    balanced group is merged; ordinary empty groups elsewhere are untouched.
    """

    output: list[str] = []
    index = 0
    while index < len(source):
        if source[index] in "_^" and index + 2 < len(source):
            script = source[index]
            brace_start = index + 1
            while brace_start < len(source) and source[brace_start].isspace():
                brace_start += 1
            group = _balanced_group(source, brace_start)
            if group is not None and not group[0].strip():
                cursor = group[1]
                while cursor < len(source) and source[cursor].isspace():
                    cursor += 1
                following = _balanced_group(source, cursor)
                if following is not None:
                    output.append(script + "{" + following[0] + "}")
                    index = following[1]
                    continue
            if group is not None:
                output.append(script + "{" + group[0].strip() + "}")
                index = group[1]
                continue
        output.append(source[index])
        index += 1
    return "".join(output)


def _top_level_script_start(body: str) -> int | None:
    """Find a script attached directly to a font group's base."""

    depth = 0
    escaped = False
    for index, char in enumerate(body):
        if char == "{" and not escaped:
            depth += 1
        elif char == "}" and not escaped and depth:
            depth -= 1
        elif char in "_^" and depth == 0:
            return index
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    return None


def _is_script_only_suffix(body: str, start: int) -> bool:
    r"""Return whether ``body[start:]`` contains only balanced scripts.

    A top-level underscore inside a compound term such as ``Nd(SO_{4})`` is
    not a script on the whole ``\mathrm`` group.  Treating the first such
    underscore as the group's boundary used to turn the valid expression
    ``\mathrm{Nd(SO_{4})_{2}^{-}}`` into the invalid-looking
    ``\mathrm{Nd(SO}_{4})_{2}^{-}``.  Lifting is safe only when every
    remaining token is an actual script attached to one simple base.
    """

    cursor = start
    found = False
    while cursor < len(body):
        while cursor < len(body) and body[cursor].isspace():
            cursor += 1
        if cursor >= len(body):
            break
        if body[cursor] not in "_^":
            return False
        found = True
        cursor += 1
        while cursor < len(body) and body[cursor].isspace():
            cursor += 1
        group = _balanced_group(body, cursor)
        if group is None:
            return False
        cursor = group[1]
    return found


def _lift_font_group_scripts(source: str) -> str:
    """Lift scripts out of a font group so one base gets a combined script.

    For example, ``\\mathrm{D_{Eu^{3+}}}`` becomes
    ``\\mathrm{D}_{Eu^{3+}}``.  This is a structural LaTeX rewrite only: the
    base and script payloads are copied byte-for-byte after recursive cleanup.
    """

    output: list[str] = []
    index = 0
    while index < len(source):
        if source[index] == "\\":
            command = re.match(r"\\([A-Za-z]+)", source[index:])
            if command is not None:
                name = command.group(1)
                end = index + len(command.group(0))
                if name in _FONT_COMMANDS:
                    cursor = end
                    while cursor < len(source) and source[cursor].isspace():
                        cursor += 1
                    group = _balanced_group(source, cursor)
                    if group is not None:
                        body = _lift_font_group_scripts(_merge_empty_script_groups(group[0]))
                        script_start = _top_level_script_start(body)
                        base = body[:script_start].strip() if script_start is not None else ""
                        simple_base = bool(
                            re.fullmatch(r"(?:[A-Za-z0-9]|\\[A-Za-z]+)+", base)
                        )
                        if (
                            script_start is not None
                            and simple_base
                            and _is_script_only_suffix(body, script_start)
                        ):
                            output.append(source[index:end] + "{" + body[:script_start] + "}")
                            output.append(body[script_start:])
                            index = group[1]
                            continue
                        output.append(source[index:end] + "{" + body + "}")
                        index = group[1]
                        continue
        output.append(source[index])
        index += 1
    return "".join(output)


def _compact_token_spacing(source: str) -> str:
    """Remove tokenizer whitespace without touching protected text payloads.

    FormulaNet commonly emits one space around every decoded token. Those
    spaces are harmless in a few LaTeX positions, but become destructive when
    they occur inside scripts (``_ { 2 }``) or inside a command argument. Text
    payloads are protected by ``_protect_text_commands`` before this function
    is called, so ordinary prose spacing remains intact.
    """

    # Keep the separator after a named command (``\rightarrow B``); joining
    # it would turn the command into the unrelated control sequence
    # ``\rightarrowB`` on a second normalization pass.
    source = re.sub(
        r"(\\[A-Za-z]+)\s+(?=[A-Za-z])",
        lambda match: f"{match.group(1)}\ue000",
        source,
    )
    source = re.sub(r"\{\s+", "{", source)
    source = re.sub(r"\s+\}", "}", source)
    source = re.sub(r"\s+([_^])", r"\1", source)
    source = re.sub(r"([([{])\s+", r"\1", source)
    source = re.sub(r"\s+([([])", r"\1", source)
    source = re.sub(r"\s+([)\]}])", r"\1", source)
    source = re.sub(r"\}\s+\{", "}{", source)
    # Join adjacent alphanumeric tokens (``A u C l`` -> ``AuCl``), while
    # retaining readable spaces around operators such as ``=`` and ``+``.
    previous = None
    while previous != source:
        previous = source
        source = re.sub(r"(?<=[A-Za-z0-9])\s+(?=[A-Za-z0-9])", "", source)
    return source.replace("\ue000", " ")


def _split_top_level(source: str) -> list[str]:
    """Split an expression at top-level ``=`` and ``+`` separators."""

    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(source):
        if char in "{[":
            depth += 1
        elif char in "}]" and depth:
            depth -= 1
        elif char in "=+" and depth == 0:
            parts.extend((source[start:index], char))
            start = index + 1
    parts.append(source[start:])
    return parts


def _format_reaction_chemistry(source: str) -> str:
    """Use upright glyphs for unambiguous chemical terms in equations.

    This deliberately activates only for an equation containing a top-level
    equals sign. A standalone ``x + y`` therefore remains ordinary
    mathematics, while ``3AuCl_2^- = 2Au...`` is rendered as chemistry.
    """

    parts = _split_top_level(source)
    if "=" not in parts:
        return source
    # A pre-existing upright chemical term is strong evidence that the whole
    # equality is chemical notation. It lets us safely format a remaining
    # single-element species such as ``3F^{-}`` without treating an ordinary
    # mathematical ``F=ma`` as chemistry.
    chemistry_context = "\\mathrm{" in source or "\\mathsf{" in source
    for index, part in enumerate(parts):
        if part in {"=", "+"}:
            parts[index] = f" {part} "
            continue
        stripped = part.strip()
        if not stripped or "\\mathrm{" in stripped or "\\mathsf{" in stripped:
            continue
        coefficient = re.match(r"\d+", stripped)
        prefix = coefficient.group(0) if coefficient else ""
        body = stripped[len(prefix) :]
        if re.search(r"[A-Z][a-z]", body):
            replacement = f"{prefix}\\mathrm{{{body}}}"
            parts[index] = part[: len(part) - len(part.lstrip())] + replacement
            continue
        if chemistry_context:
            species = re.fullmatch(
                r"((?:[A-Z][a-z]?)+)(\s*(?:(?:_\{[^{}]*\}|\^\{[^{}]*\})\s*)*)",
                body,
            )
            if species:
                replacement = (
                    f"{prefix}\\mathrm{{{species.group(1)}}}{species.group(2)}"
                )
                parts[index] = part[: len(part) - len(part.lstrip())] + replacement
    return "".join(parts)


def normalize_latex(latex: str, mode: RecognitionMode = "chemistry") -> str:
    """Return a formatting-only LaTeX form while preserving OCR meaning.

    The operation is intentionally idempotent.  Existing braced scripts and
    LaTeX arrow commands are kept intact; only unambiguous textual forms are
    canonicalized.
    """

    if not isinstance(latex, str):
        raise TypeError("LaTeX input must be a string")
    if mode not in {"chemistry", "math"}:
        raise ValueError(f"Unsupported recognition mode: {mode}")
    text = _WHITESPACE_RE.sub(" ", latex.strip())
    text, protected = _protect_text_commands(text)
    text = _compact_token_spacing(text)
    for source, replacement in _ARROW_REPLACEMENTS:
        text = text.replace(source, f" {replacement} ")
    text = _COMMAND_BRACE_RE.sub(r"\1\2", text)
    text = _merge_empty_script_groups(text)
    text = _format_scripts(text)
    text = _lift_font_group_scripts(text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if mode == "chemistry":
        text = _format_reaction_chemistry(text)
    text = _lift_font_group_scripts(text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    for token, original in protected.items():
        text = text.replace(token, original)
    return text
