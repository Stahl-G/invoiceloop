"""`python3 -m invoiceloop demo` — run the whole pipeline on the bundled corpus.

The key link in a reviewer's path: the repository needs no external data.
`samples/` carries three DocILE invoices, their already-stored DWS responses (so
extraction is not re-run — zero API) and vision answers. `demo --out ws/` builds a
workspace in place, runs local OCR, executes a full run, and points at the
workbench.

046e0c49 is a degraded scan: most poppler builds cannot pull a text layer from it,
so OCR is blocked and it becomes an honest blocking exhibit; a few builds can, and
then it flows through normally. Both shapes are legitimate. The
environment-independent exhibit is the vision gate's warning about the buyer and
seller being extracted the wrong way round, which the vendored data determines.
What is pinned is the invariant "blocked must be explicit", not "this document
must block" — the 78-point review's P3 found the latter failing on a reviewer's
machine.
"""

from __future__ import annotations

import json
import os
import shutil
from importlib import resources
from pathlib import Path

#: 演示裁决的署名。裁决账本是「某个人看过并判了」的证词,而演示里的裁决
#: 不是人做的 —— 署名必须让任何人一眼看出来不是人。不要改成像人名的东西。
DEMO_ADJUDICATOR = "demo-fixture (not a human review)"

_DEMO_RATIONALE = (
    "seeded by `invoiceloop demo` as a fixture so the delivery projection has "
    "something to project — no person looked at this row"
)

_DEMO_APPROVAL_RATIONALE = (
    "seeded by `invoiceloop demo` as a fixture so the demo reaches the export "
    "gate — no person approved this document for posting"
)


def _seed_review(run_dir: Path) -> int:
    """把演示 run 里待裁决的槽逐条判掉,让至少一份文档走到出口。

    为什么要有这一步:`deliverable.json` 从 2026-08-05 起每次 run 都写,
    但内嵌语料跑完全部是 `pending`,于是公开演示上评委只看得到待办队列,
    看不到系统交付什么。存在但不可见,对读者而言约等于不存在。

    为什么这不是伪造:决策全部走 `adjudicate_and_render` 的正常路径(同样
    的三重校验、同样的哈希链),署名与理由都写明是夹具。出处在工件里,
    可核 —— 这正是这个项目对「谁判的」的一贯要求。
    """
    from .adjudicate import adjudicate_and_render
    from .deliver import build_deliverable

    seeded = 0
    while True:                              # 每轮重算,直到不再有进展
        deliverable = build_deliverable(run_dir)
        todo = [
            (doc_id, field)
            for doc_id, doc in deliverable["docs"].items()
            for field, slot in doc["fields"].items()
            if slot["status"] in ("pending", "pending_tier1")
        ]
        if not todo:
            break
        before_round = seeded
        ledger = json.loads((run_dir / "field_ledger.json").read_text(encoding="utf-8"))
        claims = {(c["doc_id"], c["field"]): c["claim_id"] for c in ledger["claims"]}
        for doc_id, field in todo:
            claim_id = claims.get((doc_id, field))
            kwargs = dict(
                doc_id=doc_id, field=field,
                # claim_id 永远显式传(缺省时为 None)—— append_adjudication
                # 把它设成 keyword-only 必填,正是为了逼调用方表态
                claim_id=claim_id,
                rationale=_DEMO_RATIONALE, adjudicator=DEMO_ADJUDICATOR,
                decided_at="2026-08-07T12:00:00+00:00",
                # 有冻结 claim 就接受它;没有就是页面上确实没这个字段
                decision="accept" if claim_id else "confirm_absent",
            )
            try:
                adjudicate_and_render(run_dir, **kwargs)
                seeded += 1
            except Exception:  # noqa: BLE001 —— 判不了的槽留 pending,如实显示
                pass
        if seeded == before_round:           # 一轮下来一条都没判成 —— 停
            break
    _seed_approvals(run_dir)
    return seeded


