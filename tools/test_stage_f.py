"""Stage F regression checks for conservative LaTeX formatting."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ocr import OCRResult, normalize_latex
from ocr.visual_case import apply_visual_case_evidence


def check(name: str, source: str, expected: str) -> None:
    actual = normalize_latex(source)
    assert actual == expected, (name, actual, expected)
    assert normalize_latex(actual) == actual, name
    print(f"{name}: PASS")


def main() -> None:
    check("element subscripts", r"H_2O + SO_4", r"H_{2}O + SO_{4}")
    check("charge superscripts", r"Fe^3+ + Cl^-", r"Fe^{3+} + Cl^{-}")
    check("command spacing", r"\mathrm {NaCl_2}", r"\mathrm{NaCl}_{2}")
    check("reaction arrows", r"A -> B <-> C => D", r"A \rightarrow B \leftrightarrow C \Rightarrow D")
    check("unicode arrows", "A ⇌ B ↔ C → D", r"A \rightleftharpoons B \leftrightarrow C \rightarrow D")
    check("reaction condition spacing", r"A \xrightarrow {heat} B", r"A \xrightarrow{heat} B")
    check("text payload preserved", r"\text{A -> B and x^2}", r"\text{A -> B and x^2}")
    check("existing structure", r"\mathrm{ThO_{2}+2H^{+}\leftrightarrow Th(OH)_{2}^{2+}}", r"\mathrm{ThO_{2}+2H^{+}\leftrightarrow Th(OH)_{2}^{2+}}")
    check(
        "upright single element in chemical equation",
        r"\mathrm{NdF}_{3} + \mathrm{Cl}^{-} = \mathrm{NdCl}^{2+} + 3F^{-}",
        r"\mathrm{NdF}_{3} + \mathrm{Cl}^{-} = \mathrm{NdCl}^{2+} + 3\mathrm{F}^{-}",
    )
    check(
        "upright multi-element species in chemical equation",
        r"\mathrm{NdF}_{3} + 2HSO_{4}^{-} + H^{+} = \mathrm{Nd(SO}_{4})_{2}^{-} + 3HF^{\circ}",
        r"\mathrm{NdF}_{3} + 2\mathrm{HSO}_{4}^{-} + \mathrm{H}^{+} = \mathrm{Nd(SO}_{4})_{2}^{-} + 3\mathrm{HF}^{\circ}",
    )
    check(
        "compound upright group keeps nested scripts",
        r"\mathrm{Nd(SO_{4})_{2}^{-}}",
        r"\mathrm{Nd(SO_{4})_{2}^{-}}",
    )
    check(
        "history acid reaction preserves compound group",
        r"\mathrm{NdF_{3}} + 2\mathrm{HSO_{4}^{-}} + \mathrm{H^{+}} = \mathrm{Nd(SO_{4})_{2}^{-}} + 3\mathrm{HF^{\circ}}",
        r"\mathrm{NdF}_{3} + 2\mathrm{HSO}_{4}^{-} + \mathrm{H}^{+} = \mathrm{Nd(SO_{4})_{2}^{-}} + 3\mathrm{HF}^{\circ}",
    )
    check(
        "tokenized chemical reaction",
        r"3 A u C l _ { 2 } ^ { - } = 2 A u ( S ) + A u C l _ { 4 } ^ { - } + 2 C l ^ { - }",
        r"3\mathrm{AuCl}_{2}^{-} = 2\mathrm{Au(S)} + \mathrm{AuCl}_{4}^{-} + 2\mathrm{Cl}^{-}",
    )
    check("tokenized upright text", r"\mathsf { F o r m u l a O C R }", r"\mathsf{FormulaOCR}")
    check(
        "combined scripts after empty placeholder",
        r"2 \mathsf{Ca}_{ }{\mathrm{Mineral}}^{2 +}",
        r"2 \mathsf{Ca}_{\mathrm{Mineral}}^{2 +}",
    )
    check(
        "font-group scripts lifted",
        r"\mathrm{D_{Eu^{3+}}}^{Mineral/Fluid}",
        r"\mathrm{D}_{Eu^{3+}}^{Mineral/Fluid}",
    )
    check(
        "nested activity script",
        r"a_{}{\left[\mathrm{Eu}^{3+}(\mathrm{OH})_{4}\right]^{-}}",
        r"a_{\left[\mathrm{Eu}^{3+}(\mathrm{OH})_{4}\right]^{-}}",
    )

    raw_case = r"3 A u C l _ { 2 } ^ { - } = 2 A u ( S ) + A u C l _ { 4 } ^ { - }"
    refined_case = apply_visual_case_evidence(
        raw_case,
        "3AuCl½ = 2Au(s) + AuClá",
    )
    assert "A u ( s )" in refined_case
    assert apply_visual_case_evidence(raw_case, "2Au(S)") == raw_case
    assert apply_visual_case_evidence(raw_case, "2Au(l)") == raw_case
    case_result = OCRResult(raw_case, None, 1.0, refined_case)
    assert r"\mathrm{Au(s)}" in case_result.formatted_latex
    assert case_result.raw_latex == raw_case
    print("image-evidenced lowercase phase: PASS")

    raw = r"2H_2 + O_2 -> 2H_2O"
    result = OCRResult(raw, None, 1.0)
    assert result.raw_latex == raw
    assert result.formatted_latex == r"2H_{2} + O_{2} \rightarrow 2H_{2}O"
    print("raw result preserved: PASS")

    source = r"\mathrm{NdF}_{3} + \mathrm{Cl}^{-} = \mathrm{NdCl}^{2+} + 3F^{-}"
    chemistry = normalize_latex(source, mode="chemistry")
    mathematics = normalize_latex(source, mode="math")
    assert r"3\mathrm{F}^{-}" in chemistry
    assert r"3F^{-}" in mathematics
    for marker in (r"^{-}", r"^{2+}"):
        assert chemistry.count(marker) == source.count(marker)
        assert mathematics.count(marker) == source.count(marker)
    assert OCRResult(source, None, 1.0).format_for("math") == mathematics
    print("chemistry/math mode preserves charges: PASS")

    cli = subprocess.run(
        [sys.executable, "main.py", "tests/samples/2026-08-08_02-32-28.png", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(cli.stdout)
    assert payload["raw_latex"]
    assert payload["latex"]
    print("CLI raw/formatted fields: PASS")


if __name__ == "__main__":
    main()
