"""M1 六个确定性门禁(ARCHITECTURE.md §6),产出 gate_report.json。

全部确定性,不调模型。检查逻辑搬自 dws-derisk 已测实现:
C1–C7 ← routers.py::consistency_review,citation ← round3.py::citation_holds
(子串包含,不是 token 匹配),agree ← paired.py::agree(双都缺值算一致 ——
预注册的字面读法)。

负面发现规则(宪章四):门禁跑不了 = blocking_level "blocking",severity "high"。
"不适用"(如 citation 对 PARTY/DATE 字段)不是跑不了 —— 记 unavailable,
不产生 finding。契约不变量:blocking == (blocking_level == "blocking")。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field

from .dws import StoredResponse
from .evidence import region_ocr_text
from .fields import AMOUNT_FIELDS, FIELDS, Kind, amount, date_parts, normalise
from .ocr import OcrUnavailable

PASS, WARNING, FAIL, UNAVAILABLE = "pass", "warning", "fail", "unavailable"

GATE_IDS = (
    "arithmetic_consistency",
    "field_wellformed",
    "extraction_present",
    "citation_holds",
    "cross_mode_agreement",
    "visual_corroboration",
)

_EPSILON = 0.02  # C1/C2 容差,与 routers.py 一致


@dataclass
class Finding:
    gate_id: str
    doc_id: str
    field: str | None
    severity: str
    blocking_level: str
    repair_owner: str  # human | re_extract | vision_reread
    recommendation: str
    evidence_ref: str
    message: str

    def to_dict(self, finding_id: str) -> dict:
        blocking = self.blocking_level == "blocking"
        return {
            "finding_id": finding_id,
            "gate_id": self.gate_id,
            "doc_id": self.doc_id,
            "field": self.field,
            "severity": self.severity,
            "blocking_level": self.blocking_level,
            "blocking": blocking,  # 契约不变量:由 blocking_level 派生,不独立赋值
            "repair_owner": self.repair_owner,
            "recommendation": self.recommendation,
            "evidence_ref": self.evidence_ref,
            "message": self.message,
        }


@dataclass
class GateAccumulator:
    findings: list[Finding] = dc_field(default_factory=list)
    seq: int = 0

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def serialise(self) -> list[dict]:
        return [f.to_dict(f"GF-{i + 1:04d}") for i, f in enumerate(self.findings)]


# ---------------------------------------------------------------- 单项检查

def _c1_c3(data: dict) -> dict[str, set[str]]:
    """C1/C2/C3:每个恒等式失败时, feeding 字段全部进 review(不猜 culprit)。
    返回 {check_id: failed_fields};输入不全的恒等式不出现在结果里(没法评)。"""
    failed: dict[str, set[str]] = {}
    net, vat, gross = (amount(data.get(k)) for k in ("total_net", "total_vat", "total_gross"))
    due = amount(data.get("amount_due"))
    if None not in (net, vat, gross) and abs((net + vat) - gross) > _EPSILON:
        failed["C1"] = {"total_net", "total_vat", "total_gross"}
    if None not in (gross, due) and abs(gross - due) > _EPSILON:
        failed["C2"] = {"total_gross", "amount_due"}
    issued, expires = date_parts(data.get("issue_date")), date_parts(data.get("due_date"))
    if issued and expires and list(reversed(issued)) > list(reversed(expires)):
        # 反序比较:字段顺序未知,但同一份文档上两个日期同格式,
        # 反序后的数字元组给出正确的时序(routers.py 的注解)。
        failed["C3"] = {"issue_date", "due_date"}
    return failed


def _wellformed_failure(name: str, value: object) -> str | None:
    """C4/C5/C6:返回失败的 check_id,通过返回 None。值缺失不归这里管(C7)。"""
    from .fields import FIELD_KINDS

    kind = FIELD_KINDS[name]
    if kind is Kind.AMOUNT and amount(value) is None:
        return "C4"
    if kind is Kind.DATE and date_parts(value) is None:
        return "C5"
    if name == "invoice_number" and not re.search(r"[a-zA-Z0-9]", str(value)):
        return "C6"
    return None


def _rel_bbox_first(meta: dict, pages: list) -> tuple[int, list[float]] | None:
    """第一个引用框的相对坐标 —— 搬 round3._rel_bbox:citation 只看第一框。"""
    src = (meta.get("source_bboxes") or [meta])[0]
    bbox = src.get("bbox")
    if not bbox:
        return None
    idx = src.get("pageIndex", meta.get("pageIndex", 0))
    page = next(
        (p for p in pages if p.get("page") == idx + 1),
        pages[idx] if idx < len(pages) else None,
    )
    if not page or not page.get("width"):
        return None
    w, h = page["width"], page["height"]
    return idx, [bbox["x"] / w, bbox["y"] / h,
                 (bbox["x"] + bbox["width"]) / w, (bbox["y"] + bbox["height"]) / h]


def _citation_holds(doc_id: str, response: StoredResponse, field_name: str) -> bool | None:
    """值是否出现在 DWS 自称的引用区(独立 OCR)。逐字语义搬 round3.citation_holds。

    子串包含:want(值剥非字母数字) in have(区域文本剥非字母数字)。
    None = 判不了(字段 kind 不适用 / 无引用 / 无值 / 区域无词)。
    OCR 文件缺失时抛 OcrUnavailable —— 由门禁层记阻断,不在这里吞。
    """
    from .fields import FIELD_KINDS

    kind = FIELD_KINDS[field_name]
    if kind not in (Kind.AMOUNT, Kind.CODE):
        return None
    meta = response.meta.get(field_name)
    value = response.data.get(field_name)
    if not meta or value is None:
        return None
    located = _rel_bbox_first(meta, response.pages)
    if not located:
        return None
    page_idx, rect = located
    # OCR 缺失在这一步抛 OcrUnavailable(region_ocr_text → iter_words → load_ocr)
    text = region_ocr_text(doc_id, page_idx + 1, rect)
    if not text:
        return None
    want = re.sub(r"[^0-9A-Za-z]", "", str(value)).lower()
    have = re.sub(r"[^0-9A-Za-z]", "", text).lower()
    if not want:
        return None
    return want in have


def _agree(a: object, b: object, field_name: str) -> bool:
    """双模式是否说了同一个东西(规范化后)。双都缺值算一致(paired.py 的预注册读法)。"""
    from .fields import FIELD_KINDS

    kind = FIELD_KINDS[field_name]
    return normalise(a, kind) == normalise(b, kind)


# ---------------------------------------------------------------- 门禁事务

def run_gates(
    doc_ids: list[str],
    *,
    understand: dict[str, StoredResponse | None],
    agentic: dict[str, StoredResponse | None],
    vision_answers: dict[str, dict[tuple[str, str], dict]],
    ledger_sha256: str,
    artifact_digest: str,
) -> dict:
    """门禁事务(§5.3):绑定确切工件哈希后运行;签名对不上则拒绝执行由调用方检查。

    返回 gate_report:evaluations(每 doc×field×gate 的裁决)+ findings + 输入签名。
    """
    acc = GateAccumulator()
    evaluations: dict[str, dict[str, dict[str, str]]] = {}

    for doc_id in doc_ids:
        u = understand.get(doc_id)
        a = agentic.get(doc_id)
        per_field: dict[str, dict[str, str]] = {f: {} for f in FIELDS}

        # ---- 响应缺失:不是"所有字段失败",是门禁基础设施跑不了 —— 文档级阻断
        if u is None:
            acc.add(Finding(
                "extraction_present", doc_id, None, "high", "blocking",
                "re_extract", "understand 响应缺失或 HTTP 非 200,重跑抽取",
                f"raw/{doc_id}.understand.json", "DWS understand 响应不可用",
            ))
            for f in FIELDS:
                per_field[f] = {g: UNAVAILABLE for g in GATE_IDS}
            evaluations[doc_id] = per_field
            continue
        try:
            _evaluate_doc(doc_id, u, a, vision_answers, acc, per_field)
        except Exception as exc:  # noqa: BLE001 —— 门禁自己出错也是阻断发现
            # 宪章四:一个门禁崩在一份文档上,不许带垮整批,也不许假装评过
            acc.add(Finding(
                "gate_error", doc_id, None, "high", "blocking",
                "human", f"门禁执行异常,查这份文档的存盘响应:{exc!r}",
                f"doc:{doc_id}", f"gate_error: {exc!r}",
            ))
            for f in FIELDS:
                per_field[f] = {g: UNAVAILABLE for g in GATE_IDS}
        evaluations[doc_id] = per_field

    return {
        "input_signature": {"ledger_sha256": ledger_sha256, "artifact_digest": artifact_digest},
        "evaluations": evaluations,
        "findings": acc.serialise(),
    }


def _evaluate_doc(
    doc_id: str,
    u: StoredResponse,
    a: StoredResponse | None,
    vision_answers: dict[str, dict[tuple[str, str], dict]],
    acc: GateAccumulator,
    per_field: dict[str, dict[str, str]],
) -> None:
    """评估一份文档的六个门禁;异常由 run_gates 记成阻断发现。"""
    if a is None:
        acc.add(Finding(
            "cross_mode_agreement", doc_id, None, "high", "blocking",
            "re_extract", "agentic 响应缺失或 HTTP 非 200,重跑抽取",
            f"raw/{doc_id}.agentic.json", "DWS agentic 响应不可用,双模式门禁跑不了",
        ))

    failed_checks = _c1_c3(u.data)
    for check_id, fields_hit in failed_checks.items():
        acc.add(Finding(
            "arithmetic_consistency", doc_id, None, "medium", "non_blocking",
            "human", f"{check_id} 恒等式不成立;feeding 字段全部进复核,不猜哪个错",
            f"doc:{doc_id}", f"{check_id} 失败,涉及 {sorted(fields_hit)}",
        ))

    for field_name in FIELDS:
        verdicts: dict[str, str] = {}
        value = u.data.get(field_name)
        present = value is not None and str(value).strip() != ""

        # ---- extraction_present(C7):缺值是阻断发现,带修复路由
        if present:
            verdicts["extraction_present"] = PASS
        else:
            verdicts["extraction_present"] = FAIL
            acc.add(Finding(
                "extraction_present", doc_id, field_name, "high", "blocking",
                "vision_reread", "DWS 未返回值;整页读图在页面别处找,或人工补",
                f"doc:{doc_id}/field:{field_name}", "DWS 未返回该字段的值",
            ))

        # ---- field_wellformed(C4/C5/C6)
        if not present:
            verdicts["field_wellformed"] = UNAVAILABLE
        else:
            bad = _wellformed_failure(field_name, value)
            if bad is None:
                verdicts["field_wellformed"] = PASS
            else:
                verdicts["field_wellformed"] = FAIL
                acc.add(Finding(
                    "field_wellformed", doc_id, field_name, "medium", "non_blocking",
                    "re_extract", f"{bad} 不通过:值 '{value}' 不符合该字段形态",
                    f"doc:{doc_id}/field:{field_name}", f"{bad}: {value!r}",
                ))

        # ---- arithmetic_consistency(C1/C2/C3,按字段归 verdict)
        # 一个字段只要被任意一个输入齐全的恒等式评过,就是 pass/fail;
        # 全都没评过才是 unavailable。gross 同时喂 C1 和 C2,只看 C1 会漏。
        net_v, vat_v = amount(u.data.get("total_net")), amount(u.data.get("total_vat"))
        gross_v, due_v = amount(u.data.get("total_gross")), amount(u.data.get("amount_due"))
        c1_ready = None not in (net_v, vat_v, gross_v)
        c2_ready = None not in (gross_v, due_v)
        c3_ready = (date_parts(u.data.get("issue_date")) is not None
                    and date_parts(u.data.get("due_date")) is not None)
        feeding = {
            "total_net": c1_ready, "total_vat": c1_ready,
            "total_gross": c1_ready or c2_ready, "amount_due": c2_ready,
            "issue_date": c3_ready, "due_date": c3_ready,
        }
        participates = [c for c, fs in failed_checks.items() if field_name in fs]
        if participates:
            verdicts["arithmetic_consistency"] = FAIL
        elif feeding.get(field_name):
            verdicts["arithmetic_consistency"] = PASS
        else:
            verdicts["arithmetic_consistency"] = UNAVAILABLE  # 没被任何恒等式评到

        # ---- citation_holds(独立 OCR;OCR 缺失 = 阻断)
        try:
            holds = _citation_holds(doc_id, u, field_name)
        except OcrUnavailable:
            holds = None
            verdicts["citation_holds"] = UNAVAILABLE
            acc.add(Finding(
                "citation_holds", doc_id, field_name, "high", "blocking",
                "human", "独立 OCR 缺失,citation 门禁跑不了",
                f"doc:{doc_id}/field:{field_name}", "OcrUnavailable",
            ))
        else:
            if holds is True:
                verdicts["citation_holds"] = PASS
            elif holds is False:
                verdicts["citation_holds"] = FAIL
                acc.add(Finding(
                    "citation_holds", doc_id, field_name, "high", "non_blocking",
                    "vision_reread", "值不在 DWS 自称的引用区(独立 OCR 判定)",
                    f"doc:{doc_id}/field:{field_name}", f"citation 不成立: {value!r}",
                ))
            else:
                verdicts["citation_holds"] = UNAVAILABLE

        # ---- cross_mode_agreement(已知不独立,lift 2.40× —— panel 必须声明)
        if a is None:
            verdicts["cross_mode_agreement"] = UNAVAILABLE
        elif _agree(value, a.data.get(field_name), field_name):
            verdicts["cross_mode_agreement"] = PASS
        else:
            verdicts["cross_mode_agreement"] = FAIL
            acc.add(Finding(
                "cross_mode_agreement", doc_id, field_name, "medium", "non_blocking",
                "human", "两模式规范化后不一致,进人工裁决",
                f"doc:{doc_id}/field:{field_name}",
                f"understand={value!r} vs agentic={a.data.get(field_name)!r}",
            ))

        # ---- visual_corroboration(整页读图;只有第六轮 60 份有存盘答案)
        if not present:
            verdicts["visual_corroboration"] = UNAVAILABLE  # 没有值可印证
        else:
            attempted = []
            for model, rows in vision_answers.items():
                row = rows.get((doc_id, field_name))
                if row and row["value"] and row["value"].upper() != "ABSTAIN":
                    attempted.append((model, row["value"]))
            if not attempted:
                verdicts["visual_corroboration"] = UNAVAILABLE  # 尚未测量,不是跑不了
            else:
                from .fields import FIELD_KINDS

                want = normalise(value, FIELD_KINDS[field_name])
                corroborated = any(
                    normalise(v, FIELD_KINDS[field_name]) is not None
                    and normalise(v, FIELD_KINDS[field_name]) == want
                    for _, v in attempted
                )
                if corroborated:
                    verdicts["visual_corroboration"] = PASS
                else:
                    # 读图自己也错得起(§6:未被 flag 的字段 7.8% 真错全过)——
                    # 记 warning 不记 fail:这是"值得看",不是"判定错"
                    verdicts["visual_corroboration"] = WARNING
                    acc.add(Finding(
                        "visual_corroboration", doc_id, field_name, "medium", "non_blocking",
                        "human",
                        f"整页读图不支持该值(尝试了 {len(attempted)} 位读者)",
                        f"doc:{doc_id}/field:{field_name}",
                        f"dws={value!r}; vision={[f'{m}:{v}' for m, v in attempted]}",
                    ))

        per_field[field_name] = verdicts
