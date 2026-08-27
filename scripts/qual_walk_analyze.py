#!/usr/bin/env python3
"""ADK 行走轮 P1–P5 对照(零 API,只读账本与冻结工件)。

P2/P3 直接复用 hitl_round_analyze(采纳率与人时口径不另立一套)。
P1/P4/P5 是本轮新增的结构性判据。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import hitl_round_analyze  # noqa: E402
import qual_walk_plan  # noqa: E402
from invoiceloop import suggest_provenance  # noqa: E402
from invoiceloop.fields import FIELD_KINDS, normalise  # noqa: E402


def exposure_sets(run_dir: Path, prov: dict, entries: list[dict]) -> dict:
    """四类曝光分开数 —— 混在一起就会把「agent 参与了」说得比事实大。

    HITL-narrow 实测(2026-08-14 那一轮,本轮写作时复算):
    队列槽 32,其中**只有 19 个有字段级建议**,13 个没有;而 16 份队列文档
    **全部**显示了文档级 ADK 卡片。所以「文档卡曝光」和「字段建议曝光」是
    两个数,「agent 在每个槽都发言」是假的。
    """
    routing = json.loads(
        (run_dir / "routing_report.json").read_text(encoding="utf-8"))
    expected = {f"{d}|{f}" for d, f in
                qual_walk_plan.queue_slots(routing["routes"],
                                           routing.get("policy") or {})}
    reading_path = run_dir / "vision" / "invoice_read.json"
    reading = json.loads(reading_path.read_text(encoding="utf-8")) \
        if reading_path.is_file() else {}
    card_docs = set(reading.get("docs") or {})
    field_slots = set(prov.get("slots") or {})
    adjudicated = {f"{e['doc_id']}|{e['field']}" for e in entries}
    expected_docs = {k.split("|")[0] for k in expected}
    return {
        "expected_queue_slots": len(expected),
        "expected_queue_docs": len(expected_docs),
        "document_card_docs": len(card_docs),
        "queue_docs_with_a_card": len(expected_docs & card_docs),
        "field_suggestion_slots": len(field_slots),
        "queue_slots_with_a_field_suggestion": len(expected & field_slots),
        "queue_slots_without_a_field_suggestion": sorted(expected - field_slots),
        "adjudicated_slots": len(adjudicated),
        "queue_slots_not_adjudicated": sorted(expected - adjudicated),
        "adjudicated_outside_the_queue": sorted(adjudicated - expected),
        "walk_complete": not (expected - adjudicated),
        "_expected": sorted(expected),
        "_adjudicated": sorted(adjudicated),
    }


def provenance_coverage(entries: list[dict], prov: dict, sets: dict) -> dict:
    """P1:该走的槽走完之后,其中有建议的每一槽是不是都带**正确**的溯源。

    两处与第一版不同,都是被挑出来的:

    1. **先过完整性闸。** 分母取 frozen ∩ adjudicated 的话,没走完的槽会
       自己从分母消失 —— 走一半也能得 100%。所以 walk_complete 为假时
       coverage 照算但 P1 **不可评**,不许写成成立。
    2. **逐槽精确相等,不是非空。** 三个字段填着别的哈希一样「非空」。
       期望值由 suggest_provenance.derive 重新导出,与账本逐字节比。
    """
    frozen = prov.get("slots") or {}
    latest: dict[str, dict] = {}
    for entry in sorted(entries, key=lambda e: e["seq"]):
        latest[f"{entry['doc_id']}|{entry['field']}"] = entry
    denom_keys = [k for k in sets["_expected"] if k in frozen and k in latest]
    exact = 0
    gaps = []
    for key in denom_keys:
        entry = latest[key]
        doc_id, field = key.split("|", 1)
        try:
            want = suggest_provenance.derive(
                prov, doc_id, field, entry.get("suggestion_seen"))
        except ValueError as exc:  # 对账本身不通 = 该槽没有可信溯源
            want = None
            gaps.append({"decision_id": entry["decision_id"], "slot": key,
                         "reconcile_error": str(exc)})
            continue
        got = (entry.get("suggestion_artifact_sha256"),
               entry.get("suggestion_model"))
        if want is not None and got == want:
            exact += 1
        else:
            gaps.append({"decision_id": entry["decision_id"], "slot": key,
                         "want": want, "got": got})
    return {
        "walk_complete": sets["walk_complete"],
        "evaluable": sets["walk_complete"] and bool(denom_keys),
        "denominator": "预期队列槽 ∩ 冻结建议槽 ∩ 已裁决槽",
        "denominator_n": len(denom_keys),
        "with_exact_provenance": exact,
        "coverage": round(exact / len(denom_keys), 4) if denom_keys else None,
        "gaps": gaps,
    }


def model_dissent_adopted(entries: list[dict], claims: dict) -> dict:
    """P4:模型给的值与冻结声明不同,人**改成了模型那个值**的槽。

    这是顾问层唯一无法用结构保证代替的价值主张:模型说了别的,而人信了。
    = 0 就如实登记为未证明,不找补。
    """
    hits = []
    for entry in entries:
        seen = entry.get("suggestion_seen") or ""
        if not seen.startswith("agree:") or entry["decision"] != "correct":
            continue
        suggested = seen.split(":", 1)[1]
        kind = FIELD_KINDS.get(entry["field"])
        if normalise(str(entry.get("corrected_value") or ""), kind) != \
                normalise(suggested, kind):
            continue
        claim = claims.get(entry.get("claim_id") or "") or {}
        if normalise(str(claim.get("value") or ""), kind) == \
                normalise(suggested, kind):
            continue  # 模型只是复述了声明,不算异议
        hits.append({"decision_id": entry["decision_id"],
                     "doc_id": entry["doc_id"], "field": entry["field"],
                     "claim_value": claim.get("value"),
                     "model_value": suggested})
    return {"n": len(hits), "slots": hits}


def authority_violations(entries: list[dict], prov: dict, run_dir: Path) -> dict:
    """P5:零权威。四条检查,任何一条非空 = 违反。

    第二条查的是**成分表这个常量**,不是某个 run 的快照实例:
    SNAPSHOT_COMPONENTS 是写死的七个文件名,扫实例永远扫不出建议工件 ——
    那是同义反复。真正会出事的是哪天有人把 vision/ 加进成分表。

    第四条是写集:只查署名字符串证明不了「agent 没有权威」,它只证明没人
    把模型名填进 adjudicator。真要证的是模型那一趟只碰了 vision/ 与
    agent_calls/,账本、门禁报告、快照一个字节没动。
    """
    from invoiceloop.snapshot import SNAPSHOT_COMPONENTS

    models = {str(rec.get("model")) for rec in
              (prov.get("readers") or {}).values() if rec.get("model")}
    tags = set(prov.get("readers") or {})
    signed_by_model = [e["decision_id"] for e in entries
                       if str(e.get("adjudicator") or "") in models]
    suggestion_in_contract = sorted(
        c for c in SNAPSHOT_COMPONENTS
        if "answers6" in c or "invoice_read" in c or c.startswith("vision/"))
    claims = json.loads(
        (run_dir / "field_ledger.json").read_text(encoding="utf-8"))["claims"]
    claims_drafted_by_agent = [
        c["claim_id"] for c in claims
        if str(c.get("drafted_by") or "") in (models | tags)]

    ws_path = run_dir / "agent_writeset.json"
    writeset_ok = None
    unexpected_writes: list[str] = []
    if ws_path.is_file():
        ws = json.loads(ws_path.read_text(encoding="utf-8"))
        allowed = ("vision/", "agent_calls/")
        unexpected_writes = sorted(
            path for path in (ws.get("changed") or [])
            if not path.startswith(allowed))
        writeset_ok = not unexpected_writes
    return {
        "decisions_signed_by_a_model": signed_by_model,
        "suggestion_paths_in_snapshot_contract": suggestion_in_contract,
        "claims_drafted_by_the_agent": claims_drafted_by_agent,
        "agent_writeset_recorded": writeset_ok is not None,
        "agent_writeset_clean": writeset_ok,
        "unexpected_writes": unexpected_writes,
        "clean": not (signed_by_model or suggestion_in_contract
                      or claims_drafted_by_agent or unexpected_writes)
                 and writeset_ok is True,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    args = ap.parse_args()
    run_dir = args.run
    base = hitl_round_analyze.analyze(run_dir)
    entries = [json.loads(x) for x in
               (run_dir / "adjudication_ledger.jsonl")
               .read_text(encoding="utf-8").splitlines() if x.strip()]
    claims = {c["claim_id"]: c for c in json.loads(
        (run_dir / "field_ledger.json").read_text())["claims"]}
    prov = suggest_provenance.load(run_dir) or {}
    sets = exposure_sets(run_dir, prov, entries)
    print(json.dumps({
        **base,
        "exposure": {k: v for k, v in sets.items() if not k.startswith("_")},
        "P1_provenance": provenance_coverage(entries, prov, sets),
        "P2_adoption": base["suggestions"],
        "P3_timing": base["timing"],
        "P4_model_dissent_adopted": model_dissent_adopted(entries, claims),
        "P5_authority": authority_violations(entries, prov, run_dir),
        "provenance_frozen_at": prov.get("frozen_at"),
        "prompt_digest": prov.get("prompt_digest"),
        "schema_digest": prov.get("schema_digest"),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
