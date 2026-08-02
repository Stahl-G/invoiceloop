"""CLI:python -m invoiceloop ...

    run         从存盘证据跑全流程(零 API)
    adjudicate  追加一条人工裁决
    bundle      打 audit_bundle.zip
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import dws


def main() -> None:
    parser = argparse.ArgumentParser(prog="invoiceloop")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="extract → freeze → gates → matrix → panel")
    p_run.add_argument("--docs", type=int, default=None, help="只跑前 N 份(默认全部存盘文档)")
    p_run.add_argument("--doc-ids", nargs="*", default=None, help="指定 doc_id 列表")
    p_run.add_argument("--out", type=Path, required=True, help="run 目录")
    p_run.add_argument("--crops", action="store_true", help="渲染证据裁剪图(需 poppler + PDF 语料)")
    p_run.add_argument("--no-vision", action="store_true", help="不并入第六轮读图作答")

    p_adj = sub.add_parser("adjudicate", help="追加人工裁决")
    p_adj.add_argument("--run", type=Path, required=True)
    p_adj.add_argument("--doc", required=True)
    p_adj.add_argument("--field", required=True)
    p_adj.add_argument("--claim-id", default=None)
    p_adj.add_argument("--decision", required=True)
    p_adj.add_argument("--rationale", required=True)
    p_adj.add_argument("--adjudicator", required=True)
    p_adj.add_argument("--decided-at", required=True, help="ISO 时间,由人给出")
    p_adj.add_argument("--corrected-value", default=None)

    p_bun = sub.add_parser("bundle", help="打 audit_bundle.zip")
    p_bun.add_argument("--run", type=Path, required=True)

    p_ho = sub.add_parser("heldout", help="留出集(docs/HELDOUT.md)")
    ho_sub = p_ho.add_subparsers(dest="heldout_command", required=True)
    p_hop = ho_sub.add_parser("plan", help="生成并落盘名单(先于任何调用)")
    p_hop.add_argument("--workspace", type=Path, required=True)
    p_hop.add_argument("--n", type=int, default=100)
    p_hoe = ho_sub.add_parser("extract", help="按名单跑双模式,断点续跑,预算熔断")
    p_hoe.add_argument("--workspace", type=Path, required=True)
    p_hoe.add_argument("--budget", type=float, default=6000.0)

    args = parser.parse_args()

    if args.command == "run":
        from .pipeline import run

        doc_ids = args.doc_ids or dws.stored_docs()
        if args.docs is not None:
            doc_ids = doc_ids[: args.docs]
        paths = run(doc_ids, args.out, render_crops=args.crops,
                    include_vision=not args.no_vision)
        summary = json.loads(paths["matrix"].read_text(encoding="utf-8"))["summary"]
        print(json.dumps({"run_dir": str(paths["run_dir"]), "summary": summary},
                         ensure_ascii=False, indent=1))
    elif args.command == "adjudicate":
        from .adjudicate import append_adjudication

        entry = append_adjudication(
            args.run, claim_id=args.claim_id, doc_id=args.doc, field=args.field,
            decision=args.decision, rationale=args.rationale,
            adjudicator=args.adjudicator, decided_at=args.decided_at,
            corrected_value=args.corrected_value,
        )
        print(json.dumps(entry, ensure_ascii=False, indent=1))
    elif args.command == "bundle":
        from .adjudicate import build_audit_bundle

        print(build_audit_bundle(args.run))
    elif args.command == "heldout":
        from . import heldout

        if args.heldout_command == "plan":
            heldout.cmd_plan(args.workspace, args.n)
        else:
            heldout.cmd_extract(args.workspace, budget=args.budget)


if __name__ == "__main__":
    main()
