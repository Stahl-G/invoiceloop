#!/usr/bin/env python3
"""Draw the 200 adjudication slots for the agent-vs-human arms. Zero API.

Protocol: `docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md` §2 — frozen before
either arm ran. Rerun to verify the list; it is a pure function of the sealed-2
support matrix plus the drand seed.

    python3 scripts/arm_sample.py > docs/arm_slot_sample.json
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import arms  # noqa: E402

RUN = Path("runs/sealed2")
DRAND_ROUND = 6356437
SEED = "08b6c717dc07a6628986c48d4ad0c9b784fd53270bc7bb3ce36d233333c6e082"
N = 200


def main() -> None:
    matrix = json.loads((RUN / "support_matrix.json").read_text(encoding="utf-8"))
    pool = arms.review_pool(matrix)
    keys = arms.sample_slots(matrix, SEED, N)
    rows = {arms.slot_key(r): r for r in matrix["rows"] if "doc_id" in r}
    picked = [rows[k] for k in keys]

    def tally(fn) -> dict:
        return dict(sorted(collections.Counter(fn(r) for r in picked).items()))

    payload = {
        "purpose": "agent-vs-human adjudication arms; same slots for both",
        "protocol": "docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md",
        "source_run": str(RUN),
        "harness_id": json.loads(
            (RUN / "routing_report.json").read_text(encoding="utf-8"))["harness_id"],
        "drand_round": DRAND_ROUND,
        "seed": SEED,
        "prng_context": arms.ARM_CONTEXT,
        "pool_size": len(pool),
        "n": N,
        # 抽中样本的构成:抽样后立刻记下,后面没法说"样本挑过"
        "drawn_profile": {
            "by_field": tally(lambda r: r["field"]),
            "by_support_strength": tally(lambda r: r.get("support_strength")),
            "empty_value": sum(1 for r in picked
                               if not (r.get("value") or "").strip()),
            "qa_probe": sum(1 for r in picked
                            if any(str(c).startswith("QA_SAMPLE:")
                                   for c in (r.get("reason_codes") or []))),
            "distinct_docs": len({r["doc_id"] for r in picked}),
        },
        "slots": keys,
    }
    print(json.dumps(payload, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
