"""Regression tests for the local LaTeX-to-MathML preview path."""

from converter.latex_to_mathml import latex_to_mathml


def test_single_mathrm_letter_is_upright_without_changing_latex_contract() -> None:
    mathml = latex_to_mathml(r"3\mathrm{F}^{-}")
    assert '<mi mathvariant="normal">F</mi>' in mathml
    assert "<msup>" in mathml


def test_plain_single_letter_remains_a_math_variable() -> None:
    mathml = latex_to_mathml("F")
    assert "mathvariant=\"normal\"" not in mathml
    assert "<mi>F</mi>" in mathml


def test_compound_species_retains_nested_subscript_and_charge() -> None:
    mathml = latex_to_mathml(r"\mathrm{Nd(SO_{4})_{2}^{-}}")
    assert "<msub>" in mathml
    assert "<msubsup>" in mathml
    assert "_4" not in mathml
    assert "_2" not in mathml
