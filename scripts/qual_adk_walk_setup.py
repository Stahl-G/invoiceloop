#!/usr/bin/env python3
"""装配 v2 ADK 行走轮(资格 FAIL 之后的独立人类问责证据)。

冻结 HAR-0023(payment_required_v1,TIER1 explicit off),与资格轮臂 D 同策略。
语料来自资格集的存盘响应 —— 走 doctouch_arms.assemble 而不是
hitl_round_setup._populate:后者的 RAW_WORKSPACES 是写死的四个目录,
不含 runs/qual-narrow-*。

不注入任何建议:建议由 hitl_adk_invoice_read.py 单独跑,跑完再冻结溯源。

**先提交本脚本再跑它。** snapshot._code_revision 用
`git status --porcelain --untracked-files=no` —— 未跟踪的文件不算脏,
拿一个没提交的 setup 起 run,input_manifest 会盖一个干干净净的 HEAD sha。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from doctouch_arms import (  # noqa: E402
    DERISK, assemble, discover_dual_mode, require_clean_code_revision,
    select_sources,
)
import qual_walk_plan  # noqa: E402
from invoiceloop import pipeline  # noqa: E402
from invoiceloop.harness import schema_digest  # noqa: E402
from invoiceloop.release_profile import document_touch_metrics  # noqa: E402
from invoiceloop.round_status import write_round_status  # noqa: E402
from invoiceloop.routing import policy_digest  # noqa: E402
from invoiceloop.sealed_batch import _corpus_environment, frozen_harness  # noqa: E402

LIST = REPO / "docs" / "qual_adk_walk_v2_doc_list.json"
HAR_POLICY = REPO / "docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json"
HAR_SCHEMA = REPO / "invoiceloop/harnesses/HAR-0001/extraction_schema.json"
PROTOCOL = REPO / "docs" / "QUAL_ADK_WALK_V2_PROTOCOL_2026-08-23.md"
ROUND = "qual-adk-walk-v2-2026-08-23"
WORKSPACE = REPO / "runs" / ROUND


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def _har0023_active() -> dict:
    policy = json.loads(HAR_POLICY.read_text(encoding="utf-8"))
    schema = json.loads(HAR_SCHEMA.read_text(encoding="utf-8"))
    return {
        "harness_id": "HAR-0023",
        "policy": policy,
        "policy_digest": policy_digest(policy),
        "policy_sha256": hashlib.sha256(HAR_POLICY.read_bytes()).hexdigest(),
        "schema": schema,
        "schema_digest": schema_digest(schema),
        "schema_sha256": hashlib.sha256(HAR_SCHEMA.read_bytes()).hexdigest(),
    }


def _load_docs(list_path: Path, *, expected_round: str) -> tuple[dict, list[str]]:
    spec = json.loads(Path(list_path).read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise SystemExit("fatal: 行走名单顶层必须是 object")
    doc_ids = spec.get("doc_ids")
    if (not isinstance(doc_ids, list) or len(doc_ids) != 20
            or len(set(doc_ids)) != len(doc_ids)
            or not all(isinstance(doc, str) and doc for doc in doc_ids)
            or doc_ids != sorted(doc_ids)
            or spec.get("n") != len(doc_ids)):
        raise SystemExit("fatal: 行走名单必须是 20 个排序、唯一的 doc_id")
    digest = hashlib.sha256("\n".join(doc_ids).encode("utf-8")).hexdigest()
    if digest != spec["doc_ids_sha256"]:
        raise SystemExit("fatal: 行走集名单 sha 不符,名单被改过")
    if spec.get("round") != expected_round:
        raise SystemExit(
            f"fatal: 行走名单 round={spec.get('round')!r},"
            f"命令 round={expected_round!r}")
    for key in ("qualification_decision", "qualification_decision_sha256",
                "source", "source_sha256", "source_input_manifest",
                "source_input_manifest_sha256", "planner_code_revision"):
        if not spec.get(key):
            raise SystemExit(f"fatal: 行走名单缺身份字段:{key}")
    return spec, doc_ids


def verify_corpus_sources(sources: dict[str, Path], doc_ids: list[str],
                          input_manifest_path: Path) -> str:
    """Bind the copied PDF/OCR/raw bytes to the frozen qualification D arm."""
    manifest = json.loads(Path(input_manifest_path).read_text(encoding="utf-8"))
    expected = {str(row.get("doc_id")): row
                for row in (manifest.get("docs") or [])}
    failures = []
    selected = []
    for doc_id in sorted(doc_ids):
        row = expected.get(doc_id)
        root = sources.get(doc_id)
        if not isinstance(row, dict) or root is None:
            failures.append(f"{doc_id}:不在冻结 input manifest 或没有双模式来源")
            continue
        checks = {
            "pdf_sha256": (DERISK / "data/docile/pdfs" / f"{doc_id}.pdf",
                           row.get("pdf_sha256")),
            "ocr_sha256": (DERISK / "data/docile/ocr" / f"{doc_id}.json",
                           row.get("ocr_sha256")),
            "raw_understand_sha256":
                (root / f"{doc_id}.understand.json",
                 (row.get("raw_sha256") or {}).get("understand")),
            "raw_agentic_sha256":
                (root / f"{doc_id}.agentic.json",
                 (row.get("raw_sha256") or {}).get("agentic")),
        }
        for label, (path, want) in checks.items():
            got = _sha(path) if path.is_file() else None
            if not want or got != want:
                failures.append(
                    f"{doc_id}:{label}:expected={want},actual={got},path={path}")
        selected.append(row)
    if failures:
        raise SystemExit(json.dumps({
            "fatal": "行走语料与冻结 qualification input manifest 不一致",
            "failures": failures,
        }, ensure_ascii=False, indent=1))
    return hashlib.sha256(json.dumps(
        selected, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def run_identity(active: dict, doc_ids: list[str], *, round_name: str,
                 protocol_path: Path, doc_list_path: Path,
                 qualification_decision_path: Path,
                 qualification_input_manifest_path: Path,
                 selected_corpus_sha256: str, code_revision: str) -> dict:
    """Every input that licenses replay of the human-walk run."""
    protocol_path = Path(protocol_path)
    if not protocol_path.is_file():
        raise SystemExit(f"fatal: 行走协议不存在:{protocol_path}")
    return {
        "round": round_name,
        "harness_id": active["harness_id"],
        "policy_digest": active["policy_digest"],
        "policy_sha256": active["policy_sha256"],
        "schema_sha256": active["schema_sha256"],
        "doc_ids_sha256": hashlib.sha256(
            "\n".join(doc_ids).encode("utf-8")).hexdigest(),
        "doc_list": qual_walk_plan.repo_rel(doc_list_path),
        "doc_list_sha256": _sha(doc_list_path),
        "qualification_decision":
            qual_walk_plan.repo_rel(qualification_decision_path),
        "qualification_decision_sha256": _sha(qualification_decision_path),
        "qualification_input_manifest":
            qual_walk_plan.repo_rel(qualification_input_manifest_path),
        "qualification_input_manifest_sha256":
            _sha(qualification_input_manifest_path),
        "selected_corpus_sha256": selected_corpus_sha256,
        "protocol": qual_walk_plan.repo_rel(protocol_path),
        "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "code_revision": code_revision,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", type=Path, default=WORKSPACE)
    ap.add_argument("--doc-list", type=Path, default=LIST)
    ap.add_argument("--protocol", type=Path, default=PROTOCOL)
    ap.add_argument("--round", dest="round_name", default=ROUND)
    ap.add_argument("--no-crops", action="store_true")
    args = ap.parse_args()

    ws = args.workspace
    list_path = args.doc_list.resolve()
    protocol_path = args.protocol.resolve()
    revision = require_clean_code_revision()
    spec, doc_ids = _load_docs(list_path, expected_round=args.round_name)
    decision_path = _resolve_repo_path(spec["qualification_decision"]).resolve()
    routing_path = _resolve_repo_path(spec["source"]).resolve()
    input_manifest_path = _resolve_repo_path(
        spec["source_input_manifest"]).resolve()
    try:
        qual_walk_plan.require_committed([
            list_path, protocol_path, decision_path,
            routing_path, input_manifest_path])
        binding = qual_walk_plan.qualification_binding(
            routing_path, input_manifest_path, decision_path)
    except ValueError as exc:
        raise SystemExit(f"fatal: {exc}") from exc
    expected_from_list = {
        "qualification_decision_sha256": spec["qualification_decision_sha256"],
        "source_routing_sha256": spec["source_sha256"],
        "source_input_manifest_sha256": spec["source_input_manifest_sha256"],
        "qualification_status": spec.get("qualification_status"),
        "qualification_promotion": spec.get("qualification_promotion"),
    }
    mismatch = {key: {"list": expected_from_list[key], "live": binding[key]}
                for key in expected_from_list
                if expected_from_list[key] != binding[key]}
    if mismatch:
        raise SystemExit(json.dumps({
            "fatal": "行走名单绑定的 qualification 来源已漂移",
            "mismatch": mismatch,
        }, ensure_ascii=False, indent=1))
    sources = select_sources(discover_dual_mode(), sorted(doc_ids))
    corpus_sha = verify_corpus_sources(
        sources, doc_ids, input_manifest_path)
    active = _har0023_active()
    identity = run_identity(
        active, doc_ids, round_name=args.round_name,
        protocol_path=protocol_path, doc_list_path=list_path,
        qualification_decision_path=decision_path,
        qualification_input_manifest_path=input_manifest_path,
        selected_corpus_sha256=corpus_sha, code_revision=revision)
    run_dir = ws / "runs" / "run-0001"
    id_path = run_dir / "run_identity.json"
    if run_dir.exists():
        # 「目录在就重放」会把上一次用别的策略/名单跑出来的东西当成这一次的。
        # doctouch_arms 的臂目录踩过同一个坑,这里同样处理。
        prior = json.loads(id_path.read_text(encoding="utf-8")) \
            if id_path.is_file() else None
        if prior != identity:
            raise SystemExit(json.dumps({
                "fatal": "run 已存在,但策略/schema/名单与本次不同 —— "
                         "复用它会把上一次的结果当成这一次的",
                "prior": prior, "now": identity,
            }, ensure_ascii=False, indent=1))
        print(f"run 已存在且身份一致,重放:{run_dir}")

    # No workspace write occurs before all committed identities and source bytes pass.
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "doc_list.json").write_text(list_path.read_text(encoding="utf-8"),
                                      encoding="utf-8")
    status_action = write_round_status(ws, {
        "round": args.round_name,
        "status": "live",
        "harness_id": "HAR-0023",
        "protocol": qual_walk_plan.repo_rel(protocol_path),
        "qualification_status": binding["qualification_status"],
        "qualification_promotion": binding["qualification_promotion"],
    })
    if status_action == "preserved_terminated":
        print("round_status 已是 terminated,setup 不复活")
    stats = assemble(ws, sources)
    if stats["missing"]:
        raise SystemExit(json.dumps(
            {"fatal": "语料缺失,协议要求缺响应换单不补抽",
             "missing": stats["missing"]}, ensure_ascii=False, indent=1))

    if not run_dir.exists():
        with _corpus_environment(ws), frozen_harness(active):
            pipeline.run(doc_ids, run_dir,
                         render_crops=not args.no_crops,
                         include_vision=False, out_of_calibration=True)
        id_path.write_text(
            json.dumps(identity, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    run_manifest = json.loads(
        (run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    if run_manifest.get("code_revision") != revision:
        raise SystemExit(json.dumps({
            "fatal": "行走 run 的 code revision 与当前身份不同",
            "identity": revision,
            "run_manifest": run_manifest.get("code_revision"),
        }, ensure_ascii=False, indent=1))

    (ws / "runs" / "current.json").write_text(
        json.dumps({"run": "run-0001"}) + "\n", encoding="utf-8")
    routing = json.loads((run_dir / "routing_report.json").read_text())
    print(json.dumps({
        "round": args.round_name,
        "docs": len(doc_ids),
        "qualification": {
            "status": binding["qualification_status"],
            "promotion": binding["qualification_promotion"],
        },
        "corpus": {"docs": stats["docs"]},
        "run": str(run_dir),
        "harness_id": routing.get("harness_id"),
        "touch": document_touch_metrics(routing["routes"], routing["policy"]),
        "next": [
            f".venv/bin/python scripts/writeset.py snapshot "
            f"--run-dir {run_dir} --out {ws}/writeset_before.json",
            f".venv/bin/python scripts/hitl_adk_invoice_read.py --run-dir {run_dir}",
            f".venv/bin/python scripts/writeset.py diff --run-dir {run_dir} "
            f"--before {ws}/writeset_before.json "
            f"--out {run_dir}/agent_writeset.json",
            f".venv/bin/python scripts/suggest_provenance_freeze.py "
            f"--run-dir {run_dir} --round {args.round_name} "
            f"--frozen-at <ISO8601>",
        ],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
