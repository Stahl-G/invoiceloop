#!/usr/bin/env python3
"""从资格集 200 份里抽 20 份行走集(最小哈希,只取工作台真会排队的文档)。

零 API:只读臂 D 的 routing_report.json。抽样规则与资格轮同款,换一把盐。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop.heldout import doc_ids_line_digest  # noqa: E402
from invoiceloop.release_profile import parse_release_profile  # noqa: E402

SALT = "invoiceloop-qual-adk-walk-v1"
AUTO = ("auto_accept", "auto_absent")


def queue_slots(routes: list[dict], policy: dict) -> list[tuple[str, str]]:
    """工作台**真的会排进队列**的 (doc_id, field)。

    不能用「任意非 auto 路由」:HAR-0023 带 release_profile,工作台走的是
    workbench._walk_release_profile —— 只有 gating 字段的待裁决槽和 QA 探针
    进队列。按非 auto 抽,会抽到打开之后队列是空的文档。
    这里复用同一个谓词,改了那边这里必须跟着改。

    行走结果分析的完整性闸也吃这个函数:「该走的槽走完了没有」与「该抽哪些
    文档」必须是同一个定义,两处各写一遍迟早会分叉。
    """
    profile = parse_release_profile(policy or {})
    gate = profile["fields"] if profile else None
    out = set()
    for row in routes:
        codes = [str(c) for c in (row.get("reason_codes") or [])]
        is_qa = any(c.startswith("QA_SAMPLE") for c in codes)
        in_q = row.get("in_human_queue", row.get("requires_adjudication"))
        if in_q is None:
            in_q = row.get("route") not in AUTO
        if is_qa or (in_q and (gate is None or row["field"] in gate)):
            out.add((str(row["doc_id"]), str(row["field"])))
    return sorted(out)


def eligible(routes: list[dict], policy: dict) -> list[str]:
    """队列槽 ≥1 的文档。"""
    return sorted({doc for doc, _ in queue_slots(routes, policy)})


def pick(doc_ids: list[str], n: int) -> list[str]:
    if len(doc_ids) < n:
        raise SystemExit(f"合格文档只有 {len(doc_ids)} 份,不足 {n}")
    ranked = sorted(doc_ids, key=lambda d: hashlib.sha256(
        f"{SALT}|{d}".encode("utf-8")).hexdigest())
    return sorted(ranked[:n])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--routing-report", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()

    report = json.loads(args.routing_report.read_text(encoding="utf-8"))
    pool = eligible(report["routes"], report.get("policy") or {})
    ids = pick(pool, args.n)
    payload = {
        "round": "qual-adk-walk",
        "n": args.n,
        "source": str(args.routing_report),
        "eligibility": "臂 D(HAR-0023)下 workbench._walk_release_profile "
                       "会排进队列的槽 ≥1(gating 字段待裁决 或 QA 探针)",
        "eligible_n": len(pool),
        "eligible_sha256": doc_ids_line_digest(pool),
        "sampling": f"min-hash:sha256(「{SALT}|」+ doc_id) 升序取前 {args.n}",
        "doc_ids": ids,
        "doc_ids_sha256": hashlib.sha256(
            "\n".join(ids).encode("utf-8")).hexdigest(),
    }
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps({k: payload[k] for k in
                      ("eligible_n", "n", "eligible_sha256", "doc_ids_sha256")},
                     ensure_ascii=False, indent=1))
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
