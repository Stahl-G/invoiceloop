"""The v2 qualification outcome is a deterministic artifact, not prose."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import qual_narrow_v2_decide as decision  # noqa: E402


def _all(*, docs: int = 200, zero: int = 0, wrong: int = 0,
         safety_wrong: int = 0, safety_absent: int = 0,
         unscored: int = 0, error_docs: int = 0) -> dict:
    return {
        "docs": docs,
        "zero_touch_docs": zero,
        "silent_wrong": wrong,
        "zero_touch_release_safety": {
            "zero_touch_docs": zero,
            "gating_slots": zero * 3,
            "silent_absent_true": safety_absent,
            "silent_wrong": safety_wrong,
            "unscored_auto_accept_slots": unscored,
            "docs_with_release_error": error_docs,
        },
    }


def _rescored(*, safety_wrong: int = 6, safety_absent: int = 0,
              unscored: int = 3, error_docs: int = 6,
              d_zero: int = 21) -> dict:
    return {"arms": {
        "HAR-0001": {"metrics": {"ALL": _all(zero=0, wrong=116)}},
        "HAR-0021": {"metrics": {"ALL": _all(zero=2, wrong=116)}},
        "HAR-0023": {"metrics": {"ALL": _all(
            zero=d_zero, wrong=113, safety_wrong=safety_wrong,
            safety_absent=safety_absent, unscored=unscored,
            error_docs=error_docs)}},
        "HAR-0021+payment(projection)": {"metrics": {"ALL": _all(
            zero=23, wrong=116)}},
    }}


def _routes(all_auto: int = 32) -> list[dict]:
    out = []
    for i in range(200):
        doc = f"d{i:03d}"
        for field in sorted(decision.GATING_FIELDS):
            out.append({"doc_id": doc, "field": field,
                        "route": "auto_accept" if i < all_auto else "review"})
    return out


def test_workflow_effect_can_pass_while_safety_qualification_fails():
    result = decision.evaluate(_rescored(), _routes())
    assert result["workflow_effect"]["passed"] is True
    assert result["workflow_effect"]["zero_touch_pct"] == 10.5
    assert result["safety_product_capability"]["passed"] is False
    assert result["qualification"] == {
        "passed": False,
        "status": "fail",
        "promotion": "denied",
        "reason_codes": ["zero_touch_silent_wrong_nonzero",
                         "zero_touch_unscored_auto_accept_nonzero"],
    }


def test_all_three_safety_criteria_must_be_zero():
    clean = decision.evaluate(
        _rescored(safety_wrong=0, safety_absent=0, unscored=0,
                  error_docs=0), _routes())
    assert clean["safety_product_capability"]["passed"] is True
    assert clean["qualification"]["passed"] is True

    for kwargs, reason in [
        ({"safety_absent": 1}, "zero_touch_silent_absent_true_nonzero"),
        ({"safety_wrong": 1}, "zero_touch_silent_wrong_nonzero"),
        ({"unscored": 1}, "zero_touch_unscored_auto_accept_nonzero"),
    ]:
        inputs = {"safety_wrong": 0, "safety_absent": 0,
                  "unscored": 0, "error_docs": 0}
        inputs.update(kwargs)
        failed = decision.evaluate(
            _rescored(**inputs), _routes())
        assert failed["qualification"]["passed"] is False
        assert reason in failed["qualification"]["reason_codes"]


def test_prediction_p5_is_reported_but_is_not_the_safety_threshold():
    result = decision.evaluate(_rescored(), _routes())
    assert result["predictions"]["P5"]["passed"] is False  # 6 is below 8
    assert result["predictions"]["P5"]["actual"] == {
        "silent_wrong": 6, "error_docs": 6,
    }
    assert result["safety_product_capability"]["criteria"]["silent_wrong"] == {
        "required": 0, "actual": 6, "passed": False,
    }


def test_three_gate_prediction_uses_all_three_routes_per_document():
    result = decision.evaluate(_rescored(), _routes(all_auto=32))
    assert result["predictions"]["P7"]["actual"]["pct"] == 16.0
    assert result["predictions"]["P7"]["passed"] is True
    assert len(result["three_gate_all_automatic_doc_ids"]) == 32


def test_workflow_gate_includes_structural_and_projection_checks():
    rescored = _rescored(d_zero=21)
    rescored["arms"]["HAR-0001"]["metrics"]["ALL"]["zero_touch_docs"] = 1
    result = decision.evaluate(rescored, _routes())
    assert result["predictions"]["P1"]["passed"] is False
    assert result["workflow_effect"]["passed"] is False
    assert result["qualification"]["reason_codes"][0] == \
        "workflow_effect_gate_failed"


def test_evidence_stage_rejects_tamper_and_undeclared_files(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    item = stage / "result.json"
    item.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(item.read_bytes()).hexdigest()
    (stage / "MANIFEST.sha256").write_text(
        f"{digest}  result.json\n", encoding="utf-8")
    assert decision.verify_stage(stage) == {"result.json": digest}

    item.write_text('{"changed":true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="哈希不符"):
        decision.verify_stage(stage)
    item.write_text("{}\n", encoding="utf-8")
    (stage / "undeclared.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="成员不闭合"):
        decision.verify_stage(stage)
