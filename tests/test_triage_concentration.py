"""分诊集中度实测:我的支持强度排序,是否真把偏差集中到队首?

§7 那句"4.2× 集中度"是六轮校准的旧数字,投影是 R-D 路由;本矩阵的排序是另一个投影,
从未被验证过。这个测试把架构唯一的核心经验主张变成可证伪的:

**预注册协议(先于看结果写下,改它就是搬球门)**
1. 全部 160 份存盘文档跑完整 pipeline(含第六轮读图作答)。
2. 真值:DocILE annotations,字段映射搬 score.py::DOCILE_TO_FIELD。
3. 记分槽:真值存在的 (doc, field)。**口径争议行整行剔除,不计偏差(宪章五)。**
4. 偏差 = 该槽没有 understand 入账声明,或入账值按预注册规则规范化后 ≠ 真值
   (与 score.py 的 correct 定义对齐:缺预测 = 错)。
5. 通过线(刻意放弱 —— 架构只主张"排序优于随机",不主张任何一档可信):
   - lift = 记分队列前 50% 的偏差率 / 后 50% 的偏差率 > 1
   - 复核召回 = 落在 requires_adjudication 行里的偏差占比 > 0.5
   报告值(不设线):coverage@46%(校准的运行点是 78%)、lift 点估计。
6. 已知噪声:DocILE 标注本身有错(第四轮 14 例中 8 例),两侧均匀分布。

红了的含义:panel 上"分诊排序经实测 4.2×"必须改写成"校准如此,本投影未复现"。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoiceloop.fields import FIELD_KINDS, normalise
from invoiceloop.ocr import corpus_available, derisk_root
from invoiceloop.pipeline import run

pytestmark = pytest.mark.skipif(not corpus_available(), reason="存盘证据不在")

#: 搬 score.py::DOCILE_TO_FIELD(预注册映射,currency_code_amount_due 按 A-1 缺席)。
DOCILE_TO_FIELD = {
    "document_id": "invoice_number",
    "date_issue": "issue_date",
    "date_due": "due_date",
    "vendor_name": "seller_name",
    "vendor_tax_id": "seller_vat_id",
    "customer_billing_name": "buyer_name",
    "amount_total_net": "total_net",
    "amount_total_tax": "total_vat",
    "amount_total_gross": "total_gross",
    "amount_due": "amount_due",
}


def _truth(doc_id: str) -> dict[str, str]:
    path = derisk_root() / "data" / "docile" / "annotations" / f"{doc_id}.json"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for item in json.loads(path.read_text())["field_extractions"]:
        name = DOCILE_TO_FIELD.get(item.get("fieldtype"))
        if name and item.get("text"):
            out.setdefault(name, item["text"])
    return out


@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    from invoiceloop import dws

    out = tmp_path_factory.mktemp("triage") / "run"
    run(dws.stored_docs(), out, render_crops=False, include_vision=True)
    return json.loads((out / "support_matrix.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scored_rows(full_run):
    """矩阵顺序不变的记分行(真值存在、口径争议剔除),每行附上偏差标记。"""
    rows = []
    for row in full_run["rows"]:
        if row["applicability"] == "label_convention_disputed":
            continue
        truth = _truth(row["doc_id"]).get(row["field"])
        if truth is None:
            continue
        kind = FIELD_KINDS[row["field"]]
        want = normalise(truth, kind)
        got = normalise(row["value"], kind) if row["claim_id"] else None
        rows.append({**row, "deviation": not (got is not None and got == want)})
    return rows


class TestTriageConcentration:
    def test_enough_evidence_to_mean_anything(self, scored_rows):
        n = sum(r["deviation"] for r in scored_rows)
        assert len(scored_rows) > 800, "记分槽太少,测不出集中度"
        assert n > 20, "偏差太少,lift 无意义"

    def test_ordering_beats_random(self, scored_rows):
        """预注册通过线:lift > 1。报告值打印在测试输出里。"""
        half = len(scored_rows) // 2
        front, back = scored_rows[:half], scored_rows[half:]
        rate_f = sum(r["deviation"] for r in front) / len(front)
        rate_b = sum(r["deviation"] for r in back) / len(back)
        lift = rate_f / rate_b if rate_b else float("inf")
        k46 = int(len(scored_rows) * 0.46)
        cov46 = (sum(r["deviation"] for r in scored_rows[:k46])
                 / max(sum(r["deviation"] for r in scored_rows), 1))
        adjudicated = sum(r["deviation"] for r in scored_rows if r["requires_adjudication"])
        total_dev = sum(r["deviation"] for r in scored_rows)
        print(f"\n  记分槽 {len(scored_rows)},偏差 {total_dev}")
        print(f"  前半偏差率 {rate_f:.1%} vs 后半 {rate_b:.1%} → lift {lift:.2f}×")
        print(f"  coverage@46% {cov46:.1%}(校准运行点 78%)")
        print(f"  复核召回 {adjudicated}/{total_dev} = {adjudicated / total_dev:.1%}")
        assert lift > 1, (
            f"排序不比随机关心偏差:lift {lift:.2f}。"
            f"panel 的 4.2× 必须改写为「校准如此,本投影未复现」"
        )

    def test_adjudication_queue_catches_majority(self, scored_rows):
        """预注册通过线:requires_adjudication 行盖住过半偏差。"""
        total_dev = sum(r["deviation"] for r in scored_rows)
        caught = sum(r["deviation"] for r in scored_rows if r["requires_adjudication"])
        assert caught / total_dev > 0.5, (
            f"复核队列漏了 {(1 - caught / total_dev):.0%} 的偏差 —— "
            f"「按设计要人看」这条守不住"
        )
