"""单据类型门 vs DocILE 标注:一张交叉表,不是一个准确率。

为什么现在需要它:2026-08-09 起 absent_expected 是**类别 × 字段**规则,
类别由 `doctype.check_document` 的页面字面证据给出。那条规则决定「这个槽
不必再问人」,所以在把它开大之前,得先知道这个类别判定本身有多可信。

为什么给交叉表而不是准确率:DocILE 的 `metadata.document_type` 与本项目的
受控词表**不是同一套东西**,而且两者回答的问题不同 ——

- DocILE 标的是这份文档在语料里的类别(`tax_invoice` / `order` /
  `sales_order` / `utility_bill` / `debit_note` …);
- 本门禁判的是**页面上是否印着**某个受控类别的字面词,它可以合法地在一张
  DocILE 标成 tax_invoice 的单据上判 no_claim(页面没写)。

把两者对齐成一个百分比,需要先编一张映射表,而那张表本身就是结论的一部分。
所以这里只登交叉表和几个可判子集的计数,映射留给读表的人。

零 API:只读已存盘的 DWS 响应、已存盘的独立 OCR、DocILE 标注。

用法:
    python3 scripts/doctype_truth.py runs/sealed1-workspace runs/heldout-workspace
不给参数则跑下面 DEV_WORKSPACES 里的全部开发语料。

**不要传 SEALED-3 的工作区。** 它已经被一次性开箱用掉(SEALED3_RESULTS.md
§7),由它的失败启发的规则不能再回到它身上验。
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import doctype  # noqa: E402
from invoiceloop.safety_metrics import derisk_root  # noqa: E402

#: 开发语料。SEALED-3 故意不在里面。
DEV_WORKSPACES = (
    "runs/sealed1-workspace",
    "runs/sealed2-workspace",
    "runs/heldout-workspace",
)


def _stored_type(path: Path) -> str | None:
    body = json.loads(path.read_text(encoding="utf-8"))
    data = ((body.get("body") or {}).get("output") or {}).get("data") or {}
    raw = data.get("invoice_type")
    return None if raw is None else str(raw)


def _docile_type(doc_id: str) -> str | None:
    path = derisk_root() / "data" / "docile" / "annotations" / f"{doc_id}.json"
    if not path.is_file():
        return None
    body = json.loads(path.read_text(encoding="utf-8"))
    return (body.get("metadata") or {}).get("document_type")


def collect(workspaces: list[Path]) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for ws in workspaces:
        raw_dir = ws / "raw"
        if not raw_dir.is_dir():
            print(f"跳过 {ws}:没有 raw/", file=sys.stderr)
            continue
        for path in sorted(raw_dir.glob("*.understand.json")):
            doc_id = path.name.split(".")[0]
            if doc_id in seen:          # 语料之间可能重叠,一份只算一次
                continue
            seen.add(doc_id)
            check = doctype.check_document(doc_id, _stored_type(path))
            rows.append({
                "doc_id": doc_id,
                "workspace": ws.name,
                "docile_type": _docile_type(doc_id),
                "claimed": check.get("raw_type"),
                "status": check.get("status"),
                "doc_class": doctype.trusted_class(check),
                "phrase": ((check.get("evidence") or {}).get("phrase")
                           if isinstance(check.get("evidence"), dict) else None),
            })
    return rows


def report(rows: list[dict]) -> None:
    n = len(rows)
    print(f"# 单据类型门 vs DocILE 标注(n={n},零 API)\n")
    if not n:
        return

    print("## 1. 门禁裁决分布\n")
    for status, count in Counter(r["status"] for r in rows).most_common():
        print(f"  {status:<16}{count:>5}  ({count / n:.1%})")

    trusted = [r for r in rows if r["doc_class"] is not None]
    print(f"\n拿到可用类别(status=pass 且字面证据完整):{len(trusted)}/{n}"
          f" = {len(trusted) / n:.1%}")
    print("剩下的既不是错也不是对 —— 是**没有页面证据**,规则就不该在它们身上"
          "生效(宪章四:没查过不等于通过)。\n")

    print("## 2. 交叉表:DocILE 标注(行) × 页面字面证据判出的类别(列)\n")
    grid: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        grid[str(r["docile_type"])][r["doc_class"] or f"<{r['status']}>"] += 1
    cols = sorted({c for row in grid.values() for c in row})
    width = max(len(c) for c in cols) + 2
    head = "".join(f"{c:>{width}}" for c in cols)
    print(f"{'docile_type':<16}{head}{'total':>8}")
    for docile in sorted(grid, key=lambda k: -sum(grid[k].values())):
        line = "".join(f"{grid[docile][c] or '':>{width}}" for c in cols)
        print(f"{docile:<16}{line}{sum(grid[docile].values()):>8}")

    print("\n## 3. 两者都表态时的一致性\n")
    print("只看 DocILE 有标注、且门禁拿到了可用类别的文档。"
          "映射是**这里显式写下的判断**,不是数据自带的:\n")
    mapping = {
        "tax_invoice": "invoice",
        "purchase_order": "purchase_order",
        "receipt": "receipt",
        "proforma": "proforma",
        "credit_note": "credit_note",
    }
    for k, v in mapping.items():
        print(f"  {k:<16}→ {v}")
    unmapped = sorted({str(r["docile_type"]) for r in rows
                       if r["docile_type"] and r["docile_type"] not in mapping})
    print(f"\n受控词表里没有对应项、因此不进这一节的 DocILE 类型:"
          f"{'、'.join(unmapped) or '(无)'}")
    print("  `order` / `sales_order` 尤其要小心:页面上印 ORDER 的单据既可能是"
          "采购订单,也可能是订单确认,DocILE 一个标签盖了两种。\n")

    scored = [r for r in trusted
              if r["docile_type"] in mapping]
    agree = [r for r in scored if r["doc_class"] == mapping[r["docile_type"]]]
    if scored:
        print(f"可判子集 {len(scored)} 份,一致 {len(agree)} 份 "
              f"= {len(agree) / len(scored):.1%}")
        for r in scored:
            if r["doc_class"] != mapping[r["docile_type"]]:
                print(f"  不一致 {r['doc_id']}:DocILE={r['docile_type']} "
                      f"页面字面「{r['phrase']}」→ {r['doc_class']} "
                      f"(DWS 自报 {r['claimed']!r})")
    else:
        print("可判子集为空。")

    print("\n## 4. DWS 自报类型 vs 页面字面证据\n")
    print("这一栏是 doctype.py 存在的理由:自报的类型由**被监督的那个模型**"
          "写出,不能拿来当放松监督的依据。\n")
    claimed_only = [r for r in rows
                    if r["claimed"] and r["doc_class"] is None]
    print(f"DWS 给了类型、但页面上找不到字面证据:{len(claimed_only)}/{n}"
          f" = {len(claimed_only) / n:.1%}")
    for status, count in Counter(r["status"] for r in claimed_only).most_common():
        print(f"    其中 {status}: {count}")


def main() -> None:
    args = sys.argv[1:]
    repo = Path(__file__).resolve().parent.parent
    paths = [Path(a) for a in args] or [repo / w for w in DEV_WORKSPACES]
    rows = collect([p if p.is_absolute() else repo / p for p in paths])
    report(rows)


if __name__ == "__main__":
    main()
