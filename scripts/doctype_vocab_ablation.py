"""Per-token ablation of the doctype vocabulary. Zero API.

Answers one question: **which tokens in `doctype.CLASSES` actually decide
anything?** For every alternative in every class pattern, drop it, reclassify
both sealed sets from the frozen DWS responses, and report what moved.

This is the evidence behind the 2026-08-07 de-contamination (`doctype-v2`).
Seven tokens were removed because they were measured dead — every free-text
string that contained one also contained a generic token (`credit`, `order`,
`contract`, `invoice`), so no document changed class. A token that decides
nothing but was written down *because the calibration corpus spelled it that
way* makes `unmapped=0` look measured when it was constructed.

Usage:
  python3 scripts/doctype_vocab_ablation.py            # summary table
  python3 scripts/doctype_vocab_ablation.py --detail   # + every reclassification
  python3 scripts/doctype_vocab_ablation.py --drop discrepancy,billing
      # combined removal — single-token ablation misses mutually-redundant
      # pairs, so a combination has to be checked as a combination
  python3 scripts/doctype_vocab_ablation.py --v1-diff
      # reconstitute the pre-de-contamination vocabulary and diff v1 -> v2.
      # This is the one that keeps "removing the seven changed nothing"
      # falsifiable now that the code no longer contains them.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

#: 2026-08-07 去污(v1 → v2)删掉的七个 DocILE 派生 token,连同它们当初
#: 挂在哪个类、插在同类 token 的第几位 —— 位置要原样记下来,不然
#: `--v1-diff` 重建出的顺序与真的 v1 不同,那就不是同一个词表了。
REMOVED_V2: tuple[tuple[str, str, int], ...] = (
    ("credit_note",    "discrepancy", 2),
    ("purchase_order", "worksheet",   1),
    ("purchase_order", "printout",    2),
    ("purchase_order", "traffic",     3),
    ("contract",       "broadcast",   2),
    ("invoice",        "affidavit",   3),
    ("invoice",        "billing",     4),
)
REMOVED_TOKENS = tuple(tok for _, tok, _ in REMOVED_V2)


def _doc_ids(which: str) -> tuple[list[str], Path]:
    if which == "s2":
        ws = REPO / "runs" / "sealed2-workspace"
        ids = json.load(open(REPO / "docs" / "sealed2_doc_list.json"))["doc_ids"]
    else:
        ws = REPO / "runs" / "sealed1-workspace"
        hitl = {p.stem for p in
                (REPO / "runs" / "hitl-sealed" / "input" / "pdfs").glob("*.pdf")}
        ids = [d for d in json.load(open(
            REPO / "docs" / "sealed1_doc_list.json"))["doc_ids"] if d not in hitl]
    return ids, ws


def raw_types(which: str) -> list[tuple[str, str | None]]:
    """(doc_id, 模型写的 invoice_type) —— 只读存盘响应,不碰 API。

    两个集的语料根不同,`dws.load_response` 认的是 `INVOICELOOP_CORPUS`,
    所以换集时必须把 invoiceloop 的模块缓存清掉重导。
    """
    ids, ws = _doc_ids(which)
    os.environ["INVOICELOOP_CORPUS"] = str(ws)
    for mod in [m for m in list(sys.modules) if m.startswith("invoiceloop")]:
        del sys.modules[mod]
    from invoiceloop import dws  # noqa: PLC0415
    out = []
    for doc in ids:
        u = dws.load_response(doc, "understand")
        v = None if u is None else u.data.get("invoice_type")
        out.append((doc, None if v is None else str(v)))
    return out


def _load_base() -> dict[str, str]:
    os.environ.setdefault("INVOICELOOP_CORPUS",
                          str(REPO / "runs" / "sealed1-workspace"))
    from invoiceloop import doctype  # noqa: PLC0415
    return {name: pat for name, (pat, _) in doctype.CLASSES.items()}


BASE = _load_base()
CORPORA = {w: raw_types(w) for w in ("s1", "s2")}
LABEL = {"s1": "SEALED-1 unseen-88", "s2": "SEALED-2"}


def classify_with(patterns: dict[str, str | None], raw: str | None) -> str:
    """`doctype.classify` 的可注入版本 —— 类顺序必须与 CLASSES 一致。"""
    s = (raw or "").strip().lower()
    if not s:
        return "no_claim"
    for name in BASE:                     # dict 保序 == 匹配顺序
        pat = patterns.get(name)
        if pat and re.search(pat, s):
            return name
    return "unmapped"


def without(tokens: set[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for cls, pat in BASE.items():
        alts = [a for a in pat.split("|") if a not in tokens]
        out[cls] = "|".join(alts) if alts else None
    return out


def v1_patterns() -> dict[str, str]:
    """把去污前的词表按记录的插入位重建出来。"""
    alts = {cls: pat.split("|") for cls, pat in BASE.items()}
    for cls, tok, idx in REMOVED_V2:
        alts[cls].insert(idx, tok)
    return {cls: "|".join(a) for cls, a in alts.items()}


def deltas(patterns: dict[str, str | None],
           reference: dict[str, str | None] | None = None
           ) -> dict[str, list[tuple]]:
    ref = BASE if reference is None else reference
    out = {}
    for w, rows in CORPORA.items():
        moved = []
        for doc, raw in rows:
            was, now = classify_with(ref, raw), classify_with(patterns, raw)
            if was != now:
                moved.append((doc, raw, was, now))
        out[w] = moved
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--drop", help="逗号分隔的 token,一起删(组合验证)")
    ap.add_argument("--v1-diff", action="store_true",
                    help="重建去污前词表并与现行 v2 对比")
    args = ap.parse_args()

    if args.v1_diff:
        v1 = v1_patterns()
        print("=== doctype-v1 (reconstituted) -> doctype-v2 (current) ===")
        for cls in BASE:
            if v1[cls] != BASE[cls]:
                print(f"  {cls}: {v1[cls]!r} -> {BASE[cls]!r}")
        d = deltas(BASE, reference=v1)
        total = 0
        for w in CORPORA:
            print(f"  {LABEL[w]}: {len(d[w])} reclassified")
            for doc, raw, was, now in d[w]:
                print(f"      {raw!r}  {was} -> {now}   ({doc})")
            total += len(d[w])
        print(f"  TOTAL RECLASSIFIED BY THE DE-CONTAMINATION: {total}")
        sys.exit(0)

    if args.drop is not None:
        tokens = {t.strip() for t in args.drop.split(",") if t.strip()}
        d = deltas(without(tokens))
        print(f"=== combined removal: {sorted(tokens)} ===")
        for cls, pat in BASE.items():
            new = without(tokens)[cls]
            if new != pat:
                print(f"  {cls}: {pat!r} -> {new!r}")
        total = 0
        for w in CORPORA:
            print(f"  {LABEL[w]}: {len(d[w])} reclassified")
            for doc, raw, was, now in d[w]:
                print(f"      {raw!r}  {was} -> {now}   ({doc})")
            total += len(d[w])
        print(f"  TOTAL: {total}")
        sys.exit(0)

    print(f"{'class':<15} {'token':<18} {'S1':>4} {'S2':>4}   verdict")
    print("-" * 60)
    for cls, pat in BASE.items():
        for alt in pat.split("|"):
            d = deltas(without({alt}))
            n1, n2 = len(d["s1"]), len(d["s2"])
            verdict = "DEAD" if n1 == n2 == 0 else "load-bearing"
            mark = "  <- removed in v2" if alt in REMOVED_V2 else ""
            print(f"{cls:<15} {alt:<18} {n1:>4} {n2:>4}   {verdict}{mark}")
            if args.detail:
                for w in ("s1", "s2"):
                    for doc, raw, was, now in d[w]:
                        print(f"{'':<20} {w}: {raw!r}  {was} -> {now}")

    print()
    print("NOTE 单 token 消融看不出**互相冗余**的一对(去掉任一另一个还在),"
          "组合要用 --drop 验。")


if __name__ == "__main__":
    main()
