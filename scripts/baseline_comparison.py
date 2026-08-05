"""四方基线比较(2026-08-05 重写:高级裁决三,各系统从自己的预测源打分)。

回答 rubric 的核心问题:在同样的留出集上,把每个信号当作「自动放行规则」
时,静默错误 / 自动化覆盖 / 人工负载各是什么形状。

用法:
    python3 scripts/baseline_comparison.py runs/heldout runs/heldout-workspace

五个系统(全部从存盘证据零 API 重算):
    1. raw DWS(全信)      —— understand 返回什么就信什么,缺值也照放(地板)
    2. raw DWS(有值才放行) —— understand 有非空值才放行,缺值进人工
    3. 置信度阈值          —— raw understand 值 + raw metadata confidence ≥0.95
    4. 双模式一致          —— raw understand 与 raw agentic 归一化相等且有值
    5. InvoiceLoop        —— 冻结 claim 入账值,requires_adjudication=False 放行

独立性纪律(高级裁决三):
- 1–4 的判定值全部来自 **raw 存盘响应**(output.data / output.metadata),
  不经过 InvoiceLoop 的冻结账本 —— 「有值」指 DWS 自己返回了值,
  不是「通过了 InvoiceLoop 绑定」;
- deviation 按系统各自的判定值独立计算,不共用一份;
- 槽宇宙 = 真值存在且非口径争议;争议判据(matrix.label_convention_disputed)
  只读 raw understand 数据本身,是全系统共享的输入属性;
- 置信度升序的平局用固定 (doc_id, field) tie-break,**不用 queue_idx**
  (矩阵行序是 InvoiceLoop 的分诊序,借它破平 = 借对方的排序);
  预算切入 confidence 同分组时加报 best/worst/expected。

诚实声明(与表同屏,宪章六):
- 探索性分析,不是预注册判据(H1–H6 才是);
- InvoiceLoop 产品本身从不自动放行 —— 人裁决。本表评估的是分诊信号在
  反事实自动放行下的质量,不是产品行为承诺;
- 关键字段 = TIER1(搬自 dws-derisk routers.py,事前存在,不是看结果挑的)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from heldout_metrics import truth  # noqa: E402  (同一真值口径,不复制)

from invoiceloop.eval_norm import eval_normalise as normalise  # noqa: E402
from invoiceloop.fields import FIELD_KINDS, TIER1  # noqa: E402
from invoiceloop.matrix import label_convention_disputed  # noqa: E402

#: 口径争议只影响这三个金额字段(§4)
_DISPUTE_FIELDS = ("total_net", "total_gross", "amount_due")


def _raw_payload(raw_dir: Path, doc_id: str, mode: str) -> dict:
    try:
        rec = json.loads((raw_dir / f"{doc_id}.{mode}.json").read_text())
        return (rec.get("body") or {}).get("output") or {}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def score_slots(run_dir: Path, raw_dir: Path) -> list[dict]:
    """逐槽打分:每个系统自己的值、自己的 deviation、自己的放行判据。"""
    run_dir = Path(run_dir)
    raw_dir = Path(raw_dir)
    matrix = json.loads((run_dir / "support_matrix.json").read_text())
    u_cache: dict[str, dict] = {}
    a_cache: dict[str, dict] = {}
    scored = []
    for row in matrix["rows"]:
        doc, field = row["doc_id"], row["field"]
        t = truth(doc).get(field)
        if t is None:
            continue
        if doc not in u_cache:
            u_cache[doc] = _raw_payload(raw_dir, doc, "understand")
            a_cache[doc] = _raw_payload(raw_dir, doc, "agentic")
        u_out, a_out = u_cache[doc], a_cache[doc]
        u_data = u_out.get("data") or {}
        # 口径争议:只看 raw understand 数据本身(共享输入属性)
        if field in _DISPUTE_FIELDS and label_convention_disputed(u_data):
            continue
        kind = FIELD_KINDS[field]
        want = normalise(t, kind)
        raw_v = normalise(u_data.get(field), kind)
        ag_v = normalise(a_out.get("data", {}).get(field)
                         if isinstance(a_out.get("data"), dict) else None, kind)
        meta = (u_out.get("metadata") or {}).get(field) or {}
        conf = meta.get("confidence")
        il_v = normalise(row["value"], kind) if row["claim_id"] else None
        scored.append({
            "doc_id": doc, "field": field,
            "tier1": field in TIER1,
            "queue_idx": len(scored),  # 矩阵行序 = InvoiceLoop 自己的分诊序
            # 各系统自己的判定值
            "raw_value": raw_v, "confidence": conf, "agentic_value": ag_v,
            "il_value": il_v,
            # 各系统自己的放行判据
            "raw_all_accept": True,
            "raw_nonnull_accept": raw_v is not None,
            "confidence_accept": (raw_v is not None and conf is not None
                                  and conf >= 0.95),
            "crossmode_accept": raw_v is not None and raw_v == ag_v,
            "invoiceloop_accept": not row["requires_adjudication"],
            # 各系统自己的偏差(缺值也算偏差 —— 真值在,系统没给到)
            "raw_deviation": raw_v is None or raw_v != want,
            "raw_wrong": raw_v is not None and raw_v != want,
            "il_deviation": il_v is None or il_v != want,
            "il_wrong": il_v is not None and il_v != want,
        })
    return scored


def summarise(slots: list[dict], accept_key: str, dev_key: str) -> dict:
    """一个「自动放行规则」的 rubric 指标,错值/缺值拆报(69 评 E4)。"""
    n = len(slots)
    wrong_key = dev_key.replace("_deviation", "_wrong")
    dev = sum(s[dev_key] for s in slots)
    accepted = [s for s in slots if s[accept_key]]
    silent = sum(s[dev_key] for s in accepted)
    silent_wrong = sum(s[wrong_key] for s in accepted)
    silent_missing = sum(1 for s in accepted
                         if s[dev_key] and not s[wrong_key])
    docs: dict[str, list[dict]] = {}
    for s in slots:
        docs.setdefault(s["doc_id"], []).append(s)
    released = {d: ss for d, ss in docs.items()
                if all(s[accept_key] for s in ss)}
    doc_silent = sum(1 for ss in released.values()
                     if any(s[dev_key] for s in ss))
    return {
        "slots": n,
        "deviations": dev,
        "accepted": len(accepted),
        "automation_coverage": len(accepted) / max(n, 1),
        "field_silent_error_rate": silent / max(len(accepted), 1),
        "silent_wrong_rate": silent_wrong / max(len(accepted), 1),
        "silent_missing_rate": silent_missing / max(len(accepted), 1),
        "review_load": 1 - len(accepted) / max(n, 1),
        "routing_recall": (dev - silent) / max(dev, 1),
        "docs": len(docs),
        "docs_released": len(released),
        "doc_silent_failure_rate": doc_silent / max(len(released), 1),
    }


SYSTEMS = (
    ("raw DWS(全信)", "raw_all_accept", "raw_deviation"),
    ("raw DWS(有值才放行)", "raw_nonnull_accept", "raw_deviation"),
    ("置信度阈值(≥0.95)", "confidence_accept", "raw_deviation"),
    ("双模式一致", "crossmode_accept", "raw_deviation"),
    ("InvoiceLoop 分诊", "invoiceloop_accept", "il_deviation"),
)


def table(slots: list[dict], title: str) -> str:
    lines = [
        f"### {title}",
        "",
        "| 系统 | 自动放行覆盖 | 字段静默错误率 | 其中错值 | 其中缺值放行 | 文档静默失败率 | 复核负载 | 偏差路由召回 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, accept_key, dev_key in SYSTEMS:
        m = summarise(slots, accept_key, dev_key)
        lines.append(
            f"| {name} | {m['automation_coverage']:.1%} "
            f"({m['accepted']}/{m['slots']}) "
            f"| {m['field_silent_error_rate']:.2%} "
            f"| {m['silent_wrong_rate']:.2%} "
            f"| {m['silent_missing_rate']:.2%} "
            f"| {m['doc_silent_failure_rate']:.1%} "
            f"({m['docs_released']}/{m['docs']} 整单放行) "
            f"| {m['review_load']:.1%} "
            f"| {m['routing_recall']:.1%} |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------- 同预算比较

def _ordered(slots: list[dict], key: str) -> list[dict]:
    if key == "confidence_accept":
        # 置信度升序(没把握的先看);缺 confidence = 最低,排最前;
        # 平局用固定 (doc_id, field) —— 不许用 queue_idx(高级裁决三:
        # 那是 InvoiceLoop 的分诊序,借它破平 = 借对方排序)
        return sorted(slots, key=lambda s: (
            s["confidence"] if s.get("confidence") is not None else -1.0,
            s["doc_id"], s["field"]))
    # invoiceloop_accept:矩阵行序本来就是分诊序,按 queue_idx 还原
    # (bootstrap 按文档重采样后必须重排,否则队列序被样本序打乱)
    return sorted(slots, key=lambda s: s["queue_idx"])


def _dev_key_for(order_key: str) -> str:
    return "il_deviation" if order_key == "invoiceloop_accept" \
        else "raw_deviation"


def recall_at_budget(slots: list[dict], key: str, budget: float) -> float:
    """复核前 budget 比例的槽,召回多少 TIER1 偏差(固定 tie-break 口径)。"""
    dev_key = _dev_key_for(key)
    total_dev = sum(s[dev_key] for s in slots)
    if not total_dev:
        return 0.0
    k = int(len(slots) * budget)
    reviewed = _ordered(slots, key)[:k]
    return sum(s[dev_key] for s in reviewed) / total_dev


def recall_tie_range(slots: list[dict], budget: float) -> dict:
    """confidence 升序在预算切入同分组时的 best/worst/expected(高级裁决三)。

    固定 tie-break 的点估计之外,报告「切进同 confidence 组」时的全范围:
    best = 组内偏差全被先看;worst = 组内偏差全被后看;expected = 均匀随机。
    """
    dev_key = "raw_deviation"
    total_dev = sum(s[dev_key] for s in slots)
    if not total_dev:
        return {"point": 0.0, "best": 0.0, "worst": 0.0, "expected": 0.0,
                "straddled": False}
    ordered = sorted(slots, key=lambda s: (
        s["confidence"] if s.get("confidence") is not None else -1.0,
        s["doc_id"], s["field"]))
    k = int(len(ordered) * budget)
    point = sum(s[dev_key] for s in ordered[:k]) / total_dev
    if k == 0 or k >= len(ordered):
        return {"point": point, "best": point, "worst": point,
                "expected": point, "straddled": False}
    boundary = (ordered[k - 1]["confidence"]
                if ordered[k - 1]["confidence"] is not None else -1.0)
    boundary_next = (ordered[k]["confidence"]
                     if ordered[k]["confidence"] is not None else -1.0)
    if boundary != boundary_next:
        return {"point": point, "best": point, "worst": point,
                "expected": point, "straddled": False}
    group = [s for s in ordered if (
        s["confidence"] if s["confidence"] is not None else -1.0) == boundary]
    before = [s for s in ordered if (
        s["confidence"] if s["confidence"] is not None else -1.0) < boundary]
    base_dev = sum(s[dev_key] for s in before)
    g_dev = sum(s[dev_key] for s in group)
    r = k - len(before)
    best = (base_dev + min(r, g_dev)) / total_dev
    worst = (base_dev + max(0, r - (len(group) - g_dev))) / total_dev
    expected = (base_dev + g_dev * r / len(group)) / total_dev
    return {"point": point, "best": best, "worst": worst,
            "expected": expected, "straddled": True}


def bootstrap_ci(slots: list[dict], key: str, budget: float,
                 *, n: int = 1000, seed: int = 42) -> tuple[float, float]:
    """按文档 bootstrap 的 95% CI(整份文档重采样,槽不独立 —— 同一发票的
    字段错误相关,按槽 bootstrap 会显著低估方差)。种子固定,可复算。"""
    import random

    docs: dict[str, list[dict]] = {}
    for s in slots:
        docs.setdefault(s["doc_id"], []).append(s)
    doc_ids = sorted(docs)
    rng = random.Random(seed)
    estimates = []
    for _ in range(n):
        sample = [s for d in (docs[rng.choice(doc_ids)] for _ in range(len(doc_ids)))
                  for s in d]
        estimates.append(recall_at_budget(sample, key, budget))
    estimates.sort()
    return estimates[int(n * 0.025)], estimates[int(n * 0.975)]


def budget_table(slots: list[dict]) -> str:
    budgets = (0.10, 0.20, 0.30, 0.40)
    lines = [
        "### 同人工预算比较(TIER1 偏差召回,前 b% 槽进人工)",
        "",
        "| 复核预算 | 置信度升序 | InvoiceLoop 分诊序 |",
        "|---|---|---|",
    ]
    for b in budgets:
        conf = recall_at_budget(slots, "confidence_accept", b)
        il = recall_at_budget(slots, "invoiceloop_accept", b)
        lines.append(f"| {b:.0%} | {conf:.1%} | {il:.1%} |")
    for b in budgets:
        tr = recall_tie_range(slots, b)
        if tr["straddled"]:
            lines.append(
                f"@{b:.0%} 预算切入 confidence 同分组:固定 tie-break "
                f"{tr['point']:.1%};同组内全范围 [{tr['worst']:.1%}, "
                f"{tr['best']:.1%}],均匀随机期望 {tr['expected']:.1%}")
    for name, key in (("置信度升序", "confidence_accept"),
                      ("InvoiceLoop 分诊序", "invoiceloop_accept")):
        lo, hi = bootstrap_ci(slots, key, 0.30)
        lines.append(f"@30% 预算 {name} 95% CI(按文档 bootstrap,n=1000):"
                     f" [{lo:.1%}, {hi:.1%}]")
    return "\n".join(lines)


def main() -> None:
    run_dir = Path(sys.argv[1])
    raw_dir = Path(sys.argv[2]) / "raw"
    slots = score_slots(run_dir, raw_dir)

    tier1 = [s for s in slots if s["tier1"]]
    print(table(slots, f"全部记分字段({len(slots)} 槽)"))
    print()
    print(table(tier1, f"仅 TIER1 关键字段({len(tier1)} 槽,rubric critical fields)"))
    print()
    print(budget_table(tier1))
    print()
    print("口径:探索性分析,非预注册;各系统从自己的预测源打分(raw 存盘响应 "
          "/ 冻结账本),deviation 不共用;置信度平局用固定 (doc_id, field) "
          "tie-break;InvoiceLoop 产品本身不自动放行,本表评估分诊信号的"
          "反事实质量。")


if __name__ == "__main__":
    main()