def _seed_approvals(run_dir: Path) -> int:
    """把处置完的文档批准掉,让演示走到**真正**的出口。

    2026-08-09 加:槽全部裁完只到 ready_for_approval —— 那是自动化的终点,
    不是可外发。演示要展示的正是这最后一步归人所有,所以它也必须出现在
    demo 里,并且和裁决一样署名为夹具,一眼看得出不是人批的。
    """
    from .approve import append_approval
    from .deliver import build_deliverable, write_deliverable

    approved = 0
    for doc_id, doc in build_deliverable(run_dir)["docs"].items():
        if not doc["status"].startswith("ready_for_approval"):
            continue
        try:
            append_approval(
                run_dir, doc_id=doc_id, approved_by=DEMO_ADJUDICATOR,
                rationale=_DEMO_APPROVAL_RATIONALE,
                approved_at="2026-08-07T12:00:00+00:00")
            approved += 1
        except Exception:  # noqa: BLE001 —— 批不了的留 ready_for_approval
            pass
    if approved:
        # 批准是账本(权威),deliverable.json 是投影 —— 顺序同裁决:
        # 先记事件,再重写投影。少了这一步盘上的投影会停在批准前的状态。
        write_deliverable(run_dir)
    return approved


def _copy_samples(ws: Path) -> None:
    src = resources.files("invoiceloop") / "samples"
    for sub, target in (("pdfs", ws / "input" / "pdfs"),
                        ("raw", ws / "raw"),
                        ("vision", ws / "vision")):
        target.mkdir(parents=True, exist_ok=True)
        for item in (src / sub).iterdir():
            (target / item.name).write_bytes(item.read_bytes())


def cmd_demo(out: Path) -> None:
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} 已存在且非空 —— run 不可变同样适用于 demo,换个目录")
    _copy_samples(out)

    # 语料指针只在本命令内改向,用完还回 —— 库调用不许留下环境副作用
    prev = {k: os.environ.get(k) for k in ("INVOICELOOP_CORPUS", "INVOICELOOP_DWS_DERISK")}
    os.environ["INVOICELOOP_CORPUS"] = str(out)
    try:
        from . import dws, ocr as ocr_mod
        from .ingest import cmd_ingest, discover
        from .pipeline import run

        # lru_cache 按 doc_id 记:同进程里别的语料先跑过的话,
        # 同名文档会拿到旧语料的 OCR(长驻进程缓存污染,同复核 #6 一类)
        ocr_mod.load_ocr.cache_clear()
        ocr_mod.doc_tokens.cache_clear()

        summary = cmd_ingest(out, do_ocr=True, do_extract=False)
        doc_ids = sorted(set(discover(out)) | set(dws.stored_docs()))
        run_dir = out / "runs" / "run-0001"
        paths = run(doc_ids, run_dir, render_crops=True,
                    include_vision=True, out_of_calibration=True)
        (out / "runs" / "current.json").write_text(
            json.dumps({"run": "run-0001"}, ensure_ascii=False) + "\n", encoding="utf-8")
        seeded = _seed_review(run_dir)
    finally:
        for key, value in prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    blocked = summary.get("ocr_blocked", [])
    blocked_ids = [b["doc_id"] for b in blocked]
    if blocked_ids:
        note = (f"OCR 受阻:{', '.join(blocked_ids)} —— 诚实阻断展品;"
                f"046e0c49 的读图门「买卖双方抽反」warning 两份展品都在")
    else:
        note = ("本机 poppler 从退化扫描件也抽出了文字层,三份全流程正常;"
                "046e0c49 的展品是读图门对「买卖双方抽反」的 warning(数据决定)")
    from .deliver import build_deliverable

    delivered = build_deliverable(run_dir)
    print(json.dumps({
        "workspace": str(out),
        "run_dir": str(run_dir),
        "panel": str(paths["panel"]),
        "docs": doc_ids,
        "ocr_blocked": blocked_ids,
        "seeded_decisions": seeded,
        "seeded_by": DEMO_ADJUDICATOR,
        "delivery_status": delivered["summary"]["by_status"],
        "deliverable": str(run_dir / "deliverable.json"),
        "next": f"python3 -m invoiceloop workbench --workspace {out}",
        "note": note,
    }, ensure_ascii=False, indent=1))
