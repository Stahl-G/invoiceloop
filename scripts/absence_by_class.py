"""每条「类别 × 字段」缺席规则,能省多少槽、要付多少静默缺席。

这是提 absent_expected 候选之前该看的那张表。它不替人决定开哪条规则 ——
它把两侧的数量摆出来,让签字的人看着数字决定。

一个槽只有在 DWS **没返回值**时才会落到缺席规则手里。此时两种可能:

- 真值也没有 → 这条规则省下一次人工,没有代价;
- 真值**有** → 这个槽被自动判成缺席,再也不会有人看到它。这就是
  silent_absent,SEALED-3 主臂唯一那次失败就长这样(一张 credit note 上
  真有值的 seller_vat_id 被一条无条件规则吞掉,SEALED3_RESULTS.md §4)。

所以每条规则的报告是一对数:`saves`(净省)与 `silent`(静默吞掉)。
`silent > 0` 的规则不该开 —— improve.gate_verdict 也会在 QA 抽检**之前**
就拒掉它,这里只是让人提前看见同一件事。

类别只认页面字面证据(doctype.trusted_class)。DWS 自报的类型不进这张表:
自报类型由被监督的模型写出,拿它当放松监督的依据等于让模型关掉自己的监督。

零 API:只读已存盘的 DWS 响应、独立 OCR、DocILE 标注。
**不要传 SEALED-3 的工作区**(SEALED3_RESULTS.md §7 已把它用掉)。

用法:
    python3 scripts/absence_by_class.py [workspace ...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import doctype  # noqa: E402
from invoiceloop.fields import FIELDS, TIER1  # noqa: E402
from invoiceloop.safety_metrics import (  # noqa: E402
    annotation_record_available,
    truth,
)
#: 开发语料。SEALED-3 故意不在里面(与 scripts/doctype_truth.py 同一份名单;
#: 这里重列一遍而不是跨脚本 import —— 脚本目录不是包,import 依赖 cwd。)
DEV_WORKSPACES = (
    "runs/sealed1-workspace",
    "runs/sealed2-workspace",
    "runs/heldout-workspace",
)


def _understand(path: Path) -> tuple[str | None, dict]:
    body = json.loads(path.read_text(encoding="utf-8"))
    data = ((body.get("body") or {}).get("output") or {}).get("data") or {}
    raw = data.get("invoice_type")
    return (None if raw is None else str(raw)), data


def collect(workspaces: list[Path]) -> tuple[dict[tuple[str, str], dict], dict]:
    stats: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"docs": 0, "dws_missing": 0, "saves": 0, "silent": 0,
                 "unscored": 0, "silent_docs": []})
    totals = {"docs": 0, "classed": 0}
    seen: set[str] = set()
    for ws in workspaces:
        raw_dir = ws / "raw"
        if not raw_dir.is_dir():
            print(f"跳过 {ws}:没有 raw/", file=sys.stderr)
            continue
        for path in sorted(raw_dir.glob("*.understand.json")):
            doc_id = path.name.split(".")[0]
            if doc_id in seen:
                continue
            seen.add(doc_id)
            totals["docs"] += 1
            raw_type, data = _understand(path)
            doc_class = doctype.trusted_class(
                doctype.check_document(doc_id, raw_type))
            if doc_class is None:
                continue           # 没有页面证据 → 类别条件规则不该生效
            totals["classed"] += 1
            truth_ok = annotation_record_available(doc_id)
            tmap = truth(doc_id) if truth_ok else {}
            for field in sorted(FIELDS):
                cell = stats[(doc_class, field)]
                cell["docs"] += 1
                value = data.get(field)
                if value is not None and str(value).strip():
                    continue       # DWS 给了值,缺席规则碰不到这个槽
                cell["dws_missing"] += 1
                if not truth_ok:
                    cell["unscored"] += 1
                elif tmap.get(field) is not None:
                    cell["silent"] += 1
                    cell["silent_docs"].append(doc_id)
                else:
                    cell["saves"] += 1
    return stats, totals


def report(stats: dict[tuple[str, str], dict], totals: dict) -> None:
    rows = [(c, f, v) for (c, f), v in stats.items() if v["dws_missing"]]
    rows.sort(key=lambda r: (-r[2]["saves"], r[0], r[1]))
    print(f"# 类别 × 字段缺席规则台账"
          f"(语料 {totals['docs']} 份,其中有页面类别证据 "
          f"{totals['classed']} 份)\n")
    print("saves = DWS 没给值且真值也没有(净省的人工);"
          "silent = DWS 没给值但真值**有**(会被静默吞掉);"
          "unscored = 该文档没有标注记录,算不出来 —— 不是零。\n")
    print(f"{'doc_class':<16}{'field':<18}{'tier':<7}"
          f"{'saves':>7}{'silent':>8}{'unscored':>10}")
    for doc_class, field, v in rows:
        tier = "TIER1" if field in TIER1 else "TIER2"
        print(f"{doc_class:<16}{field:<18}{tier:<7}"
              f"{v['saves']:>7}{v['silent']:>8}{v['unscored']:>10}")

    safe = [(c, f, v) for c, f, v in rows
            if v["silent"] == 0 and v["unscored"] == 0 and v["saves"] >= 3]
    print(f"\n## 可以提的候选(silent=0、unscored=0、saves≥3):{len(safe)} 条\n")
    for doc_class, field, v in safe:
        rule = f"AE-{doc_class}-{field}"
        print(f"  {rule:<34} 省 {v['saves']:>3} 槽"
              f"({v['saves'] / max(v['docs'], 1):.1%} 的该类文档)")
    saved = sum(v["saves"] for _, _, v in safe)
    all_slots = totals["docs"] * len(FIELDS)
    print(f"\n合计省 {saved} 槽 / 全语料 {all_slots} 槽 = "
          f"{saved / max(all_slots, 1):.1%} 的人工负载。")
    print("这一列是**开发集上的**数字。它决定值不值得提这条候选;"
          "它不是未见集上的保证 —— 那要另抽一批封箱语料(SEALED-4)。\n")

    risky = [(c, f, v) for c, f, v in rows if v["silent"]]
    print(f"## 不许开的(silent > 0):{len(risky)} 条\n")
    for doc_class, field, v in risky:
        docs = "、".join(v["silent_docs"][:3])
        more = f" 等 {v['silent']} 份" if v["silent"] > 3 else ""
        rule = f"AE-{doc_class}-{field}"
        print(f"  {rule:<34} 会吞掉 {v['silent']} 个真有值的槽"
              f"(换 {v['saves']} 次省人工):{docs}{more}")


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    args = [Path(a) for a in sys.argv[1:]]
    paths = args or [repo / w for w in DEV_WORKSPACES]
    stats, totals = collect([p if p.is_absolute() else repo / p for p in paths])
    report(stats, totals)


if __name__ == "__main__":
    main()
