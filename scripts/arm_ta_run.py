#!/usr/bin/env python3
"""Run the TA arm: an ADK agent adjudicates the 200 pre-registered slots.

Protocol: `docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md`. Zero DWS calls; one
Gemini call per slot.

Resumable: slots already present in the ledger are skipped, because
`append_adjudication` refuses a second decision on the same slot without an
explicit supersede — a resume must not look like a reviewer changing their mind.

    python3 scripts/arm_ta_run.py --decided-at 2026-08-08T00:00:00Z
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop import arms  # noqa: E402
from invoiceloop.agents import adjudicator as adj  # noqa: E402
from invoiceloop.review import load_decisions  # noqa: E402

SOURCE_RUN = Path("runs/sealed2")
SOURCE_WS = Path("runs/sealed2-workspace")
ARM_WS = Path("runs/arm-ta")
ARM_RUN = ARM_WS / "runs" / "run-0001"
SAMPLE = Path("docs/arm_slot_sample.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decided-at", required=True,
                    help="ISO 8601;整臂一个时间戳,工件不读墙钟")
    ap.add_argument("--model", default="gemini-3.6-flash")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retries", type=int, default=4,
                    help="仅对传输层失败退避重试;写入口拒绝不重试")
    ap.add_argument("--backoff", type=float, default=8.0)
    ap.add_argument("--pace", type=float, default=1.5,
                    help="槽间固定间隔,压配额峰值")
    args = ap.parse_args()

    slots = json.loads(SAMPLE.read_text(encoding="utf-8"))["slots"]
    if args.limit:
        slots = slots[: args.limit]

    done = {f"{d['doc_id']}|{d['field']}" for d in load_decisions(ARM_RUN)}
    # 写入口拒绝过的槽**永久跳过**。它们不是"没跑",是 agent 给了一个非法
    # 裁决、被那个照样接受人的写入口挡回来 —— 那就是 TA 臂的实测缺陷。
    # 重试它等于摇到一个能过的答案为止,是拿结果调参(预注册 §7)。
    refused_path = ARM_WS / "refused_slots.json"
    refused = set()
    if refused_path.exists():
        refused = {r["slot"] for r in
                   json.loads(refused_path.read_text(encoding="utf-8"))["slots"]}
    todo = [s for s in slots if s not in done and s not in refused]
    print(f"slots={len(slots)} already={len(done)} refused={len(refused)} "
          f"todo={len(todo)}", flush=True)

    registry = json.loads(
        (SOURCE_RUN / "evidence_span_registry.json").read_text(encoding="utf-8"))
    images_dir = ARM_WS / "images"
    judge = adj.make_adk_judge(model=args.model, workspace=ARM_WS)

    def images_for(key: str) -> list[bytes]:
        paths = arms.visual_pack(SOURCE_RUN, SOURCE_WS, key, images_dir,
                                 registry=registry)
        return [p.read_bytes() for p in paths]

    started = time.time()
    written, failures = 0, []
    for i, key in enumerate(todo, 1):
        # 传输层失败(配额耗尽 / 5xx)退避重试:重试改的不是 prompt/判据/抽样,
        # 只是让这个槽真的被问到一次。**写入口的拒绝不在此列** —— 那是答案,
        # 不是传输,重试它就是调参。
        for attempt in range(args.retries + 1):
            one = adj.run_arm(ARM_RUN, [key], judge=judge, model=args.model,
                              decided_at=args.decided_at, images_for=images_for)
            err = one["failures"][0]["error"] if one["failures"] else ""
            transport = ("ResourceExhausted" in err or "ServerError" in err
                         or "DeadlineExceeded" in err)
            if not transport or attempt == args.retries:
                break
            time.sleep(args.backoff * (2 ** attempt))
        written += one["written"]
        failures.extend(one["failures"])
        time.sleep(args.pace)
        if i % 10 == 0 or i == len(todo):
            rate = (time.time() - started) / i
            print(f"  {i}/{len(todo)}  written={written} failed={len(failures)}"
                  f"  {rate:.1f}s/slot", flush=True)

    report = {
        "protocol": "docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md",
        "arm": "TA",
        "model": args.model,
        "adjudicator": adj.adjudicator_id(args.model),
        "decided_at": args.decided_at,
        "slots_in_sample": len(slots),
        "attempted": len(todo),
        "written": written,
        "failed": len(failures),
        "failures": failures,
        "retries": args.retries,
        "pace_seconds": args.pace,
        "ledger_lines": len(
            (ARM_RUN / "adjudication_ledger.jsonl").read_text(
                encoding="utf-8").splitlines()),
        "recordings": len(list((ARM_WS / "agent_calls").glob("*.json"))),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    (ARM_WS / "arm_report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    # 只打结构量 —— 裁决内容在人做完 H2 之前不得出现在任何输出里(预注册 §8)
    print(json.dumps({k: v for k, v in report.items() if k != "failures"},
                     indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
