#!/usr/bin/env python3
"""文档触达四臂测量(docs/DOCTOUCH_PREREG_2026-08-18.md,零 API)。

问的是「窄放行契约能让多少张发票根本不用被人打开」。零触达是**路由时属性** ——
`release_profile.document_touch_metrics` 只吃 routes,不需要人。

臂 A/B/D 各跑一次完整流水线:门禁本身吃 policy 的 absent 队列
(`pipeline.py:281-284`),所以不能跑一次再换策略重算 —— 手搓那一步正是
SEALED-4 H7 首验失败的成因。臂 C 是 B 的**投影**(同路由,换契约字段集),
不重跑。

用法:python3 scripts/doctouch_arms.py --out runs/doctouch-2026-08-18
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop import harness, ocr, pipeline  # noqa: E402
from invoiceloop.release_profile import (  # noqa: E402
    PAYMENT_REQUIRED_V1, document_touch_metrics,
)
from invoiceloop.routing import policy_digest  # noqa: E402
from invoiceloop.safety_metrics import score_routes, truth  # noqa: E402
from invoiceloop.scope import classify_broadcast_ocr  # noqa: E402
from invoiceloop.sealed_batch import _corpus_environment, frozen_harness  # noqa: E402
from invoiceloop import truth_caliber as _caliber  # noqa: E402
from invoiceloop.harness import schema_digest  # noqa: E402

DERISK = Path.home() / "Developer" / "dws-derisk"
SCHEMA = REPO / "invoiceloop" / "harnesses" / "HAR-0001" / "extraction_schema.json"
DOC_RE = re.compile(r"^([0-9a-f]{24})\.(agentic|understand)\.json$")

#: 预注册 §3 的四个臂。C 是 B 的投影,不是一次跑。
ARM_POLICIES = {
    "HAR-0021": REPO / "docs/evidence/absence_v3_2026-08-10/HAR-0021.routing_policy.json",
    "HAR-0023": REPO / "docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json",
}


def discover_dual_mode() -> dict[str, Path]:
    """→ {doc_id: 那份响应所在的 raw 目录}。双模式齐全才算。"""
    roots = [DERISK / "raw"]
    roots += sorted(REPO.glob("runs/*/raw")) + sorted(REPO.glob("runs/*/*/raw"))
    modes: dict[str, set[str]] = collections.defaultdict(set)
    where: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.json"):
            m = DOC_RE.match(path.name)
            if m:
                modes[m.group(1)].add(m.group(2))
                where.setdefault(m.group(1), root)
    return {doc: where[doc] for doc, ms in modes.items() if len(ms) == 2}


def strata(doc_ids: list[str]) -> dict[str, str]:
    """doc_id → strong / weak / none(broadcast-pilot-v1 冻结实现)。"""
    out = {}
    for doc in doc_ids:
        path = DERISK / "data" / "docile" / "ocr" / f"{doc}.json"
        out[doc] = classify_broadcast_ocr(path)["strength"] if path.is_file() else "unknown"
    return out


def assemble(ws: Path, sources: dict[str, Path]) -> dict:
    """一份工作区装齐 660 份的 pdf / ocr / 双模式响应。"""
    for sub in ("input/pdfs", "ocr", "raw"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    stats = {"docs": 0, "missing": []}
    for doc, raw_root in sorted(sources.items()):
        pdf = DERISK / "data" / "docile" / "pdfs" / f"{doc}.pdf"
        ocr_src = DERISK / "data" / "docile" / "ocr" / f"{doc}.json"
        if not (pdf.is_file() and ocr_src.is_file()):
            stats["missing"].append(doc)
            continue
        for src, dst in (
            (pdf, ws / "input" / "pdfs" / f"{doc}.pdf"),
            (ocr_src, ws / "ocr" / f"{doc}.json"),
            (raw_root / f"{doc}.understand.json", ws / "raw" / f"{doc}.understand.json"),
            (raw_root / f"{doc}.agentic.json", ws / "raw" / f"{doc}.agentic.json"),
        ):
            if not dst.exists():
                dst.write_bytes(src.read_bytes())
        stats["docs"] += 1
    return stats


def active_for(arm: str) -> dict:
    if arm == "HAR-0001":
        policy = harness._builtin_policy()   # 包内保守默认,与 loop_generalization 同源
        policy_sha = None
    else:
        path = ARM_POLICIES[arm]
        policy = json.loads(path.read_text(encoding="utf-8"))
        policy_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return {
        "harness_id": arm,
        "policy": policy,
        "policy_digest": policy_digest(policy),
        "policy_sha256": policy_sha,
        "schema": schema,
        "schema_digest": schema_digest(schema),
        "schema_sha256": hashlib.sha256(SCHEMA.read_bytes()).hexdigest(),
    }


def measure(routes: list[dict], policy: dict, strength: dict[str, str],
            understand: dict) -> dict:
    """每层报预注册 §4 的四组数。"""
    out = {}
    for layer in ("strong", "weak", "none", "ALL"):
        rows = [r for r in routes
                if layer == "ALL" or strength.get(r["doc_id"]) == layer]
        if not rows:
            continue
        touch = document_touch_metrics(rows, policy)
        safety = score_routes(
            rows, truth_of=truth,
            understand_of=lambda d: understand.get(d),
            caliber_of=_caliber.caliber_dispute,
        )
        out[layer] = {
            "docs": touch["docs"],
            "zero_touch_docs": touch["zero_touch_docs"],
            "zero_touch_pct": round(
                100.0 * touch["zero_touch_docs"] / max(touch["docs"], 1), 1),
            "unresolved_release_slots": touch["unresolved_release_slots"],
            "qa_probe_slots": touch["qa_probe_slots"],
            "human_queue_slots": sum(
                1 for r in rows if r["route"] not in ("auto_accept", "auto_absent")),
            "slots": len(rows),
            "silent_absent_true": safety.get("silent_absent_true"),
            "caliber_disputes": safety.get("caliber_disputes"),
            "silent_wrong": safety.get("silent_wrong"),
            "absent_hits": safety.get("absent_hits"),
            "value_hits": safety.get("value_hits"),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    sources = discover_dual_mode()
    doc_ids = sorted(sources)
    print(f"双模式齐全 {len(doc_ids)} 份", flush=True)
    strength = strata(doc_ids)
    print("  分层 " + json.dumps(dict(collections.Counter(strength.values())),
                                 ensure_ascii=False), flush=True)

    ws = out / "corpus"
    print("装配语料…", flush=True)
    stats = assemble(ws, sources)
    print(f"  装齐 {stats['docs']};缺件 {len(stats['missing'])}", flush=True)
    doc_ids = [d for d in doc_ids if d not in set(stats["missing"])]

    understand = {}
    with _corpus_environment(ws):
        from invoiceloop.dws import load_response
        for doc in doc_ids:
            resp = load_response(doc, "understand")
            understand[doc] = resp.data if resp else None

    results = {"n_docs": len(doc_ids),
               "strata": dict(collections.Counter(
                   strength[d] for d in doc_ids)),
               "arms": {}}

    routes_by_arm = {}
    for arm in ("HAR-0001", "HAR-0021", "HAR-0023"):
        arm_dir = out / "arms" / arm
        active = active_for(arm)
        if not arm_dir.exists():
            print(f"跑 {arm}…", flush=True)
            with _corpus_environment(ws), frozen_harness(active):
                pipeline.run(doc_ids, arm_dir, render_crops=False,
                             include_vision=False, out_of_calibration=True)
        report = json.loads((arm_dir / "routing_report.json").read_text())
        routes_by_arm[arm] = report["routes"]
        results["arms"][arm] = {
            "policy_digest": report["policy_digest"],
            "policy_sha256": active["policy_sha256"],
            "release_profile": (active["policy"].get("release_profile") or {}).get("id"),
            "release_tier1_explicit": active["policy"].get("release_tier1_explicit"),
            "gate": "census" if not active["policy"].get("release_profile")
                    else "payment_required_v1",
            "metrics": measure(report["routes"], active["policy"],
                               strength, understand),
        }

    # 臂 C:B 的路由,换成付款契约的字段集 —— 投影,不重跑。
    projected = json.loads(ARM_POLICIES["HAR-0021"].read_text(encoding="utf-8"))
    projected["release_profile"] = {"id": "payment_required_v1",
                                    "fields": sorted(PAYMENT_REQUIRED_V1)}
    results["arms"]["HAR-0021+payment(projection)"] = {
        "note": "臂 C:HAR-0021 路由不变,只把放行闸换成付款三字段。"
                "与 HAR-0023 的差 = release_tier1_explicit: false 的作用。",
        "gate": "payment_required_v1",
        "release_tier1_explicit": projected.get("release_tier1_explicit"),
        "metrics": measure(routes_by_arm["HAR-0021"], projected,
                           strength, understand),
    }

    (out / "doctouch_metrics.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print()
    hdr = f"{'arm':34s} {'gate':18s} {'层':7s} {'零触达':>12s} {'队列槽':>8s} {'真静默':>7s}"
    print(hdr); print("-" * len(hdr))
    for arm, rec in results["arms"].items():
        for layer, m in rec["metrics"].items():
            print(f"{arm:34s} {rec['gate']:18s} {layer:7s} "
                  f"{m['zero_touch_docs']:>5d}/{m['docs']:<4d}({m['zero_touch_pct']:4.1f}%) "
                  f"{m['human_queue_slots']:>8d} {m['silent_absent_true']:>7}")
    print(f"\n→ {out/'doctouch_metrics.json'}")


if __name__ == "__main__":
    main()
