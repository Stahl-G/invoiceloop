"""四方基线比较(scripts/baseline_comparison.py)的度量数学钉死。

钉的是指标定义与各系统独立打分,不是留出集数字(研究路径,runs/heldout
不进仓库):
- summarise() 的分母分子 + 错值/缺值拆报;
- 文档级「整单放行」与文档静默失败;
- 各系统从自己的预测源取值(raw 响应 vs 冻结账本),deviation 不共用;
- 置信度平局用固定 (doc_id, field) tie-break,不用 queue_idx;
- 预算切入同 confidence 组时的 best/worst/expected。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from baseline_comparison import (recall_at_budget, recall_tie_range,  # noqa: E402
                                 score_slots, summarise)


def _slot(doc, field, *, raw_value, il_value, conf=None, ag="same",
          il_accept=True, idx=0):
    """raw/il 两侧的判定值分开给 —— 各系统偏差独立计算。"""
    raw_dev = raw_value != "WANT"
    il_dev = il_value != "WANT"
    return {
        "doc_id": doc, "field": field, "tier1": True, "queue_idx": idx,
        "raw_value": raw_value, "confidence": conf,
        "agentic_value": raw_value if ag == "same" else "OTHER",
        "il_value": il_value,
        "raw_all_accept": True,
        "raw_nonnull_accept": raw_value is not None,
        "confidence_accept": (raw_value is not None and conf is not None
                              and conf >= 0.95),
        "crossmode_accept": raw_value is not None and ag == "same",
        "invoiceloop_accept": il_accept,
        "raw_deviation": raw_dev, "raw_wrong": raw_value is not None and raw_dev,
        "il_deviation": il_dev, "il_wrong": il_value is not None and il_dev,
    }


class TestSummarise:
    SLOTS = [
        _slot("d1", "total_gross", raw_value="WANT", il_value="WANT"),
        _slot("d1", "total_net", raw_value="BAD", il_value="BAD",
              il_accept=False),
        _slot("d2", "total_gross", raw_value="BAD", il_value="BAD"),
        _slot("d2", "total_net", raw_value="WANT", il_value="WANT"),
    ]

    def test_metric_math(self):
        m = summarise(self.SLOTS, "invoiceloop_accept", "il_deviation")
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
        m = summarise(self.SLOTS, "raw_all_accept", "raw_deviation")
        assert m["field_silent_error_rate"] == 0.5
        assert m["routing_recall"] == 0.0
        assert m["doc_silent_failure_rate"] == 1.0

    def test_wrong_missing_split(self):
        """错值与缺值拆报:raw 全信口径把缺值也放进交付,占静默错误的一份;
        有值才放行口径把缺值赶进人工,静默错误率下降但复核负载上升。"""
        slots = [
            _slot("d1", "total_gross", raw_value="WANT", il_value="WANT"),
            _slot("d1", "total_net", raw_value="BAD", il_value="BAD"),
            _slot("d2", "total_gross", raw_value=None, il_value=None),
        ]
        m_all = summarise(slots, "raw_all_accept", "raw_deviation")
        assert m_all["field_silent_error_rate"] == 2 / 3
        assert m_all["silent_wrong_rate"] == 1 / 3
        assert m_all["silent_missing_rate"] == 1 / 3, "缺值照放是 raw 全信的静默错误"
        m_nn = summarise(slots, "raw_nonnull_accept", "raw_deviation")
        assert m_nn["field_silent_error_rate"] == 0.5
        assert m_nn["silent_missing_rate"] == 0.0, "缺值进人工,不再算静默放行"
        assert m_nn["review_load"] == pytest.approx(1 / 3)


class TestIndependentScoring:
    def test_raw_value_ignores_freeze_outcome(self, tmp_path):
        """高级裁决三的核心:DWS 返回了错误非空值但被冻结拒绝的槽,
        raw-nonnull 口径必须仍算「DWS 有值」—— raw 系不借 InvoiceLoop
        的冻结结果。构造:raw 有值 BAD;矩阵行无 claim(冻结拒了)。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        raw = tmp_path / "raw"
        raw.mkdir()
        doc = "d1"
        (raw / f"{doc}.understand.json").write_text(json.dumps(
            {"body": {"output": {"data": {"total_gross": "999.00"},
                                 "metadata": {"total_gross": {"confidence": 0.95}}}}}))
        (raw / f"{doc}.agentic.json").write_text(json.dumps(
            {"body": {"output": {"data": {"total_gross": "999.00"}}}}))
        (run_dir / "support_matrix.json").write_text(json.dumps({"rows": [{
            "doc_id": doc, "field": "total_gross", "value": None,
            "claim_id": None,  # 冻结拒绝 → InvoiceLoop 无值
            "requires_adjudication": True}]}))

        import heldout_metrics
        original_truth = heldout_metrics.truth
        heldout_metrics.truth = lambda d: {"total_gross": "100.00"}
        import baseline_comparison
        baseline_comparison.truth = lambda d: {"total_gross": "100.00"}
        try:
            slots = score_slots(run_dir, raw)
        finally:
            heldout_metrics.truth = original_truth
            baseline_comparison.truth = original_truth
        (s,) = slots
        assert s["raw_value"] is not None, "raw 的值来自 raw 响应,不是冻结结果"
        assert s["raw_nonnull_accept"] is True, \
            "DWS 有值(哪怕错、哪怕被冻结拒)raw-nonnull 就放行"
        assert s["raw_deviation"] is True
        assert s["il_value"] is None and s["il_deviation"] is True
        assert s["invoiceloop_accept"] is False


class TestConfidenceTieBreak:
    def test_tie_broken_by_doc_field_not_queue(self):
        """同 confidence 的平局用 (doc_id, field) 固定破 —— 与 queue_idx
        (InvoiceLoop 分诊序)无关。"""
        slots = [
            _slot("b2", "total_net", raw_value="BAD", il_value="BAD",
                  conf=0.95, idx=0),
            _slot("a1", "total_gross", raw_value="WANT", il_value="WANT",
                  conf=0.95, idx=1),
            _slot("c3", "total_vat", raw_value="WANT", il_value="WANT",
                  conf=0.40, idx=2),
        ]
        # budget 75% → 3 槽里看 2 个:0.40 先看,然后平局里 a1 在 b2 前
        # (按 doc_id 字母序,与 queue_idx 相反)
        r = recall_at_budget(slots, "confidence_accept", 0.67)
        assert r == 0.0, "前 2 槽(0.40 档 + 平局中的 a1)都不含偏差"
        r = recall_at_budget(slots, "confidence_accept", 1.0)
        assert r == 1.0

    def test_tie_range_reports_span_when_straddled(self):
        slots = [
            _slot("d1", "f1", raw_value="WANT", il_value="WANT", conf=0.40),
            _slot("d2", "f2", raw_value="BAD", il_value="BAD", conf=0.95),
            _slot("d3", "f3", raw_value="WANT", il_value="WANT", conf=0.95),
            _slot("d4", "f4", raw_value="WANT", il_value="WANT", conf=0.95),
        ]
        tr = recall_tie_range(slots, 0.5)  # 看 2 槽:0.40 + 切入 0.95 同分组
        assert tr["straddled"] is True
        assert tr["best"] == 1.0, "同分组内偏差先看 = 全召回"
        assert tr["worst"] == 0.0, "同分组内偏差后看 = 零召回"
        assert 0.0 < tr["expected"] < 1.0
        tr2 = recall_tie_range(slots, 0.25)  # 正好切在组边界
        assert tr2["straddled"] is False
        assert tr2["point"] == tr2["best"] == tr2["worst"]
