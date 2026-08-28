"""CLI: python -m invoiceloop ...

run         full pipeline from stored evidence (zero API)
adjudicate  append one human decision
bundle      build audit_bundle.zip
doctor      environment self-check (missing product-path dependency → exit 1)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import dws
from .heldout import DEFAULT_SEALED_CONTEXT as _DEFAULT_SEALED_CONTEXT
from .heldout import SEALED_CONTEXTS as _SEALED_CONTEXTS
from .heldout import SEALED_SCOPES as _SEALED_SCOPES
from .heldout import DEFAULT_QUAL_CONTEXT as _DEFAULT_QUAL_CONTEXT
from .heldout import QUAL_CONTEXTS as _QUAL_CONTEXTS


def _main() -> None:
    parser = argparse.ArgumentParser(prog="invoiceloop")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="extract → freeze → gates → matrix → panel")
    p_run.add_argument("--docs", type=int, default=None, help="run only the first N documents (default: all stored documents)")
    p_run.add_argument("--doc-ids", nargs="*", default=None, help="explicit list of doc_ids")
    p_run.add_argument("--out", type=Path, default=None, help="run directory (unused with --workspace)")
    p_run.add_argument("--workspace", type=Path, default=None,
                       help="input-contract workspace: reads ws/raw + ws/ocr + ws/input/pdfs, writes ws/output")
    p_run.add_argument("--crops", action="store_true", help="render evidence crops (needs poppler + the PDF corpus)")
    p_run.add_argument("--no-vision", action="store_true", help="do not merge the round-six vision answers")
    p_run.add_argument("--new-run", action="store_true",
                       help="open a new run even if input is unchanged (default: replay the run with the same fingerprint; old runs are never touched)")

    p_ing = sub.add_parser("ingest", help="input contract: input/pdfs -> ocr/ + raw/")
    p_ing.add_argument("--workspace", type=Path, required=True)
    p_ing.add_argument("--no-ocr", action="store_true", help="skip local independent OCR")
    p_ing.add_argument("--no-extract", action="store_true", help="skip DWS extraction (produce OCR only)")
    p_ing.add_argument(
        "--adaptive", action="store_true",
        help="L1 opt-in: run understand first, call agentic only for risky documents "
             "(default: both modes for all; do not enable in sealed evaluations)",
    )

    p_adj = sub.add_parser("adjudicate", help="append one human adjudication (panel is then re-rendered)")
    p_adj.add_argument("--run", type=Path, required=True)
    p_adj.add_argument("--doc", required=True)
    p_adj.add_argument("--field", required=True)
    p_adj.add_argument("--claim-id", default=None)
    p_adj.add_argument("--decision", required=True)
    p_adj.add_argument("--rationale", required=True)
    p_adj.add_argument("--adjudicator", required=True)
    p_adj.add_argument("--decided-at", required=True, help="ISO timestamp, supplied by a human")
    p_adj.add_argument("--corrected-value", default=None,
                       help="required when decision=correct, forbidden otherwise")
    # 反馈平面(v0.2 §5.2)此前只有网页表单能填 —— 改进循环在命令行上
    # 不可测、不可脚本化。两个都是可选:不给就是不给,系统不代填
    p_adj.add_argument("--reason-code", default=None,
                       help="one of the minimal reason codes (optional; legal combinations with the decision are validated)")
    p_adj.add_argument("--reviewer-confidence", default=None,
                       choices=["high", "medium", "low"],
                       help="mark low only when unsure — leaving it empty does not affect mining eligibility")
    p_adj.add_argument("--supersedes", dest="supersedes_decision_id", default=None,
                       help="required when this slot already has a decision: the current tip decision_id")

    p_app = sub.add_parser(
        "approve",
        help="approve one document for export (the final step after every slot is dealt with; only a human can do it)")
    p_app.add_argument("--run", type=Path, required=True)
    p_app.add_argument("--doc", required=True)
    p_app.add_argument("--approved-by", required=True, help="signature; the system never signs on your behalf")
    p_app.add_argument("--rationale", required=True, help="approval rationale; enters the audit trail")
    p_app.add_argument("--approved-at", required=True, help="ISO timestamp, supplied by a human")

    p_ren = sub.add_parser("render", help="re-render the panel from on-disk artifacts (pure projection, recomputable)")
    p_ren.add_argument("--run", type=Path, required=True)

    p_bun = sub.add_parser("bundle", help="build audit_bundle.zip (fully self-contained)")
    p_bun.add_argument("--run", type=Path, required=True)

    p_ver = sub.add_parser("verify", help="verify an audit bundle offline (members/snapshot/binding/semantics/signature)")
    p_ver.add_argument("bundle", type=Path)

    p_seal = sub.add_parser("seal", help="have DWS countersign an audit bundle (needs NUTRIENT_API_KEY)")
    p_seal.add_argument("--run", type=Path, required=True)

    p_carry = sub.add_parser("carry", help="carry adjudications across runs on identical evidence: from the old run into the latest")
    p_carry.add_argument("--run", type=Path, required=True)
    p_carry.add_argument("--decided-at", default=None,
                         help="ISO timestamp (default: current UTC — running carry is a human supplying the time)")

    p_wb = sub.add_parser("workbench", help="H1 review workbench (default 127.0.0.1; use --host 0.0.0.0 on Cloud Run)")
    p_wb.add_argument("--workspace", type=Path, required=True)
    p_wb.add_argument("--port", type=int, default=None,
                      help="defaults to the PORT env var (Cloud Run), else 8765")
    p_wb.add_argument("--host", default="127.0.0.1",
                      help="bind address; pass 0.0.0.0 in containers/Cloud Run")
    p_wb.add_argument("--allowed-host", action="append", default=[],
                      dest="allowed_hosts",
                      help="optional Host allowlist when binding publicly (repeatable; .run.app suffix supported)")
    p_wb.add_argument("--read-only", action="store_true",
                      help="reject every POST (403). Required for public demos — the adjudication ledger is "
                           "human testimony; a writable public endpoint would allow forging it")
    p_wb.add_argument(
        "--review-scope", type=Path, default=None,
        help="JSON slot allowlist ({slots:[doc|field,...]}): constrains queue, navigation, and "
             "the adjudication write path at once; used for sampled review")

    p_demo = sub.add_parser("demo", help="vendored sample corpus -> a full run (zero API, zero external data)")
    p_demo.add_argument("--out", type=Path, required=True, help="demo workspace target (must not exist or be empty)")

    p_vis = sub.add_parser("vision", help="vision ingest: full-page renders -> a vision model answering -> vision/answers6 tsv")
    p_vis.add_argument("--workspace", type=Path, required=True)
    p_vis.add_argument(
        "--tag", default=None,
        help="reader tag for older artifacts; default is the real model name of the final call",
    )
    p_vis.add_argument(
        "--model", default=None,
        help="vision model; defaults to ANTHROPIC_MODEL, failing explicitly if unset",
    )
    p_vis.add_argument("--api-key", default=None, help="defaults to ANTHROPIC_API_KEY")

    sub.add_parser("doctor", help="environment self-check: poppler/tesseract/requests/research data")

    p_ho = sub.add_parser("heldout", help="held-out set (docs/HELDOUT.md)")
    ho_sub = p_ho.add_subparsers(dest="heldout_command", required=True)
    p_hop = ho_sub.add_parser("plan", help="generate and write the list to disk (before any call)")
    p_hop.add_argument("--workspace", type=Path, required=True)
    p_hop.add_argument("--n", type=int, default=100)
    p_hoe = ho_sub.add_parser("extract", help="run both modes over the list, resumable, with a budget breaker")
    p_hoe.add_argument("--workspace", type=Path, required=True)
    p_hoe.add_argument("--budget", type=float, default=6000.0)

    p_se = sub.add_parser(
        "sealed", help="sealed held-out set (docs/SEALED3_PROTOCOL.md; use the matching --context to recompute an old batch)")
    se_sub = p_se.add_subparsers(dest="sealed_command", required=True)
    p_sep = se_sub.add_parser("plan", help="seed-sample and write the list to disk (before any call)")
    p_sep.add_argument("--workspace", type=Path, required=True)
    p_sep.add_argument("--seed", required=True,
                       help="hexadecimal entropy from an external randomness source (drand round randomness)")
    p_sep.add_argument("--seed-source", required=True,
                       help="commitment identifier of the randomness source (protocol doc + round)")
    # 语境词表只有一处权威(heldout.SEALED_CONTEXTS)。这里原先手抄了一份,
    # 于是加 sealed4-v1 时 CLI 不认 —— 抄一份就会有一天两份不一样。
    p_sep.add_argument("--context", default=_DEFAULT_SEALED_CONTEXT,
                       choices=tuple(sorted(_SEALED_CONTEXTS)),
                       help=f"PRNG context (default {_DEFAULT_SEALED_CONTEXT})")
    p_sep.add_argument("--scope", default=None,
                       choices=tuple(sorted(_SEALED_SCOPES)),
                       help="scope filter: sample from that scope sub-pool when given (e.g. broadcast-pilot-v1, "
                            "SEALED-4 addendum A1); default is the full pool")
    p_sep.add_argument("--n", type=int, default=100)
    p_see = se_sub.add_parser("extract", help="run both modes over the list, resumable, with a budget breaker")
    p_see.add_argument("--workspace", type=Path, required=True)
    p_see.add_argument("--budget", type=float, default=6000.0)

    p_q = sub.add_parser(
        "qualify",
        help="qualification set (unexposed confirmation round; docs/QUALIFICATION_NARROW_PROTOCOL_*.md)")
    q_sub = p_q.add_subparsers(dest="qualify_command", required=True)
    p_qp = q_sub.add_parser("plan", help="min-hash sample and write the list to disk (before any call)")
    p_qp.add_argument("--workspace", type=Path, required=True)
    p_qp.add_argument("--n", type=int, default=200)
    p_qp.add_argument("--context", default=_DEFAULT_QUAL_CONTEXT,
                      choices=tuple(sorted(_QUAL_CONTEXTS)),
                      help=f"sampling salt context (default {_DEFAULT_QUAL_CONTEXT})")
    p_qe = q_sub.add_parser("extract", help="run both modes over the list, resumable, with a budget breaker")
    p_qe.add_argument("--workspace", type=Path, required=True)
    p_qe.add_argument("--budget", type=float, default=6000.0)
    p_qe.add_argument("--round", required=True,
                      help="frozen evidence round name (used to look up the plan manifest)")
    p_qe.add_argument("--protocol", type=Path, required=True,
                      help="frozen protocol that is committed and listed in the plan manifest")

    # suggest 刻意**不在** improve 之下:改进控制面仍是全确定性零模型,
    # 顾问层旁挂,输出 advisory 草稿,采纳与否走人 —— 与 vision 同款位置
    p_sg = sub.add_parser("suggest", help="advisory layer: a model reads review notes and drafts proposals (needs human review)")
    p_sg.add_argument("--workspace", type=Path, required=True)
    p_sg.add_argument("--model", default=None)

    p_un = sub.add_parser(
        "unattended",
        help="Arm U experimental arm: clerk->critic->policy gate->approver, unattended "
             "adjudication + approval (explicit opt-in, not the product default; the "
             "default path still requires a human signature to approve)")
    p_un.add_argument("--run", type=Path, required=True,
                      help="an existing run directory (adjudications and approvals append to its ledgers)")
    p_un.add_argument("--model", default=None,
                      help="defaults to gemini-3.7-flash; INVOICELOOP_REPLAY=1 uses recordings")
    p_un.add_argument("--decided-at", required=True,
                      help="ISO timestamp, injected by the operator/job trigger — artifacts never read the wall clock")
    p_un.add_argument("--docs", nargs="*", default=None,
                      help="process only these doc_ids (default: every review slot in the run)")
    p_un.add_argument("--gcloud-oauth-project", default=None,
                      help="in-memory gcloud OAuth + the Vertex AI endpoint (a demo/acceptance "
                           "credential route; the token never touches disk, see agents/vertex_oauth.py)")

    p_ag = sub.add_parser(
        "agents", help="ADK layer: the improvement loop executed by a Runner (advice only, never writes a ledger)")
    ag_sub = p_ag.add_subparsers(dest="agents_command", required=True)
    p_agl = ag_sub.add_parser(
        "improve-loop",
        help="run the ADK SequentialAgent (miner->proposer->evaluator->critic)")
    p_agl.add_argument("--workspace", type=Path, required=True)
    p_agl.add_argument("--model", default=None,
                       help="defaults to gemini-3.7-flash; INVOICELOOP_REPLAY=1 uses recordings")

    p_imp = sub.add_parser("improve", help="improvement control plane (v0.2 narrowed, fully deterministic, zero models)")
    imp_sub = p_imp.add_subparsers(dest="improve_command", required=True)
    p_im = imp_sub.add_parser("mine", help="cohort statistics: find frequently-reviewed zero-correction cohorts")
    p_im.add_argument("--workspace", type=Path, required=True)
    p_ip = imp_sub.add_parser("propose", help="generate a candidate harness (adds exactly one cohort)")
    p_ip.add_argument("--workspace", type=Path, required=True)
    p_ip.add_argument("--cohort-id", required=True)
    p_ip.add_argument("--field", default=None)
    p_ip.add_argument("--tier", default=None, choices=["TIER1", "TIER2"])
    p_ip.add_argument("--strength", default=None,
                      choices=["unsupported", "single_source", "corroborated"])
    p_ip.add_argument("--finding", required=True, help="source finding id")
    p_ip.add_argument("--prediction", required=True,
                      help="prediction contract: which metric it should move, what it might hurt")
    p_ie = imp_sub.add_parser("evaluate", help="counterfactual re-routing, side by side with the status quo")
    p_ie.add_argument("--workspace", type=Path, required=True)
    p_ie.add_argument("--candidate", required=True)
    p_pr = imp_sub.add_parser("promote", help="human promotion (the only entry point that writes active)")
    p_pr.add_argument("--workspace", type=Path, required=True)
    p_pr.add_argument("--candidate", required=True)
    p_pr.add_argument("--approved-by", required=True)
    p_pr.add_argument("--rationale", required=True)
    p_pr.add_argument("--approved-at", required=True, help="ISO timestamp, supplied by a human")
    p_rb = imp_sub.add_parser("rollback", help="roll back to an existing harness (a new PROM record, append-only)")
    p_rb.add_argument("--workspace", type=Path, required=True)
    p_rb.add_argument("--to", required=True, help="target harness id to roll back to")
    p_rb.add_argument("--approved-by", required=True)
    p_rb.add_argument("--rationale", required=True)
    p_rb.add_argument("--approved-at", required=True, help="ISO timestamp, supplied by a human")

    args = parser.parse_args()

    if args.command == "doctor":
        from .doctor import cmd_doctor

        raise SystemExit(cmd_doctor())
    if args.command == "run":
        import os

        from . import snapshot
        from .pipeline import run

        out_of_calibration = False
        replayed = None
        if args.workspace is not None:
            # 输入契约:整个工作区就是根目录,产出落 ws/runs/run-NNNN(不可变,
            # 逐代递增),panel 必须声明"不在校准集内"(§12.3)
            os.environ["INVOICELOOP_DWS_DERISK"] = str(args.workspace)
            out_of_calibration = True
            # 文档集 = input/pdfs ∪ raw:抽取失败的文档不许从 run 里隐身
            # (静默丢单违反宪章四,评审 P1)—— 缺 raw 的由 extraction_present 记阻断
            from .ingest import discover

            doc_ids = args.doc_ids or sorted(
                set(discover(args.workspace)) | set(dws.stored_docs()))
            if not doc_ids:
                parser.error(f"{args.workspace} has no documents — put PDFs into input/pdfs/ and run ingest first")
            if args.docs is not None:
                doc_ids = doc_ids[: args.docs]
            # 指纹必须在 --docs/--doc-ids 截断之后算 —— 否则「5 份文档的 run」
            # 会被当成「全部文档的 run」重放
            fingerprint = snapshot.build_input_manifest(
                doc_ids, include_vision=not args.no_vision)["execution_fingerprint"]
            runs_dir = args.workspace / "runs"
            if not args.new_run:
                replayed = snapshot.find_run_by_fingerprint(runs_dir, fingerprint)
            out_dir = snapshot.allocate_run_dir(runs_dir)
        else:
            if args.out is None:
                parser.error("run needs --out or --workspace")
            out_dir = args.out
            doc_ids = args.doc_ids or dws.stored_docs()
            if not doc_ids:
                parser.error("no documents in the stored evidence — check where INVOICELOOP_DWS_DERISK points")
            if args.docs is not None:
                doc_ids = doc_ids[: args.docs]
        if replayed is not None:
            print(json.dumps({
                "replayed": True,
                "run_dir": str(replayed),
                "note": "execution fingerprint (input+code+harness) matches an existing run; "
                        "replaying it instead of re-running. A new run opens only when input or "
                        "the harness changes, or with --new-run (old runs are never touched)",
            }, ensure_ascii=False, indent=1))
            return
        paths = run(doc_ids, out_dir, render_crops=args.crops,
                    include_vision=not args.no_vision,
                    out_of_calibration=out_of_calibration)
        if args.workspace is not None:
            # current.json 只是可重建指针,权威是各 run 目录自己
            (args.workspace / "runs" / "current.json").write_text(
                json.dumps({"run": paths["run_dir"].name}, ensure_ascii=False) + "\n",
                encoding="utf-8")
        summary = json.loads(paths["matrix"].read_text(encoding="utf-8"))["summary"]
        print(json.dumps({"run_dir": str(paths["run_dir"]), "summary": summary},
                         ensure_ascii=False, indent=1))
    elif args.command == "ingest":
        from .ingest import cmd_ingest

        cmd_ingest(args.workspace, do_ocr=not args.no_ocr,
                   do_extract=not args.no_extract,
                   adaptive=bool(getattr(args, "adaptive", False)))
    elif args.command == "adjudicate":
        from .adjudicate import adjudicate_and_render

        result = adjudicate_and_render(
            args.run, claim_id=args.claim_id, doc_id=args.doc, field=args.field,
            decision=args.decision, rationale=args.rationale,
            adjudicator=args.adjudicator, decided_at=args.decided_at,
            corrected_value=args.corrected_value,
            supersedes_decision_id=args.supersedes_decision_id,
            reason_code=args.reason_code,
            reviewer_confidence=args.reviewer_confidence,
        )
        if not result["panel_refreshed"]:
            result["hint"] = ("the panel was not refreshed, but the adjudication is on disk (fsynced). "
                              f"Fix rendering, then run: python3 -m invoiceloop render --run {args.run}")
        print(json.dumps(result, ensure_ascii=False, indent=1))
    elif args.command == "approve":
        from .approve import append_approval
        from .deliver import write_deliverable

        entry = append_approval(
            args.run, doc_id=args.doc, approved_by=args.approved_by,
            rationale=args.rationale, approved_at=args.approved_at)
        # 先记账本(权威),再重写投影 —— 与裁决同一顺序
        write_deliverable(args.run)
        print(json.dumps(entry, ensure_ascii=False, indent=1))
    elif args.command == "render":
        from .panel import render_panel_from_run

        print(render_panel_from_run(args.run))
    elif args.command == "bundle":
        from .adjudicate import build_audit_bundle

        print(build_audit_bundle(args.run))
    elif args.command == "verify":
        from .adjudicate import verify_bundle

        report = verify_bundle(args.bundle)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        raise SystemExit(0 if report["ok"] else 1)
    elif args.command == "seal":
        from .seal import seal_run

        print(seal_run(args.run))
    elif args.command == "carry":
        from datetime import datetime, timezone

        from .carry import carry_forward

        decided_at = args.decided_at or datetime.now(
            timezone.utc).replace(microsecond=0).isoformat()
        print(json.dumps(carry_forward(args.run, decided_at=decided_at),
                         ensure_ascii=False, indent=1))
    elif args.command == "workbench":
        from .workbench import cmd_workbench

        raise SystemExit(cmd_workbench(
            args.workspace, args.port,
            host=args.host, allowed_hosts=args.allowed_hosts or None,
            read_only=args.read_only, review_scope=args.review_scope))
    elif args.command == "demo":
        from .demo import cmd_demo

        cmd_demo(args.out)
    elif args.command == "vision":
        from .vision_ingest import cmd_vision

        cmd_vision(args.workspace, tag=args.tag,
                   model=args.model, api_key=args.api_key)
    elif args.command == "heldout":
        from . import heldout

        if args.heldout_command == "plan":
            heldout.cmd_plan(args.workspace, args.n)
        else:
            heldout.cmd_extract(args.workspace, budget=args.budget)
    elif args.command == "sealed":
        from . import heldout

        if args.sealed_command == "plan":
            heldout.cmd_plan_sealed(args.workspace, seed_hex=args.seed,
                                    seed_source=args.seed_source, n=args.n,
                                    context=args.context, scope=args.scope)
        else:
            heldout.cmd_extract(args.workspace, budget=args.budget)
    elif args.command == "qualify":
        from . import heldout

        if args.qualify_command == "plan":
            heldout.cmd_plan_qual(args.workspace, n=args.n,
                                  context=args.context)
        else:
            heldout.cmd_extract(
                args.workspace, budget=args.budget,
                qualification_round=args.round,
                qualification_protocol=args.protocol)
    elif args.command == "suggest":
        from . import suggest as suggest_mod

        out = suggest_mod.suggest(args.workspace, model=args.model)
        print(json.dumps({"advisory": True,
                          "suggestions": len(out["suggestions"]),
                          "dropped": out.get("dropped", []),
                          "note_count": out.get("note_count", 0),
                          "file": str(args.workspace / "improve"
                                      / "suggestions.json")},
                         ensure_ascii=False, indent=1))
    elif args.command == "unattended":
        from .agents.runtime import DEFAULT_GEMINI_MODEL
        from .agents.unattended import failed, run_unattended

        oauth_meta = None
        if args.gcloud_oauth_project:
            from .agents.vertex_oauth import activate

            oauth_meta = activate(args.gcloud_oauth_project)
        report = run_unattended(
            args.run, model=args.model or DEFAULT_GEMINI_MODEL,
            decided_at=args.decided_at, docs=args.docs)
        if oauth_meta is not None:
            import pathlib

            meta_path = pathlib.Path(args.run) / "oauth_run_metadata.json"
            meta_path.write_text(
                json.dumps(oauth_meta, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
        print(json.dumps({
            "arm": report["arm"],
            "model": report["model"],
            "queue_slots": report["queue_slots"],
            "clerk_written": report["clerk_written"],
            "clerk_failed": len(report["clerk_failures"]),
            "critic_overrides": len(report["critic_overrides"]),
            "critic_failed": len(report["critic_failures"]),
            "gate_ready_docs": report["gate_ready_docs"],
            "approvals": report["approvals"],
            "approval_refusals": report["approval_refusals"],
            "adk_executed": report["adk"]["executed"],
            "stages": report["adk"]["event_authors"],
            "file": str(Path(args.run) / "unattended_run.json"),
            "note": "experimental arm, not the product default — approvals "
                    "are signed " + report["policy_id"] + "+agent:critic:"
                    + report["model"],
        }, ensure_ascii=False, indent=1))
        # 宪章四:执行失败(drive_fatal / 任一 *_failures)必须反映在退出码
        # 上 —— 否则 Vertex 全挂时 Cloud Run Job 照样报 successfully
        # completed。approval_refusals 是业务结果,不算失败(failed 的定义)。
        raise SystemExit(1 if failed(report) else 0)
    elif args.command == "agents":
        from .agents.improve_loop import run_improve_loop

        report = run_improve_loop(args.workspace, model=args.model)
        print(json.dumps({
            "advisory": report["advisory"],
            "adk_executed": report["adk"]["executed"],
            "stages": report["adk"]["event_authors"],
            "model": report["model"],
            "proposals": len(report["proposals"]),
            "blocking_evaluations": report["blocking_evaluations"],
            "recommended_for_human_review":
                report["recommended_for_human_review"],
            "file": str(args.workspace / "improve" / "adk_loop_report.json"),
            "note": "advice only — promotion is still decided by Gate 2 plus a human signature",
        }, ensure_ascii=False, indent=1))
    elif args.command == "improve":
        from . import improve

        if args.improve_command == "mine":
            report = improve.mine(args.workspace)
            print(json.dumps({"events": report["events"],
                              "cohorts": len(report["cohorts"]),
                              "low_yield_candidates": report["low_yield_candidates"],
                              "report": str(args.workspace / "improve" / "mine_report.json")},
                             ensure_ascii=False, indent=1))
        elif args.improve_command == "propose":
            cohort = {"id": args.cohort_id}
            if args.field:
                cohort["field"] = args.field
            if args.tier:
                cohort["tier"] = args.tier
            if args.strength:
                cohort["strength"] = args.strength
            cand = improve.propose(args.workspace, cohort=cohort,
                                   finding=args.finding,
                                   prediction=args.prediction)
            print(f"candidate created: {cand} (status=candidate, not in effect)")
        elif args.improve_command == "evaluate":
            result = improve.evaluate(args.workspace, args.candidate)
            print(json.dumps(result, ensure_ascii=False, indent=1))
        elif args.improve_command == "rollback":
            record = improve.rollback(
                args.workspace, to_harness_id=args.to,
                approved_by=args.approved_by, rationale=args.rationale,
                approved_at=args.approved_at)
            print(json.dumps(record, ensure_ascii=False, indent=1))
        else:  # promote
            record = improve.promote(
                args.workspace, args.candidate,
                approved_by=args.approved_by, rationale=args.rationale,
                approved_at=args.approved_at)
            print(json.dumps(record, ensure_ascii=False, indent=1))


def main() -> None:
    """CLI 入口:用户的输入错误给干净的一句话,不给裸 traceback。

    捕 Exception 全类(RunExistsError/CalledProcessError/OSError 都算用户
    该看到一句话的错,双评 P1-2/P1-4 实测 5 类裸 traceback);SystemExit
    与 KeyboardInterrupt 不是 Exception 的子类,自然穿透。
    """
    try:
        _main()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"error: {exc}") from None


if __name__ == "__main__":
    main()
