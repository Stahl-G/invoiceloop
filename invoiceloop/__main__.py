"""CLI:python -m invoiceloop ...

    run         从存盘证据跑全流程(零 API)
    adjudicate  追加一条人工裁决
    bundle      打 audit_bundle.zip
    doctor      环境自检(产品路径硬依赖缺失 → 退出码 1)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import dws


def _main() -> None:
    parser = argparse.ArgumentParser(prog="invoiceloop")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="extract → freeze → gates → matrix → panel")
    p_run.add_argument("--docs", type=int, default=None, help="只跑前 N 份(默认全部存盘文档)")
    p_run.add_argument("--doc-ids", nargs="*", default=None, help="指定 doc_id 列表")
    p_run.add_argument("--out", type=Path, default=None, help="run 目录(--workspace 时不用)")
    p_run.add_argument("--workspace", type=Path, default=None,
                       help="输入契约工作区:读 ws/raw + ws/ocr + ws/input/pdfs,写到 ws/output")
    p_run.add_argument("--crops", action="store_true", help="渲染证据裁剪图(需 poppler + PDF 语料)")
    p_run.add_argument("--no-vision", action="store_true", help="不并入第六轮读图作答")
    p_run.add_argument("--new-run", action="store_true",
                       help="输入未变也开新 run(默认重放同指纹的既有 run;旧 run 永远原样保留)")

    p_ing = sub.add_parser("ingest", help="输入契约:input/pdfs → ocr/ + raw/")
    p_ing.add_argument("--workspace", type=Path, required=True)
    p_ing.add_argument("--no-ocr", action="store_true", help="跳过本地独立 OCR")
    p_ing.add_argument("--no-extract", action="store_true", help="跳过 DWS 抽取(先只产 OCR)")

    p_adj = sub.add_parser("adjudicate", help="追加人工裁决(随后自动重渲 panel)")
    p_adj.add_argument("--run", type=Path, required=True)
    p_adj.add_argument("--doc", required=True)
    p_adj.add_argument("--field", required=True)
    p_adj.add_argument("--claim-id", default=None)
    p_adj.add_argument("--decision", required=True)
    p_adj.add_argument("--rationale", required=True)
    p_adj.add_argument("--adjudicator", required=True)
    p_adj.add_argument("--decided-at", required=True, help="ISO 时间,由人给出")
    p_adj.add_argument("--corrected-value", default=None,
                       help="decision=correct 时必填,其余决策禁带")
    p_adj.add_argument("--supersedes", dest="supersedes_decision_id", default=None,
                       help="该字段槽已有裁决时必填:当前 tip 的 decision_id")

    p_ren = sub.add_parser("render", help="从盘上工件重渲 panel(纯投影,可重算)")
    p_ren.add_argument("--run", type=Path, required=True)

    p_bun = sub.add_parser("bundle", help="打 audit_bundle.zip(全量自包含)")
    p_bun.add_argument("--run", type=Path, required=True)

    p_ver = sub.add_parser("verify", help="离线校验 audit bundle(三层:成员/快照/绑定)")
    p_ver.add_argument("bundle", type=Path)

    p_wb = sub.add_parser("workbench", help="H1 复核工作台:本地 loopback Web 应用(127.0.0.1)")
    p_wb.add_argument("--workspace", type=Path, required=True)
    p_wb.add_argument("--port", type=int, default=8765)

    p_demo = sub.add_parser("demo", help="内嵌示例语料 → 完整 run(零 API、零外部数据)")
    p_demo.add_argument("--out", type=Path, required=True, help="demo workspace 落点(必须不存在或为空)")

    p_vis = sub.add_parser("vision", help="读图 ingest:整页渲染 → 读图模型作答 → vision/answers6 tsv")
    p_vis.add_argument("--workspace", type=Path, required=True)
    p_vis.add_argument("--tag", default="D", help="读者 tag(显示名映射见 dws.VISION_READERS)")
    p_vis.add_argument("--model", default=None, help="读图模型(默认 claude-sonnet-5)")
    p_vis.add_argument("--api-key", default=None, help="默认读 ANTHROPIC_API_KEY")

    sub.add_parser("doctor", help="环境自检:poppler/tesseract/requests/研究数据")

    p_ho = sub.add_parser("heldout", help="留出集(docs/HELDOUT.md)")
    ho_sub = p_ho.add_subparsers(dest="heldout_command", required=True)
    p_hop = ho_sub.add_parser("plan", help="生成并落盘名单(先于任何调用)")
    p_hop.add_argument("--workspace", type=Path, required=True)
    p_hop.add_argument("--n", type=int, default=100)
    p_hoe = ho_sub.add_parser("extract", help="按名单跑双模式,断点续跑,预算熔断")
    p_hoe.add_argument("--workspace", type=Path, required=True)
    p_hoe.add_argument("--budget", type=float, default=6000.0)

    p_imp = sub.add_parser("improve", help="改进控制面(v0.2 收窄版,全确定性零模型)")
    imp_sub = p_imp.add_subparsers(dest="improve_command", required=True)
    p_im = imp_sub.add_parser("mine", help="cohort 统计:找高频复核零修正")
    p_im.add_argument("--workspace", type=Path, required=True)
    p_ip = imp_sub.add_parser("propose", help="生成候选 harness(只加一条 cohort)")
    p_ip.add_argument("--workspace", type=Path, required=True)
    p_ip.add_argument("--cohort-id", required=True)
    p_ip.add_argument("--field", default=None)
    p_ip.add_argument("--tier", default=None, choices=["TIER1", "TIER2"])
    p_ip.add_argument("--strength", default=None,
                      choices=["unsupported", "single_source", "corroborated"])
    p_ip.add_argument("--finding", required=True, help="来源 finding id")
    p_ip.add_argument("--prediction", required=True,
                      help="预测合同:预计改什么指标、可能伤害什么")
    p_ie = imp_sub.add_parser("evaluate", help="反事实重路由,与现状并排")
    p_ie.add_argument("--workspace", type=Path, required=True)
    p_ie.add_argument("--candidate", required=True)
    p_pr = imp_sub.add_parser("promote", help="人工晋升(唯一写 active 的入口)")
    p_pr.add_argument("--workspace", type=Path, required=True)
    p_pr.add_argument("--candidate", required=True)
    p_pr.add_argument("--approved-by", required=True)
    p_pr.add_argument("--rationale", required=True)
    p_pr.add_argument("--approved-at", required=True, help="ISO 时间,由人给出")
    p_rb = imp_sub.add_parser("rollback", help="回滚到既有 harness(新 PROM 记录,append-only)")
    p_rb.add_argument("--workspace", type=Path, required=True)
    p_rb.add_argument("--to", required=True, help="回滚目标 harness id")
    p_rb.add_argument("--approved-by", required=True)
    p_rb.add_argument("--rationale", required=True)
    p_rb.add_argument("--approved-at", required=True, help="ISO 时间,由人给出")

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
                parser.error(f"{args.workspace} 里没有文档 —— 先放 PDF 进 input/pdfs/ 再 ingest")
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
                parser.error("run 需要 --out 或 --workspace")
            out_dir = args.out
            doc_ids = args.doc_ids or dws.stored_docs()
            if not doc_ids:
                parser.error("存盘证据里没有文档 —— 检查 INVOICELOOP_DWS_DERISK 指向")
            if args.docs is not None:
                doc_ids = doc_ids[: args.docs]
        if replayed is not None:
            print(json.dumps({
                "replayed": True,
                "run_dir": str(replayed),
                "note": "执行指纹(输入+代码+harness)与既有 run 一致,重放不重跑;"
                        "输入或 harness 变化或 --new-run 才开新 run(旧 run 永远原样保留)",
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
                   do_extract=not args.no_extract)
    elif args.command == "adjudicate":
        from .adjudicate import adjudicate_and_render

        result = adjudicate_and_render(
            args.run, claim_id=args.claim_id, doc_id=args.doc, field=args.field,
            decision=args.decision, rationale=args.rationale,
            adjudicator=args.adjudicator, decided_at=args.decided_at,
            corrected_value=args.corrected_value,
            supersedes_decision_id=args.supersedes_decision_id,
        )
        if not result["panel_refreshed"]:
            result["hint"] = ("panel 未刷新,但裁决已落盘(fsync)。"
                              f"修好渲染后跑:python3 -m invoiceloop render --run {args.run}")
        print(json.dumps(result, ensure_ascii=False, indent=1))
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
    elif args.command == "workbench":
        from .workbench import cmd_workbench

        raise SystemExit(cmd_workbench(args.workspace, args.port))
    elif args.command == "demo":
        from .demo import cmd_demo

        cmd_demo(args.out)
    elif args.command == "vision":
        from .vision_ingest import DEFAULT_MODEL, cmd_vision

        cmd_vision(args.workspace, tag=args.tag,
                   model=args.model or DEFAULT_MODEL, api_key=args.api_key)
    elif args.command == "heldout":
        from . import heldout

        if args.heldout_command == "plan":
            heldout.cmd_plan(args.workspace, args.n)
        else:
            heldout.cmd_extract(args.workspace, budget=args.budget)
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
            print(f"候选已建:{cand}(status=candidate,未生效)")
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
        raise SystemExit(f"错误:{exc}") from None


if __name__ == "__main__":
    main()
