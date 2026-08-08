#!/usr/bin/env python3
"""Open SEALED-3 once under every pre-frozen harness arm.

This command deliberately prints identities and invariants only.  It never
calculates workload, safety, or H1-H7; those become readable only after the
whole batch has a ``batch_complete.json`` marker.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop.sealed_batch import run_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan", type=Path,
        default=REPO / "docs" / "sealed3_multiharness_plan.json",
    )
    parser.add_argument(
        "--corpus", type=Path, default=REPO / "runs" / "sealed3-workspace",
    )
    parser.add_argument(
        "--out", type=Path, default=REPO / "runs" / "sealed3-multiharness",
    )
    parser.add_argument(
        "--expected-head", required=True,
        help="冻结 addendum 提交后的完整 git SHA;不一致即拒绝开箱",
    )
    args = parser.parse_args()
    complete = run_batch(
        args.plan,
        args.out,
        corpus_root=args.corpus,
        repo_root=REPO,
        expected_head=args.expected_head,
    )
    print(json.dumps({
        "status": complete["status"],
        "opened_at_commit": complete["opened_at_commit"],
        "plan_sha256": complete["plan_sha256"],
        "n_docs": complete["n_docs"],
        "arm_ids": [arm["arm_id"] for arm in complete["arms"]],
        "input_fingerprint": complete["arms"][0]["input_fingerprint"],
        "invariants": complete["invariants"],
        "note": "未读取或打印任何结果指标;批次完整后才可运行 scorer。",
    }, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
