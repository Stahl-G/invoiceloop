#!/usr/bin/env python3
"""Freeze the public DocILE broadcast pilot boundary.

This is a sampling/control script, not a runtime document classifier.  It
never writes a harness or changes active state.  The runtime receives a
human-approved batch scope produced from the resulting list.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from invoiceloop.scope import BROADCAST_DOMAIN, doc_ids_digest

CALLSIGN = re.compile(r"^[KW][A-Z]{2,3}(-(TV|FM|AM|DT|CD|LD))?$")
BROADCAST_TERMS = (
    "advertiser", "broadcast", "station", "spot", "airtime", "commercial",
    "agency", "media", "network", "radio", "television", "political",
)
DEFAULT_WORKSPACES = (
    "sealed1-workspace", "sealed2-workspace", "heldout-workspace",
    "sealed3-workspace",
)


def _words(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        str(word.get("value", ""))
        for page in payload.get("pages", [])
        for block in page.get("blocks", [])
        for line in block.get("lines", [])
        for word in line.get("words", [])
    ]


def classify_evidence(ocr_path: Path) -> dict[str, Any]:
    words = _words(ocr_path)
    upper = [word.upper() for word in words]
    lower = " ".join(words).lower()
    callsigns = sorted({word for word in upper if CALLSIGN.fullmatch(word)})
    keyword_hits = sorted({term for term in BROADCAST_TERMS if term in lower})
    keyword_occurrences = sum(lower.count(term) for term in BROADCAST_TERMS)
    strong = bool(callsigns) and keyword_occurrences >= 2
    # Weak means the document enters the broadcast candidate union through
    # exactly one strong signal: a callsign without two keyword occurrences,
    # or two keyword occurrences without a callsign.  A single keyword alone
    # remains OOD rather than acquiring broadcast policy authority.
    weak = ((bool(callsigns) and keyword_occurrences < 2)
            or (not callsigns and keyword_occurrences >= 2))
    return {
        "callsigns": callsigns,
        "keyword_hits": keyword_hits,
        "keyword_occurrences": keyword_occurrences,
        "strength": "strong" if strong else "weak" if weak else "none",
    }


def dual_mode_docs(run_root: Path, workspace_names: list[str]) -> set[str]:
    found: set[str] = set()
    for name in workspace_names:
        raw = run_root / "runs" / name / "raw"
        if not raw.is_dir():
            continue
        for path in raw.glob("*.understand.json"):
            doc_id = path.name.removesuffix(".understand.json")
            if (raw / f"{doc_id}.agentic.json").is_file():
                found.add(doc_id)
    return found


def h2_docs(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("doc_id"):
            out.add(record["doc_id"])
    return out


def build_scope(run_root: Path, docile_root: Path,
                workspace_names: list[str], h2_path: Path | None,
                *, eval_n: int = 30) -> dict[str, Any]:
    ocr_root = docile_root / "data" / "docile" / "ocr"
    docs = sorted(dual_mode_docs(run_root, workspace_names))
    evidence: dict[str, dict[str, Any]] = {}
    for doc_id in docs:
        path = ocr_root / f"{doc_id}.json"
        if path.is_file():
            evidence[doc_id] = classify_evidence(path)
        else:
            evidence[doc_id] = {"callsigns": [], "keyword_hits": [],
                                "strength": "none", "ocr_missing": True}
    strong = sorted(d for d in docs if evidence[d]["strength"] == "strong")
    weak = sorted(d for d in docs if evidence[d]["strength"] == "weak")
    none = sorted(d for d in docs if evidence[d]["strength"] == "none")
    excluded = h2_docs(h2_path)
    eligible = [d for d in strong if d not in excluded]
    ranked = sorted(
        eligible,
        key=lambda d: hashlib.sha256(
            f"broadcast-pilot-v1|{d}".encode("utf-8")).hexdigest(),
    )
    if eval_n <= 0 or eval_n > len(ranked):
        raise ValueError(f"eval_n={eval_n} 超出可用广播文档数 {len(ranked)}")
    evaluation = ranked[:eval_n]
    development = [d for d in strong if d not in set(evaluation)]
    return {
        "protocol": "broadcast-pilot-v1",
        "domain": BROADCAST_DOMAIN,
        "selection_rule": (
            "strong = FCC-style callsign AND at least two broadcast terms; "
            "weak = one-sided evidence; none = neither"
        ),
        "source_workspaces": workspace_names,
        "n_dual_mode_docs": len(docs),
        "strong_n": len(strong),
        "weak_n": len(weak),
        "none_n": len(none),
        "strong_doc_ids_sha256": doc_ids_digest(strong),
        "weak_doc_ids_sha256": doc_ids_digest(weak),
        "none_doc_ids_sha256": doc_ids_digest(none),
        "h2_excluded_n": len(excluded & set(strong)),
        "h2_excluded_doc_ids": sorted(excluded & set(strong)),
        "evaluation_doc_ids": evaluation,
        "evaluation_n": len(evaluation),
        "evaluation_doc_ids_sha256": doc_ids_digest(evaluation),
        "development_doc_ids": development,
        "development_n": len(development),
        "ood_doc_ids": none,
        "ood_n": len(none),
        "evidence": {doc_id: evidence[doc_id] for doc_id in docs},
        "counts": {
            "by_strength": dict(Counter(evidence[d]["strength"] for d in docs)),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True,
                        help="共享 runs 根目录,其中包含 runs/<workspace>/raw")
    parser.add_argument("--docile-root", type=Path, required=True,
                        help="dws-derisk 根目录,其中包含 data/docile/ocr")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--h2-ledger", type=Path, default=None)
    parser.add_argument("--workspace", action="append", dest="workspaces")
    parser.add_argument("--eval-n", type=int, default=30)
    args = parser.parse_args()
    workspace_names = args.workspaces or list(DEFAULT_WORKSPACES)
    result = build_scope(args.run_root, args.docile_root, workspace_names,
                         args.h2_ledger,
                         eval_n=args.eval_n)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "n_dual_mode_docs", "strong_n", "weak_n", "none_n", "evaluation_n",
        "development_n", "ood_n", "h2_excluded_n")}, ensure_ascii=False,
        indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
