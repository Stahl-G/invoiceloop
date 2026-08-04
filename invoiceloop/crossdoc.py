"""跨文档查重(C8):同号发票的内容冲突与重复提交。

六道门禁全是单文档的;这是第一个跨文档维度,看的是一个 run 的整个文档集。
纪律(与门禁同一宪章):

- finding 不是 verdict:同号冲突 ≠ 「是假发票」,是「必须人看」——
  non-blocking,repair_owner=human,不进错误率;
- 分组键是 (seller_name, invoice_number) —— 编号空间是按卖家的,
  不同卖家同号不算冲突;
- 取值只来自冻结账本(dws_understand 声明优先,缺了取 agentic)——
  草稿不算数,查重建立在已过绑定的值上;
- 确定性、零 API:同一冻结账本必然产出同一组冲突。
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
