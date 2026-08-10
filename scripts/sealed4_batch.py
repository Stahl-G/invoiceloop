#!/usr/bin/env python3
"""Open SEALED-4 (broadcast redraw) once under the frozen harness arms.

Same discipline as the SEALED-3 opener: identities and invariants only; no
workload, safety, or H1-H7 number exists before ``batch_complete.json``.
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
        default=REPO / "docs" / "sealed4_plan.json",
    )
    parser.add_argument(
        "--corpus", type=Path, default=REPO / "runs" / "sealed4-v2-workspace",
    )
    parser.add_argument(
        "--out", type=Path, default=REPO / "runs" / "sealed4-broadcast",
    )
    parser.add_argument(
        "--expected-head", required=True,
        help="钉板 commit 的完整 git SHA;不一致即拒绝开箱",
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
