"""三方基线比较:raw DWS vs 双模式一致 vs InvoiceLoop 分诊(78 评 P1)。

回答 rubric 的核心问题:在同样的留出集上,把每个信号当作「自动放行规则」
时,静默错误 / 自动化覆盖 / 人工负载各是什么形状。

用法:
    python3 scripts/baseline_comparison.py runs/heldout runs/heldout-workspace

三个系统(全部从存盘证据零 API 重算):
    1. raw DWS         —— understand 返回什么就信什么(基线地板)
    2. 双模式一致       —— understand 与 agentic 归一化后相等才放行(最简单的
                         免费校验;DWS 不给字段级置信度,这就是「简单阈值」)
    3. InvoiceLoop     —— support_matrix 里 requires_adjudication=False 才放行

诚实声明(与表同屏,宪章六):
- 这是 2026-08-04 的**探索性**分析,不是预注册判据(H1–H6 才是);
- InvoiceLoop 产品本身从不自动放行 —— 人裁决。本表评估的是分诊信号在
  反事实自动放行下的质量,不是产品行为承诺;
- 偏差定义与 heldout_metrics.py / test_triage_concentration.py 完全同口径:
  真值存在、口径争议行剔除、无 understand 入账声明或归一化不等 = 偏差;
- 关键字段 = TIER1(搬自 dws-derisk routers.py,事前存在,不是看结果挑的)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from heldout_metrics import truth  # noqa: E402  (同一偏差口径,不复制)

from invoiceloop import dws  # noqa: E402
from invoiceloop.fields import FIELD_KINDS, TIER1, normalise  # noqa: E402
from invoiceloop.ocr import derisk_root  # noqa: E402


def score_slots(run_dir: Path) -> list[dict]:
    """与 heldout_metrics.measure 完全同口径的逐槽偏差标注。"""
    matrix = json.loads((Path(run_dir) / "support_matrix.json").read_text())
    scored = []
    for row in matrix["rows"]:
        if row["applicability"] == "label_convention_disputed":
            continue
        t = truth(row["doc_id"]).get(row["field"])
        if t is None:
            continue
        kind = FIELD_KINDS[row["field"]]
        want = normalise(t, kind)
        got = normalise(row["value"], kind) if row["claim_id"] else None
        scored.append({
            "doc_id": row["doc_id"], "field": row["field"],
            "tier1": row["field"] in TIER1,
            "deviation": not (got is not None and got == want),
            "invoiceloop_accept": not row["requires_adjudication"],
        })
    return scored


def add_crossmode(slots: list[dict], raw_dir: Path) -> None:
    """双模式一致基线:两模式都有值且归一化相等才放行(同 paired.agree 口径,
    但「双缺=一致」在放行语境下不成立 —— 没值不能算有支持)。"""
    cache: dict[tuple[str, str], dict] = {}

    def data(doc_id: str, mode: str) -> dict:
        key = (doc_id, mode)
        if key not in cache:
            path = raw_dir / f"{doc_id}.{mode}.json"
            try:
                rec = json.loads(path.read_text())
                body = rec.get("body") or {}
                cache[key] = (body.get("output") or {}).get("data") or {}
            except (OSError, json.JSONDecodeError, AttributeError):
                cache[key] = {}
        return cache[key]

    for slot in slots:
        doc, field = slot["doc_id"], slot["field"]
        kind = FIELD_KINDS[field]
        u = normalise(data(doc, "understand").get(field), kind)
        a = normalise(data(doc, "agentic").get(field), kind)
        slot["crossmode_accept"] = u is not None and u == a


def summarise(slots: list[dict], accept_key: str) -> dict[str, float]:
    """一个「自动放行规则」的四个 rubric 指标 + 文档级静默失败。"""
    n = len(slots)
    dev = sum(s["deviation"] for s in slots)
    accepted = [s for s in slots if s[accept_key]]
    silent = sum(s["deviation"] for s in accepted)
    docs: dict[str, list[dict]] = {}
    for s in slots:
        docs.setdefault(s["doc_id"], []).append(s)
    released = {d: ss for d, ss in docs.items()
                if all(s[accept_key] for s in ss)}
    doc_silent = sum(1 for ss in released.values() if any(s["deviation"] for s in ss))
    return {
        "slots": n,
        "deviations": dev,
        "accepted": len(accepted),
        "automation_coverage": len(accepted) / max(n, 1),
        "field_silent_error_rate": silent / max(len(accepted), 1),
        "review_load": 1 - len(accepted) / max(n, 1),
        "routing_recall": (dev - silent) / max(dev, 1),
        "docs": len(docs),
        "docs_released": len(released),
        "doc_silent_failure_rate": doc_silent / max(len(released), 1),
    }


SYSTEMS = (
    ("raw DWS(全信)", None),
    ("双模式一致", "crossmode_accept"),
    ("InvoiceLoop 分诊", "invoiceloop_accept"),
)


def table(slots: list[dict], title: str) -> str:
    lines = [
        f"### {title}",
        "",
        "| 系统 | 自动放行覆盖 | 字段静默错误率 | 文档静默失败率 | 复核负载 | 偏差路由召回 |",
        "|---|---|---|---|---|---|",
    ]
    for name, key in SYSTEMS:
        if key is None:  # raw DWS:全放行
            for s in slots:
                s["_raw_accept"] = True
            key = "_raw_accept"
        m = summarise(slots, key)
        lines.append(
            f"| {name} | {m['automation_coverage']:.1%} "
            f"({m['accepted']}/{m['slots']}) "
            f"| {m['field_silent_error_rate']:.2%} "
            f"| {m['doc_silent_failure_rate']:.1%} "
            f"({m['docs_released']}/{m['docs']} 整单放行) "
            f"| {m['review_load']:.1%} "
            f"| {m['routing_recall']:.1%} |"
        )
    return "\n".join(lines)


def main() -> None:
    run_dir = Path(sys.argv[1])
    raw_dir = Path(sys.argv[2]) / "raw"
    slots = score_slots(run_dir)
    add_crossmode(slots, raw_dir)

    tier1 = [s for s in slots if s["tier1"]]
    print(table(slots, f"全部记分字段({len(slots)} 槽)"))
    print()
    print(table(tier1, f"仅 TIER1 关键字段({len(tier1)} 槽,rubric critical fields)"))
    print()
    print("口径:探索性分析(2026-08-04),非预注册;偏差定义与 heldout_metrics 同;")
    print("InvoiceLoop 产品本身不自动放行,本表评估分诊信号的反事实质量。")


if __name__ == "__main__":
    main()
