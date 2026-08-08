#!/usr/bin/env python3
"""Score a completed SEALED-3 multi-harness batch (zero DWS / zero ADK)."""

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
        "--batch", type=Path, default=REPO / "runs" / "sealed3-multiharness",
    )
    parser.add_argument(
        "--corpus", type=Path, default=REPO / "runs" / "sealed3-workspace",
    )
    parser.add_argument(
        "--bundle", type=Path, required=True,
        help="主臂 audit_bundle.zip;离线 verify 的结果就是 H7",
    )
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
