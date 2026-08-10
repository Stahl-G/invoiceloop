#!/usr/bin/env python3
"""Draw the HITL R1/R2 round corpora (docs/HITL_R1R2_PROTOCOL_2026-08-10.md §1).

Pool = broadcast strong/weak docs from the frozen pilot scope file (its own
classification, not recomputed), minus h2_excluded.  sealed4-100 is excluded
by construction (those docs are not in the pilot scope workspaces' dual-mode
set used here) and asserted anyway.  Zero new DWS calls: every sampled doc
must have understand+agentic responses stored in one of the four workspaces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCOPE_FILE = REPO / "docs" / "BROADCAST_PILOT_SCOPE_2026-08-09.json"
SEALED4_LIST = REPO / "docs" / "sealed4_doc_list.json"
WORKSPACES = ("sealed1-workspace", "sealed2-workspace",
              "heldout-workspace", "sealed3-workspace")
SEED_CONTEXT = "invoiceloop-hitl-r1r2-2026-08-10"


def _digest(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def _has_dual_mode(doc_id: str) -> str | None:
    for name in WORKSPACES:
        raw = REPO / "runs" / name / "raw"
        if (raw / f"{doc_id}.understand.json").is_file() and \
                (raw / f"{doc_id}.agentic.json").is_file():
            return name
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n-per-round", type=int, default=100)
    args = ap.parse_args()

    scope = json.loads(SCOPE_FILE.read_text(encoding="utf-8"))
    excluded = set(scope["h2_excluded_doc_ids"])
    pool = sorted(doc for doc, ev in scope["evidence"].items()
                  if ev["strength"] in ("strong", "weak")
                  and doc not in excluded)
    sealed4 = set(json.loads(SEALED4_LIST.read_text())["doc_ids"])
    overlap = sealed4 & set(pool)
    assert not overlap, f"语料池混入资格集文档:{sorted(overlap)[:3]}"

    missing = [d for d in pool if _has_dual_mode(d) is None]
    if missing:
        print(json.dumps({"dropped_no_stored_response": missing},
                         ensure_ascii=False, indent=1))
        pool = [d for d in pool if d not in set(missing)]

    seed = int(hashlib.sha256(SEED_CONTEXT.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    r1 = sorted(rng.sample(pool, args.n_per_round))
    rest = [d for d in pool if d not in set(r1)]
    r2 = sorted(rng.sample(rest, args.n_per_round))

    strength = {d: scope["evidence"][d]["strength"] for d in pool}
    for name, ids in (("hitl-r1", r1), ("hitl-r2", r2)):
        out_dir = REPO / "runs" / name
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "protocol": "docs/HITL_R1R2_PROTOCOL_2026-08-10.md",
            "round": name, "n": len(ids),
            "strong_n": sum(1 for d in ids if strength[d] == "strong"),
            "weak_n": sum(1 for d in ids if strength[d] == "weak"),
            "pool_n": len(pool), "pool_sha256": _digest(pool),
            "seed_context": SEED_CONTEXT,
            "sampling": "random.Random(sha256(seed_context)).sample, "
                        "R1 first, R2 from remainder, both sorted",
            "classification": "docs/BROADCAST_PILOT_SCOPE_2026-08-09.json "
                              "evidence.strength(不重新分类)",
            "exclusions": ["h2_excluded(17)", "sealed4-100(断言零交集)",
                           "无存盘双模式响应(见 stdout)"],
            "doc_ids_sha256": _digest(ids),
            "doc_ids": ids,
        }
        (out_dir / "doc_list.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
        print(name, "n=", len(ids),
              "strong=", payload["strong_n"], "weak=", payload["weak_n"],
              "sha=", payload["doc_ids_sha256"][:16])


if __name__ == "__main__":
    main()
