#!/usr/bin/env python3
"""装配 ADK 行走轮(docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md)。

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
    assemble, discover_dual_mode, require_clean_code_revision, select_sources,
)
from invoiceloop import pipeline  # noqa: E402
from invoiceloop.harness import schema_digest  # noqa: E402
from invoiceloop.release_profile import document_touch_metrics  # noqa: E402
from invoiceloop.round_status import write_round_status  # noqa: E402
from invoiceloop.routing import policy_digest  # noqa: E402
from invoiceloop.sealed_batch import _corpus_environment, frozen_harness  # noqa: E402

LIST = REPO / "docs" / "qual_adk_walk_doc_list.json"
HAR_POLICY = REPO / "docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json"
HAR_SCHEMA = REPO / "invoiceloop/harnesses/HAR-0001/extraction_schema.json"
PROTOCOL = "docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md"


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


def _load_docs() -> list[str]:
    spec = json.loads(LIST.read_text(encoding="utf-8"))
    doc_ids = spec["doc_ids"]
    digest = hashlib.sha256("\n".join(doc_ids).encode("utf-8")).hexdigest()
    if digest != spec["doc_ids_sha256"]:
        raise SystemExit("fatal: 行走集名单 sha 不符,名单被改过")
    return doc_ids


def run_identity(active: dict, doc_ids: list[str], *, protocol_path: Path,
                 code_revision: str) -> dict:
    """Every input that licenses replay of the human-walk run."""
    protocol_path = Path(protocol_path)
    if not protocol_path.is_file():
        raise SystemExit(f"fatal: 行走协议不存在:{protocol_path}")
    return {
        "harness_id": active["harness_id"],
        "policy_digest": active["policy_digest"],
        "policy_sha256": active["policy_sha256"],
        "schema_sha256": active["schema_sha256"],
        "doc_ids_sha256": hashlib.sha256(
            "\n".join(doc_ids).encode("utf-8")).hexdigest(),
        "protocol": str(protocol_path),
        "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "code_revision": code_revision,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", type=Path,
                    default=REPO / "runs" / "qual-adk-walk")
    ap.add_argument("--no-crops", action="store_true")
    args = ap.parse_args()

    ws = args.workspace
    doc_ids = _load_docs()
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "doc_list.json").write_text(LIST.read_text(encoding="utf-8"),
                                      encoding="utf-8")
    status_action = write_round_status(ws, {
        "round": "qual-adk-walk",
        "status": "live",
        "harness_id": "HAR-0023",
        "protocol": PROTOCOL,
    })
    if status_action == "preserved_terminated":
        print("round_status 已是 terminated,setup 不复活")

    sources = select_sources(discover_dual_mode(), sorted(doc_ids))
    stats = assemble(ws, sources)
    if stats["missing"]:
        raise SystemExit(json.dumps(
            {"fatal": "语料缺失,协议要求缺响应换单不补抽",
             "missing": stats["missing"]}, ensure_ascii=False, indent=1))

    run_dir = ws / "runs" / "run-0001"
    active = _har0023_active()
    revision = require_clean_code_revision()
    identity = run_identity(
        active, doc_ids, protocol_path=REPO / PROTOCOL,
        code_revision=revision)
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
    else:
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
        "round": "qual-adk-walk",
        "docs": len(doc_ids),
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
            f"--run-dir {run_dir} --round qual-adk-walk-2026-08-25 "
            f"--frozen-at <ISO8601>",
        ],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
