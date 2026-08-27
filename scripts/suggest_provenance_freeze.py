#!/usr/bin/env python3
"""建议预生成之后冻结 —— 走前跑一次,走中途不跑。

冻结的是**人真正会看见的那些行**:vision/answers6.<tag>.tsv 的每一行,
连同它背后那份读法的摘要。整表 sha256 作为工件哈希进账本。

已存在则拒绝覆盖:溯源表被改写过,账本里已有的哈希就对不上了 ——
那正是废臂条款要挡的「走中途补生成建议」。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop import suggest_provenance  # noqa: E402
from invoiceloop.agents.invoice_read import (  # noqa: E402
    INVOICE_READ_SYSTEM, READ_USER_PROMPT, SUGGEST_TAG, InvoiceReading,
)


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def freeze(run_dir: Path, *, tag: str, round_name: str,
           frozen_at: str) -> Path:
    run_dir = Path(run_dir)
    out = run_dir / "vision" / suggest_provenance.FILENAME
    if out.exists():
        raise SystemExit(json.dumps({
            "fatal": "溯源表已存在,拒绝覆盖 —— 账本里已有的哈希会对不上。"
                     "要重来就换一个 run。",
            "path": str(out),
        }, ensure_ascii=False, indent=1))

    tsv = run_dir / "vision" / f"answers6.{tag}.tsv"
    packed = json.loads((run_dir / "vision" / "invoice_read.json")
                        .read_text(encoding="utf-8"))
    top_model = str(packed.get("model") or "")
    readings = packed.get("docs") or {}

    slots = suggest_provenance.build_slots(run_dir)
    orphans = sorted(k for k in slots if k.split("|")[0] not in readings)
    if orphans:
        raise SystemExit(json.dumps({
            "fatal": "有展示行没有对应读法 —— 人看得见,却指不出它从哪来",
            "slots": orphans,
        }, ensure_ascii=False, indent=1))
    for key, slot in slots.items():
        slot["reading_sha256"] = suggest_provenance.record_digest(
            readings[key.split("|")[0]])

    if packed.get("failed"):
        print(json.dumps({
            "warning": "有读法失败的文档 —— 它们没有工件,也不会有展示行。"
                       "结果文档必须写出失败数,不能当成 100% 覆盖。",
            "failed": packed["failed"],
        }, ensure_ascii=False, indent=1), flush=True)

    payload = {
        "round": round_name,
        "frozen_at": frozen_at,
        "prompt_digest": _text_digest(INVOICE_READ_SYSTEM + "\n" + READ_USER_PROMPT),
        "schema_digest": _text_digest(json.dumps(
            InvoiceReading.model_json_schema(), sort_keys=True,
            ensure_ascii=False, separators=(",", ":"))),
        "readers": {tag: {
            "model": top_model,
            "artifact": f"vision/answers6.{tag}.tsv",
            "artifact_sha256": hashlib.sha256(tsv.read_bytes()).hexdigest(),
            "upstream": "vision/invoice_read.json",
            "upstream_sha256": hashlib.sha256(
                (run_dir / "vision" / "invoice_read.json").read_bytes()).hexdigest(),
        }},
        "slots": slots,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--tag", default=SUGGEST_TAG)
    ap.add_argument("--round", required=True, dest="round_name")
    ap.add_argument("--frozen-at", required=True,
                    help="ISO 8601;时间由人给,工件不读墙钟")
    args = ap.parse_args()
    path = freeze(args.run_dir, tag=args.tag, round_name=args.round_name,
                  frozen_at=args.frozen_at)
    prov = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps({
        "wrote": str(path),
        "tag": args.tag,
        "model": prov["readers"][args.tag]["model"],
        "frozen_slots": len(prov["slots"]),
        "artifact_sha256": prov["readers"][args.tag]["artifact_sha256"][:16] + "…",
        "prompt_digest": prov["prompt_digest"][:16] + "…",
        "schema_digest": prov["schema_digest"][:16] + "…",
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
