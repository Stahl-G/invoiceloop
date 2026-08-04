"""三方基线比较(scripts/baseline_comparison.py)的度量数学钉死。

钉的是 summarise() 的指标定义,不是留出集数字(那是研究路径,
runs/heldout 不进仓库):
- automation_coverage / silent_error_rate / review_load / routing_recall
  的分母分子;
- 文档级「整单放行」与文档静默失败;
- 双模式一致基线:任一侧缺值都不许放行(「双缺=一致」在放行语境不成立)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from baseline_comparison import add_crossmode, summarise  # noqa: E402


def _slot(doc, field, deviation, il_accept):
    return {"doc_id": doc, "field": field, "tier1": True,
            "deviation": deviation, "invoiceloop_accept": il_accept}


SLOTS = [
    _slot("d1", "total_gross", False, True),    # 对,放行
    _slot("d1", "total_net", True, False),      # 错,拦下
    _slot("d2", "total_gross", True, True),     # 错,放行 = 静默错误
    _slot("d2", "total_net", False, True),      # 对,放行
]


class TestSummarise:
    def test_metric_math(self):
        m = summarise(SLOTS, "invoiceloop_accept")
        assert m["slots"] == 4 and m["deviations"] == 2
        assert m["accepted"] == 3
        assert m["automation_coverage"] == 0.75
        assert m["field_silent_error_rate"] == 1 / 3
        assert m["review_load"] == 0.25
        assert m["routing_recall"] == 0.5, "2 个偏差拦下 1 个"
        assert m["docs"] == 2 and m["docs_released"] == 1, \
            "d1 有槽被拦 → 整单不放行;d2 全放行"
        assert m["doc_silent_failure_rate"] == 1.0, \
            "d2 整单放行但含静默错误 —— 残余风险的诚实展示"

    def test_raw_accept_all_is_the_floor(self):
        for s in SLOTS:
            s["_raw"] = True
        m = summarise(SLOTS, "_raw")
        assert m["field_silent_error_rate"] == 0.5
        assert m["routing_recall"] == 0.0
        assert m["doc_silent_failure_rate"] == 1.0


class TestCrossmodeBaseline:
    def test_missing_on_either_side_is_not_accepted(self, tmp_path):
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "d1.understand.json").write_text(json.dumps(
            {"body": {"output": {"data": {"total_gross": "100.00"}}}}))
        (raw / "d1.agentic.json").write_text(json.dumps(
            {"body": {"output": {"data": {"total_gross": "100.00"}}}}))
        (raw / "d2.understand.json").write_text(json.dumps(
            {"body": {"output": {"data": {"total_gross": "100.00"}}}}))
        (raw / "d2.agentic.json").write_text(json.dumps(
            {"body": {"output": {"data": {}}}}))  # agentic 缺值

        slots = [_slot("d1", "total_gross", False, True),
                 _slot("d2", "total_gross", False, True)]
        add_crossmode(slots, raw)
        assert slots[0]["crossmode_accept"] is True
        assert slots[1]["crossmode_accept"] is False, \
            "一侧缺值不算一致 —— 没值不能算有支持"

    def test_disagreement_after_normalisation_is_not_accepted(self, tmp_path):
        raw = tmp_path / "raw"
        raw.mkdir()
        for mode, value in (("understand", "$1,000.00"), ("agentic", "1000.00")):
            (raw / f"d1.{mode}.json").write_text(json.dumps(
                {"body": {"output": {"data": {"total_gross": value}}}}))
        (raw / "d2.understand.json").write_text(json.dumps(
            {"body": {"output": {"data": {"total_gross": "100.00"}}}}))
        (raw / "d2.agentic.json").write_text(json.dumps(
            {"body": {"output": {"data": {"total_gross": "100.01"}}}}))

        slots = [_slot("d1", "total_gross", False, True),
                 _slot("d2", "total_gross", False, True)]
        add_crossmode(slots, raw)
        assert slots[0]["crossmode_accept"] is True, \
            "归一化后相等($1,000.00 ≡ 1000.00)= 一致"
        assert slots[1]["crossmode_accept"] is False
