#!/usr/bin/env python3
"""S1 四臂准确率对比(docs/HITL_R1_AMENDMENT_STAGED_2026-08-11.md 的 dev 集)。

臂:
- dws-u / dws-a   DWS 存盘原始值(两模式),全 200 槽
- kimi            LLM 直接读图(S1 agent 预读,tag kimi),仅 92 队列槽
- pipeline-auto   DWS + InvoiceLoop 自动层(auto_accept/auto_absent),108 槽
- stahl-*         人工臂(账本),数据够才算

打分:与 SEALED-4 同函数(safety_metrics.truth + eval_norm.eval_normalise,
预注册六轮冻结)。真值非空的槽计准确率;真值缺席的槽单列"缺席判对率"。
只读,不写 runs/。
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop.eval_norm import eval_normalise  # noqa: E402
from invoiceloop.fields import FIELD_KINDS  # noqa: E402
from invoiceloop.safety_metrics import truth  # noqa: E402


def _raw_values(ws: Path, doc_id: str, mode: str) -> dict[str, str | None]:
    path = ws / "raw" / f"{doc_id}.{mode}.json"
    if not path.is_file():
        return {}
    data = (json.loads(path.read_text()).get("body") or {}).get("output", {})
    return {f: v for f, v in (data.get("data") or {}).items() if f in FIELD_KINDS}


def _norm(value, field: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    return eval_normalise(value, FIELD_KINDS[field])


def score_arm(slots: list[tuple[str, str]],
              pred_of) -> dict:
    """slots=[(doc, field)];pred_of(doc)->{field: value|None}。

    四个桶,全部可机检:
    - 真值非空 + 精确匹配 → correct
    - 真值非空 + 预测为空(miss)→ 用**冻结**的 T1/T2 规则拆:
      口径争议(truth_caliber.caliber_dispute,增补件 A3)vs 真漏
    - 真值非空 + 值不匹配 → mismatch(不自动分类!广播发票的
      「广告主 vs 代理」「gross vs net」这类值侧口径争议没有冻结规则,
      看结果后新造规则 = 拟合(truth_caliber docstring 原话)。
      全量 dump 出来人工判读,不进自动口径)
    - 真值缺席 → 预测空 = 判对;预测非空 = false_presence(同样只 dump)
    """
    scored = correct = 0
    true_miss = dispute = 0
    absent = absent_correct = 0
    mismatches: list[dict] = []
    false_presence: list[dict] = []
    by_field: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for doc, field in slots:
        tmap = truth(doc)
        t = tmap.get(field)
        got = _norm((pred_of(doc) or {}).get(field), field)
        if t is not None:
            scored += 1
            if got is None:
                # 预测缺席,真值非空:冻结拆分器管的就是这一格
                from invoiceloop.truth_caliber import caliber_dispute
                if caliber_dispute(doc, field, tmap):
                    dispute += 1
                else:
                    true_miss += 1
                by_field[field][0] += 1
                continue
            ok = got == _norm(t, field)
            correct += ok
            by_field[field][0] += 1
            by_field[field][1] += ok
            if not ok:
                mismatches.append({
                    "doc_id": doc, "field": field,
                    "predicted": str((pred_of(doc) or {}).get(field)),
                    "truth": t})
        else:
            absent += 1
            if got is None:
                absent_correct += 1
            else:
                false_presence.append({
                    "doc_id": doc, "field": field,
                    "predicted": str((pred_of(doc) or {}).get(field))})
    return {
        "slots": len(slots), "truth_present": scored, "correct": correct,
        "accuracy": round(correct / scored, 4) if scored else None,
        # 口径宽免后准确率:correct + T1/T2 冻结规则认定的口径争议。
        # 只宽免缺席轴;值侧 mismatch 无冻结规则,一个都不宽免。
        "accuracy_caliber_adjusted":
            round((correct + dispute) / scored, 4) if scored else None,
        "miss_true": true_miss, "miss_caliber_dispute": dispute,
        "mismatches": mismatches,
        "truth_absent": absent, "absent_correct": absent_correct,
        "absent_accuracy": round(absent_correct / absent, 4) if absent else None,
        "false_presence": false_presence,
        "by_field": {f: {"n": n, "correct": c,
                         "accuracy": round(c / n, 4) if n else None}
                     for f, (n, c) in sorted(by_field.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--kimi-rows", type=Path,
                    default=Path("/tmp/hitl-r1-s1-preread/kimi_rows.json"))
    args = ap.parse_args()
    run_dir = args.run_dir
    ws = run_dir.parent.parent

    sm = json.loads((run_dir / "support_matrix.json").read_text())
    queue = [(r["doc_id"], r["field"]) for r in sm["rows"] if r["in_human_queue"]]
    auto = [(r["doc_id"], r["field"]) for r in sm["rows"]
            if r["route"] in ("auto_accept", "auto_absent")]
    allslots = queue + auto

    auto_pred: dict[str, dict] = collections.defaultdict(dict)
    for r in sm["rows"]:
        if r["route"] in ("auto_accept", "auto_absent"):
            auto_pred[r["doc_id"]][r["field"]] = r["value"]

    kimi_pred: dict[str, dict] = collections.defaultdict(dict)
    if args.kimi_rows.is_file():
        for row in json.loads(args.kimi_rows.read_text()):
            kimi_pred[row["doc_id"]][row["field"]] = row["value"] or None

    ledger_path = run_dir / "adjudication_ledger.jsonl"
    ledger = [json.loads(l) for l in ledger_path.read_text().splitlines()
              if l.strip()] if ledger_path.is_file() else []

    arms = {
        "dws-u (DWS understand 原始)": (
            allslots, lambda d: _raw_values(ws, d, "understand")),
        "dws-a (DWS agentic 原始)": (
            allslots, lambda d: _raw_values(ws, d, "agentic")),
        "kimi (LLM 直接读图,越过 loop)": (queue, lambda d: kimi_pred.get(d)),
        "pipeline-auto (DWS+loop 自动层)": (auto, lambda d: auto_pred.get(d)),
        "dws-u 仅队列槽(与 kimi 同分母)": (
            queue, lambda d: _raw_values(ws, d, "understand")),
    }
    out = {"run": str(run_dir),
           "queue_slots": len(queue), "auto_slots": len(auto),
           "human_adjudications": len(ledger), "arms": {}}
    for name, (slots, pred_of) in arms.items():
        out["arms"][name] = score_arm(slots, pred_of)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
