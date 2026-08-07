"""Cross-document duplicate detection (C8): conflicting content and resubmission
under one invoice number.

All six gates are single-document; this is the first cross-document dimension,
and it looks at a run's whole document set. Same charter, same discipline:

- a finding is not a verdict: two documents sharing a number does not mean "this
  is a forgery", it means "a person must look" — non-blocking,
  repair_owner=human, and it does not enter the error rate;
- the grouping key is (seller_name, invoice_number), because number spaces belong
  to sellers; the same number from two sellers is not a conflict;
- values come only from the frozen ledger (dws_understand claims first, agentic
  as fallback) — drafts do not count, and duplicate detection is built on values
  that already passed binding;
- deterministic and zero-API: the same frozen ledger always yields the same
  conflict set.
"""

from __future__ import annotations

from .fields import Kind, normalise

#: 查重的取值字段:分组键 + 内容指纹
_FIELDS_OF_RECORD = ("invoice_number", "seller_name", "total_gross", "issue_date")


def _doc_values(claims: list[dict]) -> dict[str, dict[str, str]]:
    """每文档的查重取值。dws_understand 优先 —— 与 matrix 行的取值口径一致。"""
    by_doc: dict[str, dict[str, str]] = {}
    for c in claims:
        if c["field"] not in _FIELDS_OF_RECORD:
            continue
        slot = by_doc.setdefault(c["doc_id"], {})
        if c["field"] not in slot or c["drafted_by"] == "dws_understand":
            slot[c["field"]] = c["value"]
    return by_doc


def duplicate_groups(claims: list[dict]) -> list[dict]:
    """冻结声明 → 冲突组列表(按分组键排序,确定性)。

    每组:{seller, invoice_number, kind, docs:[{doc_id, total_gross, issue_date}]}
    kind:
    - content_conflict:同号同卖家但 gross/日期不一致 —— 经典造假信号
    - resubmission:    同号同卖家同内容 —— 疑似重复提交(重复报销信号)
    缺号/缺卖家的文档不参与(那是 extraction_present 已经记过的缺口,
    查重不在缺数据上猜)。
    """
    values = _doc_values(claims)
    groups: dict[tuple[str, str], list[str]] = {}
    for doc_id, vals in values.items():
        number = normalise(vals.get("invoice_number"), Kind.CODE)
        seller = normalise(vals.get("seller_name"), Kind.PARTY)
        if not number or not seller:
            continue
        groups.setdefault((seller, number), []).append(doc_id)

    out: list[dict] = []
    for (seller, number), docs in sorted(groups.items()):
        docs = sorted(set(docs))
        if len(docs) < 2:
            continue
        sig = {
            d: (normalise(values[d].get("total_gross"), Kind.AMOUNT),
                normalise(values[d].get("issue_date"), Kind.DATE))
            for d in docs
        }
        kind = ("content_conflict" if len(set(sig.values())) > 1
                else "resubmission")
        out.append({
            "seller": seller,
            "invoice_number": number,
            "kind": kind,
            "docs": [{"doc_id": d, "total_gross": sig[d][0],
                      "issue_date": sig[d][1]} for d in docs],
        })
    return out
