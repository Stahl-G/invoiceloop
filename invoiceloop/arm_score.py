"""Scoring for the agent-vs-human arms: M1/M2 against truth, M3 paired.

Protocol: `docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md` §5. Zero API.

**The whole difficulty is refusing to collapse three different things into
right/wrong.** DocILE truth is a field value or the absence of an annotation,
and four of the six decisions are not the kind of claim truth can settle:

- `accept` / `correct` / `reject` — truth settles these. Compared with
  `eval_norm.eval_normalise`, the same frozen comparison rule the held-out
  scoring uses (`scripts/heldout_metrics.py`). Not `fields.normalise`: the two
  are byte-identical today by deliberate copy, but the eval one is the frozen
  one, and changing it voids existing numbers.
- `confirm_absent` — truth can only ever **falsify** it. An annotation present
  means the absence claim is provably wrong. An annotation missing means the
  annotator did not label it, which is not the same as the page not having it,
  so the verdict is `unfalsified`, never `agree`. This is the direction the
  2026-08-06 generalisation analysis already scored absence in (3/85 = 3.5%),
  and naming it `agree` would let a reader take a silence for a confirmation.
- `not_applicable` — truth has no way to express "this class of document has no
  such concept". Charter rule five gives that judgement to a person. Scored as
  `unscoreable_not_applicable` and never counted wrong; counting it wrong would
  be using truth to settle a question truth is not about.
- `abstain` — not a truth claim at all.

A slot with no annotation and a value-bearing decision is `no_truth` and drops
out of the rate, matching what `heldout_metrics.measure` already does (it
`continue`s on missing truth). That convention keeps annotation gaps from
inflating either arm's error rate.

M3 pairs only slots **both** arms decided. Slots one arm missed are named in the
output rather than silently intersected away — the TA arm lost 21 slots to an
API spend cap and 6 to writer refusals, and a bare "agreement rate" over the
survivors would read as if both arms had judged all 200.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .eval_norm import eval_normalise
from .fields import FIELD_KINDS
from .review import load_decisions, project

#: 与 adjudicate.DECISIONS 同序,混淆矩阵按它建轴
DECISIONS = ("accept", "confirm_absent", "not_applicable",
             "reject", "correct", "abstain")

#: 真值管不着的决策 → 各自成桶,永不计错
_UNSCOREABLE = {
    "not_applicable": "unscoreable_not_applicable",
    "abstain": "unscoreable_abstain",
}


def load_arm(run_dir: Path) -> dict[str, dict]:
    """一臂的账本 → {slot_key: 最终裁决}。**只取链尖**,改判过的以最后一条为准。"""
    run_dir = Path(run_dir)
    if not (run_dir / "adjudication_ledger.jsonl").exists():
        return {}
    out: dict[str, dict] = {}
    for slot in project(load_decisions(run_dir)).values():
        tip = slot.get("tip")
        if tip:
            out[f"{tip['doc_id']}|{tip['field']}"] = tip
    return out


def truth_verdict(row: dict, tip: dict, *, truth_value: str | None) -> str:
    """一个槽的裁决对不对得上真值。返回值见模块文档,**不是二值**。"""
    decision = tip["decision"]
    if decision in _UNSCOREABLE:
        return _UNSCOREABLE[decision]

    kind = FIELD_KINDS.get(row["field"])
    want = eval_normalise(truth_value, kind) if kind else None

    if decision == "confirm_absent":
        # 真值只能否证缺席,不能证实 —— 没标注 ≠ 页面上没有
        return "disagree" if want is not None else "unfalsified"

    if want is None:
        return "no_truth"

    got = eval_normalise(row.get("value"), kind)
    if decision == "accept":
        return "agree" if got == want else "disagree"
    if decision == "correct":
        fixed = eval_normalise(tip.get("corrected_value"), kind)
        return "agree" if fixed == want else "disagree"
    if decision == "reject":
        # 拒绝一个确实错的值 = 判对;拒绝一个本来对的值 = 判错
        return "disagree" if got == want else "agree"
    return "no_truth"


def score_vs_truth(matrix: dict, arm: dict[str, dict], *,
                   truth_fn: Callable[[str], dict[str, str]]) -> dict[str, Any]:
    """M1 / M2:一臂对真值,按决策类型拆开报。"""
    rows = {f"{r['doc_id']}|{r['field']}": r
            for r in matrix["rows"] if "doc_id" in r}
    by_decision: dict[str, dict[str, int]] = {
        d: {"agree": 0, "disagree": 0, "unfalsified": 0, "no_truth": 0,
            "unscoreable_not_applicable": 0, "unscoreable_abstain": 0}
        for d in DECISIONS}
    for key, tip in sorted(arm.items()):
        row = rows.get(key)
        if row is None:
            continue
        t = truth_fn(row["doc_id"]).get(row["field"])
        by_decision[tip["decision"]][
            truth_verdict(row, tip, truth_value=t)] += 1
    totals = {k: sum(b[k] for b in by_decision.values())
              for k in next(iter(by_decision.values()))}
    decidable = totals["agree"] + totals["disagree"]
    return {
        "n": len(arm),
        "by_decision": by_decision,
        "totals": totals,
        # 分母只含真值判得动的槽 —— unfalsified / unscoreable / no_truth 不进
        "decidable_n": decidable,
        "agreement_rate": (totals["agree"] / decidable) if decidable else None,
    }


def pair(ta: dict[str, dict], h2: dict[str, dict]) -> dict[str, Any]:
    """M3:配对一致率 + 6×6 混淆矩阵。掉队的槽点名,不静默取交集。"""
    both = sorted(set(ta) & set(h2))
    confusion = {a: {b: 0 for b in DECISIONS} for a in DECISIONS}
    agreed = 0
    for key in both:
        a, b = ta[key]["decision"], h2[key]["decision"]
        confusion[a][b] += 1
        agreed += a == b
    return {
        "paired_n": len(both),
        "agreed": agreed,
        "agreement_rate": (agreed / len(both)) if both else None,
        "ta_only": sorted(set(ta) - set(h2)),
        "h2_only": sorted(set(h2) - set(ta)),
        # 行 = TA,列 = H2
        "confusion": confusion,
    }


def report(matrix: dict, ta_run: Path, h2_run: Path, *,
           truth_fn: Callable[[str], dict[str, str]] | None = None,
           expected_slots: list[str] | None = None) -> dict[str, Any]:
    """M1 + M2 + M3 一次算完,并交代抽样的 200 槽各自去了哪。"""
    if truth_fn is None:
        from .safety_metrics import truth as truth_fn  # noqa: PLC0415
    ta, h2 = load_arm(ta_run), load_arm(h2_run)
    out = {
        "protocol": "docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md",
        "M1_ta_vs_truth": score_vs_truth(matrix, ta, truth_fn=truth_fn),
        "M2_h2_vs_truth": score_vs_truth(matrix, h2, truth_fn=truth_fn),
        "M3_paired": pair(ta, h2),
    }
    if expected_slots:
        out["accounting"] = {
            "sampled": len(expected_slots),
            "ta_decided": sum(1 for s in expected_slots if s in ta),
            "h2_decided": sum(1 for s in expected_slots if s in h2),
            "neither": sorted(s for s in expected_slots
                              if s not in ta and s not in h2),
        }
    return out
