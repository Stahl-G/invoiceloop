"""阶段 D / Q3:主体方向空间原型 —— SEALED-2 上量准确率(零 API)。

主指标(预注册):抽出的 seller_name span 最近标签侧,是否正确预测
「抽取是否与 DocILE vendor_name 一致」。

判据:准确率 < 0.80 → 第 3 项作废,不进 gates/routing。

用法:
  INVOICELOOP_CORPUS=runs/sealed2-workspace \\
    python3 scripts/subject_direction_proto.py

  # 可选:写 JSON 明细
  ... --json /tmp/subject_direction_sealed2.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from invoiceloop.eval_norm import eval_normalise  # noqa: E402
from invoiceloop.fields import Kind  # noqa: E402
from invoiceloop.ocr import OcrUnavailable  # noqa: E402
from invoiceloop.safety_metrics import truth  # noqa: E402
from invoiceloop import subject_direction as sd  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault(
    "INVOICELOOP_CORPUS", str(REPO / "runs" / "sealed2-workspace")
)


def _doc_ids() -> list[str]:
    return json.loads(
        (REPO / "runs" / "sealed2-workspace" / "doc_list.json").read_text()
    )["doc_ids"]


def _seller_spans() -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """→ (按文档分组的 seller span, span_id → span 索引)。"""
    path = REPO / "runs" / "sealed2" / "evidence_span_registry.json"
    by_doc: dict[str, list[dict]] = {}
    by_id: dict[str, dict] = {}
    for s in json.loads(path.read_text()):
        by_id[s["span_id"]] = s
        if s.get("field") == "seller_name" and s.get("bbox_rel"):
            by_doc.setdefault(s["doc_id"], []).append(s)
    return by_doc, by_id


def _seller_claims() -> dict[str, list[dict]]:
    """每份文档的全部 seller_name claim —— 不折叠。

    SEALED-2 上 93 份里有 80 份有 **两条** seller_name claim(双模式:
    `dws_agentic` 与 `dws_understand`)。早先版本按 doc_id 覆写只留最后
    一条,再配 `spans[doc_id][0]`,claim 的值与 span 的位置可能来自不同
    模式。现在保留全部,由 `span_ids` 严格绑定。
    """
    ledger = json.loads(
        (REPO / "runs" / "sealed2" / "field_ledger.json").read_text()
    )
    out: dict[str, list[dict]] = {}
    for c in ledger["claims"]:
        if c.get("field") == "seller_name" and c.get("value") not in (None, ""):
            out.setdefault(c["doc_id"], []).append(c)
    return out


def _bound_pairs(claims: list[dict], by_id: dict[str, dict]) -> list[tuple[dict, dict]]:
    """(claim, span) —— span 必须由该 claim 自己的 span_ids 指名。"""
    pairs = []
    for c in claims:
        for sid in c.get("span_ids") or []:
            s = by_id.get(sid)
            if s and s.get("field") == "seller_name" and s.get("bbox_rel"):
                pairs.append((c, s))
                break
    return pairs


def _party_match(a: str | None, b: str | None) -> bool | None:
    if not a or not b:
        return None
    return eval_normalise(a, Kind.PARTY) == eval_normalise(b, Kind.PARTY)


def measure(doc_ids: list[str]) -> dict:
    spans, span_by_id = _seller_spans()
    claims = _seller_claims()
    rows: list[dict] = []
    primary_n = primary_correct = 0
    variants = {
        "maxdist_0_20": {"n": 0, "correct": 0},
        "both_sides_closer": {"n": 0, "correct": 0},
        "gt_bbox_nearest_seller_side": {"n": 0, "correct": 0},
    }
    skip = {
        "ocr_unavailable": 0,
        "no_seller_span": 0,
        "no_bound_span": 0,
        "no_gt_or_claim": 0,
        "no_same_page_label": 0,
    }

    from invoiceloop.ocr import derisk_root

    for doc_id in doc_ids:
        try:
            labels = sd.find_labels(doc_id)
        except OcrUnavailable:
            skip["ocr_unavailable"] += 1
            rows.append({"doc_id": doc_id, "status": "ocr_unavailable"})
            continue

        ss = spans.get(doc_id)
        gt = truth(doc_id).get("seller_name")

        # 旁证 A:真值 vendor bbox 最近标签是否卖方侧(不依赖抽取)
        ann = derisk_root() / "data" / "docile" / "annotations" / f"{doc_id}.json"
        if ann.exists() and labels:
            for item in json.loads(ann.read_text())["field_extractions"]:
                if item.get("fieldtype") == "vendor_name" and item.get("bbox"):
                    n_gt = sd.nearest_label(
                        item["bbox"], int(item.get("page", 0)) + 1, labels
                    )
                    if n_gt:
                        variants["gt_bbox_nearest_seller_side"]["n"] += 1
                        if n_gt["side"] == "seller":
                            variants["gt_bbox_nearest_seller_side"]["correct"] += 1
                    break

        if not ss:
            skip["no_seller_span"] += 1
            rows.append({"doc_id": doc_id, "status": "no_seller_span",
                         "n_labels": len(labels)})
            continue

        # 一份文档可有多条 seller_name claim(双模式)。每条只配自己
        # span_ids 指名的 span —— 不用 spans[doc_id][0]。
        pairs = _bound_pairs(claims.get(doc_id) or [], span_by_id)
        if not pairs:
            skip["no_bound_span"] += 1
            rows.append({"doc_id": doc_id, "status": "no_bound_span",
                         "n_labels": len(labels)})
            continue

        for claim, span in pairs:
            pred = claim["value"]
            matched = _party_match(pred, gt)
            if matched is None:
                skip["no_gt_or_claim"] += 1
                rows.append({"doc_id": doc_id, "status": "no_gt_or_claim",
                             "claim_id": claim["claim_id"],
                             "n_labels": len(labels)})
                continue

            nearest = sd.nearest_label(span["bbox_rel"], span["page"], labels)
            row = {
                "doc_id": doc_id,
                "claim_id": claim["claim_id"],
                "drafted_by": claim.get("drafted_by"),
                "span_id": span["span_id"],
                "status": "scored" if nearest else "no_same_page_label",
                "n_labels": len(labels),
                "label_names": sorted({l["name"] for l in labels}),
                "pred": pred,
                "gt": gt,
                "pred_matches_gt": matched,
                "nearest": None if not nearest else {
                    "name": nearest["name"],
                    "side": nearest["side"],
                    "dist": nearest["dist"],
                },
            }

            if nearest is None:
                skip["no_same_page_label"] += 1
                rows.append(row)
                continue

            primary_n += 1
            expect = sd.predict_match_from_side(nearest["side"])
            ok = expect == matched
            if ok:
                primary_correct += 1
            row["expect_match"] = expect
            row["correct"] = ok
            rows.append(row)

            n20 = sd.nearest_label(
                span["bbox_rel"], span["page"], labels, max_dist=0.20
            )
            if n20:
                variants["maxdist_0_20"]["n"] += 1
                if sd.predict_match_from_side(n20["side"]) == matched:
                    variants["maxdist_0_20"]["correct"] += 1

            side = sd.closer_side(span["bbox_rel"], span["page"], labels)
            if side:
                variants["both_sides_closer"]["n"] += 1
                if sd.predict_match_from_side(side) == matched:
                    variants["both_sides_closer"]["correct"] += 1

    acc = primary_correct / primary_n if primary_n else None
    var_out = {}
    for name, v in variants.items():
        var_out[name] = {
            **v,
            "accuracy": (v["correct"] / v["n"]) if v["n"] else None,
        }

    return {
        "engine": sd.ENGINE,
        "digest": sd.digest(),
        "kill_line": sd.KILL_LINE,
        "n_docs": len(doc_ids),
        "primary": {
            "metric": "nearest_label_side_predicts_party_match",
            "n": primary_n,
            "correct": primary_correct,
            "accuracy": acc,
            "verdict": (
                "PASS" if acc is not None and acc >= sd.KILL_LINE else "FAIL"
            ),
        },
        "variants": var_out,
        "skip": skip,
        "coverage": {
            "docs_with_any_label": len({
                r["doc_id"] for r in rows if r.get("n_labels", 0) > 0
            }),
            "claims_scored_primary": primary_n,
            "docs_scored_primary": len({
                r["doc_id"] for r in rows if r.get("status") == "scored"
            }),
        },
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, help="写完整结果 JSON")
    args = ap.parse_args()

    result = measure(_doc_ids())
    p = result["primary"]
    print(f"engine={result['engine']} digest={result['digest'][:16]}")
    print(
        f"primary n={p['n']} correct={p['correct']} "
        f"accuracy={p['accuracy']} kill_line={result['kill_line']} "
        f"verdict={p['verdict']}"
    )
    print("variants:")
    for name, v in result["variants"].items():
        print(f"  {name}: n={v['n']} acc={v['accuracy']}")
    print("skip:", result["skip"])
    print("coverage:", result["coverage"])
    if p["verdict"] == "FAIL":
        print(
            "\nKILL:准确率 < 80% —— 主体方向不做机检,"
            "只走人工队列。不接线 gates。"
        )
    if args.json:
        args.json.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
