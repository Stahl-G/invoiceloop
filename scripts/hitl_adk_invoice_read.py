#!/usr/bin/env python3
"""ADK document-level invoice reading → run-dir display suggestions.

One Gemini call per document (all page PNGs). Writes:
  <run>/vision/invoice_read.json          advisory readings (not a fingerprint)
  <run>/vision/answers6.adk-invoice.tsv   display-only field suggestions

Does not write the ledger, does not touch workspace-level vision/, does not
read DocILE truth. Tag is adk-invoice (capability); model name is in the note.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import suggest_inject  # noqa: E402
from invoiceloop.agents.invoice_read import (  # noqa: E402
    SUGGEST_TAG,
    load_page_images,
    make_invoice_reader,
    read_docs,
    save_readings,
    to_suggestion_rows,
)
from invoiceloop.agents.runtime import DEFAULT_GEMINI_MODEL  # noqa: E402


def _doc_ids(run_dir: Path) -> list[str]:
    sm = json.loads((run_dir / "support_matrix.json").read_text(encoding="utf-8"))
    return sorted({row["doc_id"] for row in sm["rows"]})


def _already_read(run_dir: Path, model: str) -> set[str]:
    """按 model 分键 —— 换模型重跑必须真的重读,不是整批 skip。"""
    return read_docs(run_dir, model)


def rereads_already_injected(run_dir: Path, tag: str,
                             reread: set[str]) -> set[str]:
    """`reread` 里在该 tag 下已经有建议行的 doc_id。

    非空 = 注入会 skip 掉它们,工作台留着上一个模型的值。
    """
    tsv = run_dir / "vision" / f"answers6.{tag}.tsv"
    if not tsv.exists() or not reread:
        return set()
    injected = {line.split("\t")[0]
                for line in tsv.read_text(encoding="utf-8").splitlines()[1:]
                if line.strip()}
    return reread & injected


def conflicting_rereads(run_dir: Path, tag: str, doc_ids: list[str],
                        model: str) -> set[str]:
    """**还没读**、但该 tag 下已有建议行的 doc_id —— 读之前就能判。

    从「本模型尚未读过的」算起,不是从「本次读到的」算起:后者在存盘之后
    就变空了,拒绝会在重试时自己消失。这个只读盘上既有状态,重试幂等。
    """
    pending = {d for d in doc_ids if d not in read_docs(run_dir, model)}
    return rereads_already_injected(run_dir, tag, pending)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--model", default=None,
                    help=f"缺省 {DEFAULT_GEMINI_MODEL}")
    args = ap.parse_args()
    run_dir = args.run_dir
    model = args.model or DEFAULT_GEMINI_MODEL
    proxy = (os.environ.get("HTTPS_PROXY")
             or os.environ.get("HTTP_PROXY")
             or os.environ.get("https_proxy")
             or os.environ.get("http_proxy")
             or "none")
    print(f"proxy {proxy}", flush=True)
    ws = run_dir.parent.parent
    doc_ids = _doc_ids(run_dir)
    n_docs = len(doc_ids)
    done = _already_read(run_dir, model)
    # 冲突检查必须在**读之前**:inject 是 append-only,重读过的单据写不进去,
    # 工作台会留着上一个模型的值。放在读完之后检查是不耐重试的 —— 第一次跑
    # 已经把读法存了盘,重试时它们进 done、pending 变空、检查就绕过去了。
    # 前置还顺带省掉整批 API 调用。
    conflict = conflicting_rereads(run_dir, SUGGEST_TAG, doc_ids, model)
    if conflict:
        print(json.dumps({
            "fatal": "待读的单据在该 tag 下已有建议行,append-only 写不进去",
            "tag": SUGGEST_TAG, "conflicting_docs": sorted(conflict),
            "fix": "换一个 tag(另起一层建议),或换一个 run",
        }, ensure_ascii=False, indent=1))
        raise SystemExit(1)
    read = make_invoice_reader(model=model, workspace=ws)

    docs: dict[str, dict] = {}
    rows: list[dict] = []
    failed: list[dict[str, str]] = []
    for i, doc_id in enumerate(doc_ids, 1):
        if doc_id in done:
            print(f"[{i}/{n_docs}] {doc_id} skip (already read by {model})",
                  flush=True)
            continue
        print(f"[{i}/{n_docs}] {doc_id}", flush=True)
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                images = load_page_images(run_dir, doc_id)
                reading = read(doc_id, images)
                payload = reading.model_dump()
                docs[doc_id] = payload
                rows.extend(to_suggestion_rows(doc_id, reading, model=model))
                save_readings(run_dir, model=model, docs=docs, failed=failed)
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001 — retry then record
                last_exc = exc
                print(f"  attempt {attempt}/3 failed: {type(exc).__name__}",
                      flush=True)
                time.sleep(2 * attempt)
        if last_exc is not None:
            failed.append({"doc_id": doc_id,
                           "error": f"{type(last_exc).__name__}: {last_exc}"})
            save_readings(run_dir, model=model, docs=docs, failed=failed)

    save_readings(run_dir, model=model, docs=docs, failed=failed)
    packed_path = run_dir / "vision" / "invoice_read.json"
    packed = json.loads(packed_path.read_text(encoding="utf-8")) \
        if packed_path.exists() else {"docs": {}}
    from invoiceloop.agents.invoice_read import InvoiceReading
    inject_rows = []
    # 重建覆盖文件里**全部**读法,包括别的模型读的。建议行的 provenance
    # 必须用那份读法自己的 model,不是本次 --model,否则旧读法被改名。
    top_model = str(packed.get("model") or model)
    for doc_id, rec in (packed.get("docs") or {}).items():
        doc_model = str(rec.get("model") or top_model)
        inject_rows.extend(to_suggestion_rows(
            doc_id, InvoiceReading.model_validate(rec), model=doc_model))
    summary = suggest_inject.inject(ws, SUGGEST_TAG, inject_rows, run_dir=run_dir)
    print(json.dumps({
        "run": str(run_dir),
        "model": model,
        "tag": SUGGEST_TAG,
        "docs": len(packed.get("docs") or {}),
        "failed": packed.get("failed") or failed,
        "injected": {k: summary[k] for k in
                     ("written", "skipped_existing", "reread_rows")},
        "dropped": summary["dropped"],
    }, ensure_ascii=False, indent=1))
    raise SystemExit(1 if (packed.get("failed") or failed) else 0)


if __name__ == "__main__":
    main()
