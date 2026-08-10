#!/usr/bin/env python3
"""Build an allowlisted, aggregate-only broadcast development report."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from invoiceloop.scope import doc_ids_digest


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(scope_path: Path, run_specs: list[str]) -> dict[str, Any]:
    scope = _load(scope_path)
    development = list(scope.get("development_doc_ids") or [])
    if not development:
        raise ValueError("scope 没有 development_doc_ids")
    dev_set = set(development)
    route_counts = Counter()
    gate_counts = Counter()
    field_route_counts: dict[str, Counter] = defaultdict(Counter)
    field_gate_counts: dict[str, Counter] = defaultdict(Counter)
    doc_counts = Counter()
    runs = []

    for spec in run_specs:
        if "=" not in spec:
            raise ValueError(f"--run 必须是 LABEL=PATH:{spec}")
        label, raw_path = spec.split("=", 1)
        run_dir = Path(raw_path)
        routing = _load(run_dir / "routing_report.json")
        gate = _load(run_dir / "gate_report.json")
        manifest = _load(run_dir / "run_manifest.json")
        run_docs = dev_set & set(manifest.get("docs") or [])
        runs.append({"label": label, "path": str(run_dir), "n_docs": len(run_docs)})
        for row in routing.get("routes") or []:
            if row.get("doc_id") not in run_docs:
                continue
            field = str(row.get("field"))
            route = str(row.get("route"))
            route_counts[route] += 1
            field_route_counts[field][route] += 1
            doc_counts[row["doc_id"]] += route not in ("auto_accept", "auto_absent")
        for finding in gate.get("findings") or []:
            if finding.get("doc_id") not in run_docs:
                continue
            gate_id = str(finding.get("gate_id"))
            gate_counts[gate_id] += 1
            if finding.get("field"):
                field_gate_counts[str(finding["field"])][gate_id] += 1

    report = {
        "protocol": "broadcast-pilot-v1",
        "source": "deterministic_dev_replay_aggregate",
        "scope_path": str(scope_path),
        "development_n": len(development),
        "development_doc_ids_sha256": doc_ids_digest(development),
        "runs": runs,
        "aggregate": {
            "route_counts": dict(sorted(route_counts.items())),
            "gate_counts": dict(sorted(gate_counts.items())),
            "field_route_counts": {
                f: dict(sorted(c.items()))
                for f, c in sorted(field_route_counts.items())
            },
            "field_gate_counts": {
                f: dict(sorted(c.items()))
                for f, c in sorted(field_gate_counts.items())
            },
            "docs_with_any_review": sum(bool(v) for v in doc_counts.values()),
            "docs_seen": len(doc_counts),
        },
        "known_constraints": [
            "Gross/Net agency-commission convention remains applicability review.",
            "due_date must be explicitly printed; payment terms are not a value.",
            "EIN, FCC ID and station callsign are not seller_vat_id.",
            "The report contains no slot values, images, DocILE truth or model drafts.",
        ],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run", action="append", required=True,
                        help="LABEL=run directory; repeatable")
    args = parser.parse_args()
    report = build_report(args.scope, args.run)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(json.dumps({
        "development_n": report["development_n"],
        "docs_seen": report["aggregate"]["docs_seen"],
        "docs_with_any_review": report["aggregate"]["docs_with_any_review"],
        "gate_counts": report["aggregate"]["gate_counts"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
