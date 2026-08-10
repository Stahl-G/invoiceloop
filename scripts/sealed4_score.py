#!/usr/bin/env python3
"""Score a completed SEALED-4 broadcast batch (zero DWS / zero ADK).

Strong 子集是主终点与 P1–P3 的判定集(增补件 A4);weak 单列照登;
P1 只看真静默列(增补件 A3,truth-caliber-v1)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop.sealed_batch import score_completed_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--batch", type=Path, default=REPO / "runs" / "sealed4-broadcast",
    )
    parser.add_argument(
        "--corpus", type=Path, default=REPO / "runs" / "sealed4-v2-workspace",
    )
    parser.add_argument("--bundle", type=Path, default=None,
                        help="主臂 audit_bundle.zip;离线 verify 的结果就是 H7")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    output = args.out or (args.batch / "metrics.json")
    metrics = score_completed_batch(
        args.batch,
        corpus_root=args.corpus,
        repo_root=REPO,
        bundle=args.bundle,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps(metrics, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
