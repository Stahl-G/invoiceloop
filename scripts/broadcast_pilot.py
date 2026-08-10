#!/usr/bin/env python3
"""Run the frozen broadcast schema pilot.

The baseline reuses existing public DocILE/DWS raw responses.  The candidate
alone makes new DWS calls, then both arms run the same deterministic pipeline
in isolated temporary workspaces.  No active harness or SEALED artifact is
modified.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from invoiceloop import harness, ocr, pipeline
from invoiceloop.dws_client import extract
from invoiceloop.due_date import derive_due_date_file
from invoiceloop.eval_norm import eval_normalise
from invoiceloop.fields import FIELD_KINDS
from invoiceloop.ingest import default_extraction_schema
from invoiceloop.scope import (BROADCAST_DOMAIN, SCOPE_VERSION, build_scope,
                               require_workspace_scope)
from invoiceloop.sealed_batch import frozen_harness

MODES = ("understand", "agentic")
AUTO_ROUTES = {"auto_accept", "auto_absent"}
RAW_DUE_DATE_SUFFIX = (
    " Keep this raw field limited to a date printed on the page; a date "
    "derived from payment terms belongs in the separate deterministic "
    "calculated_due_date artifact."
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _raw_source(run_root: Path, doc_id: str, mode: str) -> Path:
    for workspace in (
        "sealed1-workspace", "sealed2-workspace", "heldout-workspace",
        "sealed3-workspace", "absence-dev-corpus",
    ):
        path = run_root / "runs" / workspace / "raw" / f"{doc_id}.{mode}.json"
        if path.is_file():
            return path
    raise FileNotFoundError(f"没有找到 {doc_id}.{mode}.json 的存盘 raw")


def _prepare_workspace(
    target: Path,
    doc_ids: list[str],
    *,
    run_root: Path,
    docile_root: Path,
    include_raw: bool = True,
) -> None:
    (target / "input" / "pdfs").mkdir(parents=True, exist_ok=True)
    (target / "ocr").mkdir(parents=True, exist_ok=True)
    (target / "raw").mkdir(parents=True, exist_ok=True)
    for doc_id in doc_ids:
        source_ocr = docile_root / "data" / "docile" / "ocr" / f"{doc_id}.json"
        if not source_ocr.is_file():
            raise FileNotFoundError(f"缺少 DocILE OCR:{source_ocr}")
        shutil.copyfile(source_ocr, target / "ocr" / f"{doc_id}.json")
        if include_raw:
            for mode in MODES:
                shutil.copyfile(_raw_source(run_root, doc_id, mode),
                                target / "raw" / f"{doc_id}.{mode}.json")


def _candidate_schema(draft: dict[str, Any]) -> dict[str, Any]:
    if draft.get("status") == "blocking" or not draft.get("draft"):
        raise RuntimeError("ADK draft 是 blocking,不允许继续重抽")
    descriptions = (draft["draft"] or {}).get("descriptions") or {}
    schema = default_extraction_schema()
    if set(descriptions) != set(schema["properties"]):
        raise ValueError("ADK draft 与十字段 schema 集合不一致")
    for field, description in descriptions.items():
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"ADK draft 的 {field} description 为空")
        schema["properties"][field]["description"] = (
            description.strip() + RAW_DUE_DATE_SUFFIX
            if field == "due_date" else description.strip()
        )
    return schema


def _active_with_schema(schema: dict[str, Any], *, scoped: bool) -> dict[str, Any]:
    active = harness.load_active()
    active = copy.deepcopy(active)
    active["harness_id"] = "HAR-BROADCAST-PILOT" if scoped else "HAR-GENERIC-PILOT"
    active["schema"] = schema
    active["schema_digest"] = harness.schema_digest(schema)
    active["schema_sha256"] = active["schema_digest"]
    if scoped:
        active["policy"]["domain_scope"] = {
            "scope_version": SCOPE_VERSION,
            "domain": BROADCAST_DOMAIN,
        }
    active["policy"]["harness_id"] = active["harness_id"]
    active["policy_digest"] = __import__("invoiceloop.routing",
                                          fromlist=["policy_digest"]).policy_digest(
                                              active["policy"])
    active["policy_sha256"] = active["policy_digest"]
    return active


def _truth(docile_root: Path, doc_id: str) -> dict[str, str]:
    path = docile_root / "data" / "docile" / "annotations" / f"{doc_id}.json"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    mapping = {
        "document_id": "invoice_number", "date_issue": "issue_date",
        "date_due": "due_date", "vendor_name": "seller_name",
        "vendor_tax_id": "seller_vat_id", "customer_billing_name": "buyer_name",
        "amount_total_net": "total_net", "amount_total_tax": "total_vat",
        "amount_total_gross": "total_gross", "amount_due": "amount_due",
    }
    for item in (_json(path).get("field_extractions") or []):
        field = mapping.get(item.get("fieldtype"))
        if field and item.get("text"):
            out.setdefault(field, item["text"])
    return out


def _understand(workspace: Path, doc_id: str) -> dict[str, Any]:
    body = _json(workspace / "raw" / f"{doc_id}.understand.json").get("body") or {}
    output = body.get("output") or {}
    return output.get("data") or {}


def _score(run_dir: Path, workspace: Path, docile_root: Path,
           doc_ids: list[str]) -> dict[str, Any]:
    routing = _json(run_dir / "routing_report.json")
    deliverable = _json(run_dir / "deliverable.json")
    routes = [row for row in routing.get("routes") or []
              if row.get("doc_id") in set(doc_ids)]
    counts = Counter()
    for row in routes:
        route = row.get("route")
        field = row.get("field")
        truth = _truth(docile_root, row["doc_id"]).get(field)
        got = _understand(workspace, row["doc_id"]).get(field)
        if route not in AUTO_ROUTES:
            counts["review_slots"] += 1
            continue
        if route == "auto_absent":
            counts["absent_hits"] += 1
            if truth is not None:
                counts["silent_absent"] += 1
            continue
        if truth is not None and got is not None and field in FIELD_KINDS:
            counts["value_hits"] += 1
            if eval_normalise(truth, FIELD_KINDS[field]) != eval_normalise(
                    got, FIELD_KINDS[field]):
                counts["silent_wrong"] += 1
    summary = deliverable.get("summary") or {}
    touched = sum(
        1 for doc_id in doc_ids
        if any(row["doc_id"] == doc_id and row.get("route") not in AUTO_ROUTES
               for row in routes)
    )
    counts.update({
        "decision_slots_for_release": summary.get("decision_slots_for_release"),
        "decision_load_for_release": summary.get("decision_load_for_release"),
        "docs_touched": touched,
        "docs": len(doc_ids),
        "routes": len(routes),
    })
    return dict(counts)


def _derive_due_dates(workspace: Path, doc_ids: list[str]) -> dict[str, Any]:
    """Write the separate page-derived due-date artifact for a pilot arm."""
    records = {
        doc_id: derive_due_date_file(workspace / "ocr" / f"{doc_id}.json")
        for doc_id in sorted(doc_ids)
    }
    payload = {
        "artifact": "calculated_due_dates.json",
        "derivation_version": "due-date-relative-term-v1",
        "raw_due_date_semantics": (
            "raw DWS due_date remains explicit-page-date only; it is not overwritten"
        ),
        "records": records,
        "summary": {
            "docs": len(records),
            "computed": sum(r["status"] == "computed" for r in records.values()),
            "not_computable": sum(r["status"] == "not_computable" for r in records.values()),
        },
    }
    _write(workspace / "calculated_due_dates.json", payload)
    return payload


def _run_pipeline(workspace: Path, doc_ids: list[str], active: dict[str, Any]) -> Path:
    os.environ["INVOICELOOP_CORPUS"] = str(workspace)
    os.environ["INVOICELOOP_DWS_DERISK"] = str(workspace)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    run_dir = workspace / "runs" / "run-0001"
    with frozen_harness(active):
        pipeline.run(doc_ids, run_dir, include_vision=False,
                     out_of_calibration=True)
    return run_dir


def _extract_candidate(doc_ids: list[str], workspace: Path, schema: dict[str, Any],
                       docile_root: Path, *, budget: float) -> dict[str, Any]:
    from invoiceloop.env import credential

    key = credential("dws", workspace=Path("/Users/yihongguo/Developer/invoiceloop"))
    if not key:
        raise RuntimeError("DWS credential 不可用;未开始候选重抽")
    spent = 0.0
    completed: list[dict[str, Any]] = []
    for doc_id in doc_ids:
        pdf = docile_root / "data" / "docile" / "pdfs" / f"{doc_id}.pdf"
        if not pdf.is_file():
            completed.append({"doc_id": doc_id, "status": "blocking",
                              "reason": "pdf_missing"})
            continue
        for mode in MODES:
            if spent >= budget:
                completed.append({"doc_id": doc_id, "mode": mode,
                                  "status": "blocking", "reason": "budget_cap"})
                continue
            try:
                # One identical transport retry is enforced inside extract.
                record = extract(pdf, schema, doc_id=doc_id, mode=mode,
                                 api_key=key, retries=1)
                target = workspace / "raw" / f"{doc_id}.{mode}.json"
                _write(target, record)
                usage = (record.get("body") or {}).get("usage") or {}
                cost = float((usage.get("data_extraction_credits") or {}).get(
                    "cost") or 0.0)
                spent += cost
                completed.append({"doc_id": doc_id, "mode": mode,
                                  "status": "ok" if record.get("http_status") == 200
                                  else "http_error", "credits": cost,
                                  "http_status": record.get("http_status")})
            except Exception as exc:  # preserve the failure and continue inventory
                completed.append({"doc_id": doc_id, "mode": mode,
                                  "status": "blocking",
                                  "reason": f"{type(exc).__name__}: {exc}"})
    return {"credits_spent": spent, "budget": budget,
            "completed": completed,
            "complete_pairs": sum(
                all(any(x.get("doc_id") == d and x.get("mode") == m
                        and x.get("status") == "ok" for x in completed)
                    for m in MODES) for d in doc_ids)}


def run_pilot(scope_path: Path, draft_path: Path, *, run_root: Path,
              docile_root: Path, out_root: Path, result_path: Path,
              budget: float = 2000.0) -> dict[str, Any]:
    scope = _json(scope_path)
    doc_ids = list(scope.get("evaluation_doc_ids") or [])
    if len(doc_ids) != 30 or len(set(doc_ids)) != 30:
        raise ValueError("广播 pilot 必须是冻结的 30 份评估名单")
    draft = _json(draft_path)
    schema = _candidate_schema(draft)
    baseline_ws = out_root / "baseline"
    candidate_ws = out_root / "candidate"
    ood_ws = out_root / "ood-generic"
    for path in (baseline_ws, candidate_ws, ood_ws):
        if path.exists() and any(path.iterdir()):
            raise FileExistsError(f"实验输出目录已存在且非空:{path}")
    _prepare_workspace(baseline_ws, doc_ids, run_root=run_root,
                       docile_root=docile_root)
    _prepare_workspace(candidate_ws, doc_ids, run_root=run_root,
                       docile_root=docile_root, include_raw=False)
    candidate_scope = build_scope(
        BROADCAST_DOMAIN, doc_ids, approved_by="user-authorized-execution",
        approved_at="2026-08-10", evidence_basis="frozen_broadcast_pilot_v1")
    _write(candidate_ws / "domain_scope.json", candidate_scope)
    baseline_derived = _derive_due_dates(baseline_ws, doc_ids)
    candidate_derived = _derive_due_dates(candidate_ws, doc_ids)
    candidate_active = _active_with_schema(schema, scoped=True)
    baseline_active = _active_with_schema(default_extraction_schema(), scoped=False)
    extraction = _extract_candidate(doc_ids, candidate_ws, schema, docile_root,
                                    budget=budget)
    candidate_run = None
    baseline_run = None
    if extraction["complete_pairs"] == len(doc_ids):
        baseline_run = _run_pipeline(baseline_ws, doc_ids, baseline_active)
        candidate_run = _run_pipeline(candidate_ws, doc_ids, candidate_active)

    scope_ood = _json(scope_path).get("ood_doc_ids") or []
    _prepare_workspace(ood_ws, scope_ood, run_root=run_root,
                       docile_root=docile_root)
    ood_run = _run_pipeline(ood_ws, scope_ood, baseline_active)
    try:
        require_workspace_scope(candidate_ws, scope_ood, BROADCAST_DOMAIN)
    except ValueError as exc:
        ood_scope_blocked = {"blocked": True, "reason": str(exc)}
    else:
        ood_scope_blocked = {"blocked": False}

    result: dict[str, Any] = {
        "protocol": "broadcast-pilot-v1",
        "status": "complete" if candidate_run else "incomplete",
        "scope_sha256": hashlib.sha256(scope_path.read_bytes()).hexdigest(),
        "adk_draft_sha256": hashlib.sha256(draft_path.read_bytes()).hexdigest(),
        "evaluation_n": len(doc_ids),
        "candidate_schema_digest": harness.schema_digest(schema),
        "candidate_policy_digest": candidate_active["policy_digest"],
        "extraction": extraction,
        "baseline_run": str(baseline_run) if baseline_run else None,
        "candidate_run": str(candidate_run) if candidate_run else None,
        "ood_run": str(ood_run),
        "derived_due_dates": {
            "baseline": baseline_derived["summary"],
            "candidate": candidate_derived["summary"],
        },
        "ood_scope_check": ood_scope_blocked,
        "metrics": {
            "baseline": _score(baseline_run, baseline_ws, docile_root, doc_ids)
            if baseline_run else None,
            "candidate": _score(candidate_run, candidate_ws, docile_root, doc_ids)
            if candidate_run else None,
            "ood_generic": _score(ood_run, ood_ws, docile_root, scope_ood),
        },
        "claims": {
            "human_accuracy": "NOT_MEASURED",
            "ood_schema_transfer": "NOT_MEASURED",
            "scope": "paired exploratory pilot on previously stored public DocILE documents",
        },
    }
    _write(result_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--docile-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--budget", type=float, default=2000.0)
    args = parser.parse_args()
    result = run_pilot(args.scope, args.draft, run_root=args.run_root,
                       docile_root=args.docile_root, out_root=args.out_root,
                       result_path=args.result, budget=args.budget)
    print(json.dumps({
        "status": result["status"],
        "extraction": {k: result["extraction"].get(k)
                       for k in ("credits_spent", "complete_pairs")},
        "metrics": result["metrics"],
        "ood_scope_check": result["ood_scope_check"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
