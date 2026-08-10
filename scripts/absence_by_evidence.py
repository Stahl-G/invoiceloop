"""每条「页面证据缺席」规则,能省多少槽、要付多少静默缺席。

与 `absence_by_class.py` 同一张表的另一半。那一张按 `doc_class × field` 统计,
授权来自同类文档;这一张按 `field` 统计,授权来自**这一份**的页面上没印过
该字段的标签(`invoice_evidence.LABEL_LEXICON` + 词级 OCR)。

一个槽只有在 DWS **没返回值**时才落到缺席规则手里。此时:

- 页面上印着标签 → 这不是缺席,是漏抽,留给人(`held`);
- 页面上没有标签,真值也没有 → 净省一次人工(`saves`);
- 页面上没有标签,真值**有** → 静默吞掉(`silent`)。**页面上没印标签不等于
  真的没有这个字段** —— 这一列就是为了把这句话的代价量出来。

第三列还有 `unscored`:没有 DocILE 标注记录的文档算不出来,不是零。

**marginal 列**是这套机制真正要回答的问题:有多少 saves 是 2026-08-09 晋升的
16 条类别规则**够不到**的?那 16 条全部落在非 invoice 类,而剩余缺值槽的
568/722 是 invoice。

零 API:只读已存盘的 DWS 响应、独立 OCR、DocILE 标注。
**不要传 SEALED-3 的工作区**(SEALED3_RESULTS.md §7 已把它用掉)。

用法:
    python3 scripts/absence_by_evidence.py [workspace ...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import absence_evidence, doctype, truth_caliber  # noqa: E402
from invoiceloop.safety_metrics import (  # noqa: E402
    annotation_record_available,
    truth,
)

#: 开发语料。SEALED-3 故意不在里面(与 absence_by_class.py 同一份名单)。
DEV_WORKSPACES = (
    "runs/sealed1-workspace",
    "runs/sealed2-workspace",
    "runs/heldout-workspace",
)

#: 已晋升的 16 条类别规则(HAR-0017),用来算 marginal 列。
PROMOTED_POLICY = "docs/evidence/class_absence_2026-08-09/HAR-0017.routing_policy.json"


def _promoted_class_rules(repo: Path) -> set[tuple[str, str]]:
    path = repo / PROMOTED_POLICY
    if not path.exists():
        print(f"警告:{PROMOTED_POLICY} 不在,marginal 列按「无已晋升规则」算",
              file=sys.stderr)
        return set()
    policy = json.loads(path.read_text(encoding="utf-8"))
    return {(r["doc_class"], r["field"])
            for r in policy.get("absent_expected_cohorts") or []
            if r.get("doc_class")}


def _understand(path: Path) -> tuple[str | None, dict]:
    body = json.loads(path.read_text(encoding="utf-8"))
    data = ((body.get("body") or {}).get("output") or {}).get("data") or {}
    raw = data.get("invoice_type")
    return (None if raw is None else str(raw)), data


def collect(workspaces: list[Path], promoted: set[tuple[str, str]]):
    fields = sorted(absence_evidence.LABEL_LEXICON)
    stats = defaultdict(lambda: {
        "dws_missing": 0, "held": 0, "saves": 0, "silent": 0, "unscored": 0,
        "marginal_saves": 0, "marginal_silent": 0, "silent_docs": [],
        # 真值口径拆分(SEALED-4 增补件 A3,truth-caliber-v1):
        # silent = true_silent + caliber;晋升判定只看 true_silent。
        "true_silent": 0, "true_silent_docs": [],
        "caliber": 0, "caliber_docs": [],
    })
    by_class = defaultdict(lambda: {"saves": 0, "silent": 0})
    totals = {"docs": 0, "no_ocr": 0}
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
            probes = absence_evidence.probe_document(doc_id)
            if probes[fields[0]]["status"] == absence_evidence.OCR_UNAVAILABLE:
                totals["no_ocr"] += 1
            truth_ok = annotation_record_available(doc_id)
            tmap = truth(doc_id) if truth_ok else {}
            for field in fields:
                value = data.get(field)
                if value is not None and str(value).strip():
                    continue  # DWS 给了值,缺席规则碰不到这个槽
                cell = stats[field]
                cell["dws_missing"] += 1
                if not absence_evidence.trusted_absence(probes[field]):
                    cell["held"] += 1
                    continue
                # 这一槽会被页面证据规则自动判成缺席
                covered = doc_class is not None and (doc_class, field) in promoted
                if not truth_ok:
                    cell["unscored"] += 1
                elif tmap.get(field) is not None:
                    cell["silent"] += 1
                    cell["silent_docs"].append(doc_id)
                    by_class[(doc_class, field)]["silent"] += 1
                    if not covered:
                        cell["marginal_silent"] += 1
                    # T1/T2 口径争议不算真静默(增补件 A3;单列照登不归零)
                    dispute = truth_caliber.caliber_dispute(doc_id, field, tmap)
                    if dispute:
                        cell["caliber"] += 1
                        cell["caliber_docs"].append(f"{doc_id}({dispute})")
                    else:
                        cell["true_silent"] += 1
                        cell["true_silent_docs"].append(doc_id)
                else:
                    cell["saves"] += 1
                    by_class[(doc_class, field)]["saves"] += 1
                    if not covered:
                        cell["marginal_saves"] += 1
    return stats, by_class, totals


def report(stats, by_class, totals, promoted) -> None:
    fields = sorted(absence_evidence.LABEL_LEXICON)
    n_slots = totals["docs"] * 10
    print(f"# 页面证据缺席台账(语料 {totals['docs']} 份 / {n_slots} 槽;"
          f"OCR 不可用 {totals['no_ocr']} 份)")
    print(f"词表版本 {absence_evidence.digest()[:16]}…"
          f"(引擎 {absence_evidence.ENGINE})\n")
    print("held = 页面印着标签,缺席不成立,留给人;"
          "saves = 无标签且真值也没有;silent = 无标签但真值**有**(静默吞掉);"
          "unscored = 无标注记录,算不出来。")
    print("silent 拆两列(truth-caliber-v1,增补件 A3):caliber = T1/T2 口径争议,"
          "true = 真静默;晋升判定只看 true。\n")
    print("marginal = 已晋升的 16 条类别规则够不到的那部分。\n")
    print(f"{'field':<18}{'缺值':>7}{'held':>7}{'saves':>7}{'silent':>8}"
          f"{'caliber':>9}{'true':>6}{'unscored':>10}{'marg.saves':>12}"
          f"{'marg.silent':>13}")
    for field in fields:
        v = stats[field]
        print(f"{field:<18}{v['dws_missing']:>7}{v['held']:>7}{v['saves']:>7}"
              f"{v['silent']:>8}{v['caliber']:>9}{v['true_silent']:>6}"
              f"{v['unscored']:>10}"
              f"{v['marginal_saves']:>12}{v['marginal_silent']:>13}")

    print("\n## 逐条候选判定(口径规则后:真静默=0、unscored=0、saves≥3)\n")
    safe, risky = [], []
    for field in fields:
        v = stats[field]
        if not v["dws_missing"]:
            continue
        (safe if v["true_silent"] == 0 and v["unscored"] == 0
         and v["saves"] >= 3
         else risky).append((field, v))
    for field, v in safe:
        calib = ""
        if v["caliber"]:
            shown = "、".join(v["caliber_docs"][:4])
            more = f" 等 {v['caliber']} 份" if v["caliber"] > 4 else ""
            calib = f";含口径争议 {v['caliber']} 槽:{shown}{more}"
        print(f"  AV-{field:<20} 省 {v['saves']:>4} 槽,"
              f"其中 {v['marginal_saves']} 是类别规则够不到的{calib}")
    if not safe:
        print("  (无)")
    print(f"\n## 不许开的:{len(risky)} 条\n")
    for field, v in risky:
        docs = "、".join(v["true_silent_docs"][:3])
        more = f" 等 {v['true_silent']} 份" if v["true_silent"] > 3 else ""
        why = []
        if v["true_silent"]:
            why.append(f"吞掉 {v['true_silent']} 个真有值的槽:{docs}{more}")
        if v["unscored"]:
            why.append(f"{v['unscored']} 槽无标注记录,算不出来")
        if v["saves"] < 3:
            why.append(f"只省 {v['saves']} 槽,不值一条规则")
        print(f"  AV-{field:<20} {';'.join(why)}")

    saved = sum(v["saves"] for _, v in safe)
    marginal = sum(v["marginal_saves"] for _, v in safe)
    print(f"\n合计省 {saved} 槽 / 全语料 {n_slots} 槽 = "
          f"{saved / max(n_slots, 1):.2%};其中 {marginal} 槽"
          f"({marginal / max(saved, 1):.0%})是已晋升的 16 条类别规则够不到的。")

    print("\n## 按类别拆开(只看可提的那几条)\n")
    print(f"{'doc_class':<18}{'field':<18}{'saves':>7}{'silent':>8}")
    safe_fields = {f for f, _ in safe}
    rows = [((c, f), v) for (c, f), v in by_class.items() if f in safe_fields]
    rows.sort(key=lambda r: (-r[1]["saves"], str(r[0][0]), r[0][1]))
    for (doc_class, field), v in rows:
        covered = " ←已被类别规则覆盖" if (doc_class, field) in promoted else ""
        print(f"{str(doc_class):<18}{field:<18}"
              f"{v['saves']:>7}{v['silent']:>8}{covered}")

    print("\n三条限定,不许省略:")
    print("- **这是开发集上的数字。** 它决定值不值得提这条候选,"
          "不是未见集上的保证(SEALED-4 尚未抽取)。")
    print("- 词表当前引擎 absence-evidence-v3,机制与词表都**先于本表** commit。"
          "加词只会减少放行、永远不造静默错;看过本表之后删词/窄化就是拟合。")
    print("- 口径争议(truth-caliber-v1)单列照登,不是零 —— 它不计真静默,"
          "但每一例都可复算(T1 金额相等 / T2 词窗命中,增补件 A3 逐条列明)。")
    print("- `unscored` 是「算不出来」,不是零 —— "
          "`improve.gate_verdict` 会在 QA 抽检之前因此拒掉候选。")


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    args = [Path(a) for a in sys.argv[1:]]
    paths = args or [repo / w for w in DEV_WORKSPACES]
    promoted = _promoted_class_rules(repo)
    stats, by_class, totals = collect(
        [p if p.is_absolute() else repo / p for p in paths], promoted)
    report(stats, by_class, totals, promoted)


if __name__ == "__main__":
    main()
