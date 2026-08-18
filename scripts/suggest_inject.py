#!/usr/bin/env python3
"""Offline suggestion injector (Phase 0-1, docs/PHASE01_HITL_SUGGESTION_PLAN_2026-08-10.md).

Converts any offline suggestion source (TA-arm adjudications, ADK pilot
outputs, deterministic derivations) into `vision/answers6.<tag>.tsv` inside a
workspace, **before** `invoiceloop run`. Suggestions are run inputs: they are
captured into the run, enter the input fingerprint, and reach the review UI
only as prefill drafts — a human still decides what enters the ledger.

Append-only, like cmd_vision: a (doc, field) pair already answered by this tag
is left untouched and reported, never rewritten.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from invoiceloop.dws import load_vision_answers
from invoiceloop.fields import FIELD_KINDS

#: tag 会拼进文件名 answers6.<tag>.tsv;字符集与 bundle 成员名校验同形
_SAFE_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

HEADER = "doc\tfield\tvalue\tprinted_label\tnote\n"


def _load_rows(path: Path) -> list[dict]:
    """输入:JSON array 或 JSONL,每条形如
    {"doc_id", "field", "value", "printed_label"?, "note"?}。"""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if not isinstance(data, list):
        raise SystemExit(f"输入契约:{path} 顶层必须是 array(或改用 .jsonl)")
    return data


def inject(workspace: Path, tag: str, rows: list[dict], *,
           run_dir: Path | None = None) -> dict:
    """默认写 <workspace>/vision(run 前,建议进输入指纹、成为冻结草稿);
    run_dir 模式写 <run_dir>/vision(run 后,**展示型建议** —— 只进裁决页
    预填,不成为草稿,不进快照成分;HITL 轮次协议 §2 的用法)。"""
    if not _SAFE_TAG.match(tag):
        raise SystemExit(f"非法 tag:{tag!r} —— 只允许 {_SAFE_TAG.pattern}")
    vision_dir = Path(run_dir) / "vision" if run_dir is not None \
        else Path(workspace) / "vision"
    vision_dir.mkdir(parents=True, exist_ok=True)
    tsv = vision_dir / f"answers6.{tag}.tsv"

    answered = set()
    if tsv.exists():
        for line in tsv.read_text(encoding="utf-8").splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) >= 2 and cols[0].strip() and cols[1].strip():
                answered.add((cols[0], cols[1]))

    summary = {"written": 0, "skipped_existing": 0, "dropped": []}
    new_lines: list[str] = []
    for i, row in enumerate(rows):
        doc = str(row.get("doc_id") or "").strip()
        field = str(row.get("field") or "").strip()
        value = str(row.get("value") or "").strip()
        if not doc or field not in FIELD_KINDS:
            summary["dropped"].append(
                {"index": i, "doc_id": doc, "field": field,
                 "reason": "doc_id 为空或 field 不在字段表"})
            continue
        if "\t" in value or "\n" in value:
            summary["dropped"].append(
                {"index": i, "doc_id": doc, "field": field,
                 "reason": "value 含制表符/换行,会破坏 TSV 列"})
            continue
        if (doc, field) in answered:
            summary["skipped_existing"] += 1
            continue
        label = str(row.get("printed_label") or "").strip()
        note = str(row.get("note") or "").strip()
        new_lines.append("\t".join([doc, field, value, label, note]))
        answered.add((doc, field))
        summary["written"] += 1

    if new_lines:
        needs_header = not tsv.exists() or tsv.stat().st_size == 0
        with tsv.open("a", encoding="utf-8") as fh:
            if needs_header:
                fh.write(HEADER)
            for line in new_lines:
                fh.write(line + "\n")

    # 回读校验:落盘行数必须能被既有加载器原样读回(畸形=注入器自己的 bug)。
    # 加载器按显示名建键:已登记 tag 用 VISION_READERS 的名字,新 tag 用自身。
    from invoiceloop.dws import VISION_READERS

    reread = load_vision_answers(vision_dir=vision_dir)
    model_rows = reread.get(VISION_READERS.get(tag, tag), {})
    summary["reread_rows"] = len(model_rows)
    summary["tsv"] = str(tsv)
    return summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", type=Path,
                    help="run 前模式:写 <ws>/vision/answers6.<tag>.tsv")
    ap.add_argument("--run-dir", type=Path, default=None,
                    help="run 后模式:写 <run>/vision/(展示型建议,不成草稿)")
    ap.add_argument("--tag", required=True,
                    help="建议来源 tag(显示名;新读者用新 tag)")
    ap.add_argument("--input", required=True, type=Path,
                    help="JSON array 或 .jsonl:{doc_id, field, value, ...}")
    args = ap.parse_args(argv)
    if args.run_dir is None and args.workspace is None:
        ap.error("--workspace 与 --run-dir 至少给其一")
    rows = _load_rows(args.input)
    summary = inject(args.workspace or args.run_dir, args.tag, rows,
                     run_dir=args.run_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if summary["dropped"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
