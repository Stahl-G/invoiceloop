"""gateinfo:悬停说明的完整性与回退。"""

from invoiceloop.gateinfo import _INFO, tooltip

GATES = ("arithmetic_consistency", "field_wellformed", "extraction_present",
         "citation_holds", "cross_mode_agreement", "visual_corroboration")


def test_every_gate_has_both_languages_and_an_intro():
    for gate in GATES:
        for lang in ("en", "zh"):
            assert _INFO[lang][gate]["intro"], f"{gate}/{lang} 缺简介"
            assert tooltip(gate, "pass", lang) != gate


def test_unknown_gate_falls_back_to_id():
    assert tooltip("future_gate", "pass", "zh") == "future_gate"


def test_unknown_verdict_falls_back_to_unavailable_text():
    text = tooltip("citation_holds", "weird-verdict", "zh")
    assert "无法机检" in text
