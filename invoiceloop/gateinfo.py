"""One-line explanations of the six gates — the data source for hover tooltips,
shared by the workbench and the static panel.

Every line was written against the implementation in gates.py and the
pre-registered conclusions in THRESHOLDS.md (charter rule six: do not describe a
gate as checking something it does not). A fidelity review on 2026-08-03 caught
and corrected three distortions:

- the 118 misbound rows were caught by the **freeze transaction's document-level
  binding** (token ≥80% against the whole document's OCR), not by the citation
  gate. The citation gate acts on already-accepted values, and its measured record
  is round three pushing TIER1 silent errors from 4.4% to 3.1%, on roughly half of
  observations being decidable;
- vision reading's independence from DWS **failed** the pre-registered line
  (lift 1.29× / 1.33×, below 1.5). The real reason it warns rather than vetoes is
  that readers' own silent-error rate of 8.6–15.8% is far above the 1% line and
  they abstain 59–61% of the time;
- the round-six conclusion rests on **two** readers: GPT 5.6 SOL's 359 rows were
  voided wholesale because 63.1% of their content appeared in other documents, so
  they do not enter the determination.

Implementation basis: arithmetic C1/C2/C3 (tolerance 0.02), well-formedness C4–C6,
presence C7, citation via round3.citation_holds (`want in have` substring,
AMOUNT/CODE, first cited box), dual-mode paired.agree (both absent counts as
agreement; the modes are correlated, so agreement does not mean correct), and
vision WARNING that does not veto (gates.py: "the reader can be wrong too").
"""

from __future__ import annotations

_INFO: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "arithmetic_consistency": {
            "intro": "Arithmetic: checks net+VAT=gross, gross=due, and date order, tolerance 0.02.",
            "pass": "The identities hold.",
            "fail": "An identity breaks — mis-extraction or a genuinely inconsistent invoice; a human must judge which.",
            "unavailable": "Not enough fields to compute.",
        },
        "field_wellformed": {
            "intro": "Well-formedness: amounts parse, dates really exist, codes are clean.",
            "pass": "Well-formed.",
            "fail": "Malformed (e.g. an impossible date) — most likely mis-extraction.",
            "unavailable": "Nothing to check.",
        },
        "extraction_present": {
            "intro": "Presence: did the extraction service (DWS) return this field?",
            "pass": "A value was returned.",
            "fail": "The extraction service returned nothing — an honest absence, not proof the field is missing from the page; worth a human look.",
            "unavailable": "Extraction response missing or the check errored — not evaluated; recorded as a document-level blocking finding.",
        },
        "citation_holds": {
            "intro": "Citation: does the region the extraction service (DWS) pointed to actually contain this value, per the independent OCR (substring check, amounts/codes)?",
            "pass": "The value is in the cited region.",
            "fail": "Not in the cited region. In calibration this layer cut silent deviations from 4.4% to 3.1% (about half of observations were decidable).",
            "unavailable": "No cited region or not applicable for this field kind — not checkable; if the independent OCR is missing, the check could not run and is recorded as blocking.",
        },
        "cross_mode_agreement": {
            "intro": "Two-mode: do the extraction service's two modes (understand / agentic) agree after normalization?",
            "pass": "They agree — but the modes are correlated, so agreement is not proof of correctness.",
            "fail": "The values differ — not mechanically decidable; in label-convention disputes both readings may be legitimate and go to human adjudication.",
            "unavailable": "Only one mode available to compare.",
        },
        "visual_corroboration": {
            "intro": "Vision: frontier readers read the full page and are compared with the extraction service's (DWS) value. Vision passed the pre-registered independence bar vs DWS, but readers' own silent-error rate far exceeds 1% and they abstain ~60% of the time — so it warns, it never convicts.",
            "pass": "Vision agrees with DWS (reference).",
            "warning": "Vision disagrees with DWS — worth a human look.",
            "unavailable": "No vision answers, or no value to compare.",
        },
        "cross_document_duplicate": {
            "intro": "Cross-document duplicate: within this run's document set, do two invoices share the same number and seller? Numbering is per-seller, so the key is (seller, number). Content conflict and resubmission are both flagged.",
            "fail": "Same number + same seller as another document — content conflict or suspected resubmission. Not a verdict: a human must look at both side by side; never counted into error rates.",
            "unavailable": "Not evaluated (missing number or seller — already recorded by presence checks).",
        },
        "doctype_evidence": {
            "intro": "Document type evidence: does the page's independent OCR contain a literal phrase that supports the extractor's invoice_type claim?",
            "pass": "A supporting phrase was found on the page.",
            "fail": "No literal support — type-conditional policy relaxations must not apply; unrelated fields keep their normal routes.",
            "unavailable": "No type claim, unmapped class, or OCR unavailable — type-conditional rules stay off.",
        },
    },
    "zh": {
        "arithmetic_consistency": {
            "intro": "算术一致性:验算 净额+税额=总额、总额=应付、日期先后,容差 0.02。",
            "pass": "恒等式成立。",
            "fail": "恒等式不成立 —— 可能抽错,也可能票面本身矛盾,需要人来判是哪种。",
            "unavailable": "字段不齐,无法验算。",
        },
        "field_wellformed": {
            "intro": "形态:金额可解析、日期真实存在、编码规整。",
            "pass": "形态合法。",
            "fail": "形态非法(如不存在的日期)—— 大概率是抽取错误。",
            "unavailable": "无值可验。",
        },
        "extraction_present": {
            "intro": "在场:抽取服务(DWS)是否返回了这个字段。",
            "pass": "有返回值。",
            "fail": "抽取服务没返回 —— 诚实缺失,不等于页面上没有,值得人工找一找。",
            "unavailable": "抽取响应缺失或检查异常 —— 本档未评估,已记文档级阻断。",
        },
        "citation_holds": {
            "intro": "引用:抽取服务(DWS)指的引用区里,独立 OCR 是否真能找到这个值(子串比对,金额/编码类)。",
            "pass": "引用区里有这个值。",
            "fail": "引用区里找不到这个值。校准实测:这层把漏检从 4.4% 压到 3.1%(约一半观测可判定)。",
            "unavailable": "没有引用区或字段类不适用 —— 无法机检;若是独立 OCR 缺失 —— 检查跑不了,已记阻断。",
        },
        "cross_mode_agreement": {
            "intro": "双模式:抽取服务两种模式(understand / agentic)归一化后的答案是否一致。",
            "pass": "一致 —— 但两种模式相关,一致不等于对。",
            "fail": "两个值不同 —— 无法机判哪个对;若属纸面口径争议,两种读法可能都成立,进人工裁决。",
            "unavailable": "只有单模式结果,无法比对。",
        },
        "visual_corroboration": {
            "intro": "读图:前沿模型整页读图,与抽取服务(DWS)的值比对。读图相对 DWS 的独立性过了预注册线,但读者自身静默错误远超 1% 线、弃权近六成 —— 所以只作警示,不作否决。",
            "pass": "读图与 DWS 一致(参考)。",
            "warning": "读图与 DWS 不一致 —— 值得人看一眼。",
            "unavailable": "没有读图作答,或没有值可比对。",
        },
        "cross_document_duplicate": {
            "intro": "跨文档查重:本 run 的文档集里,两份发票是否同号同卖家。编号空间按卖家独立,所以分组键是(卖家, 票号);内容冲突与疑似重复提交都会报。",
            "fail": "与另一份文档同号同卖家 —— 内容冲突或疑似重复提交。这不是判决:需要人把两份并排看;不进错误率。",
            "unavailable": "未评估(缺票号或缺卖家 —— 缺口已由在场检查记过)。",
        },
        "doctype_evidence": {
            "intro": "单据类型字面证据:独立 OCR 上是否出现支撑抽取器 invoice_type 声明的字面短语。",
            "pass": "页面上找到了支撑短语。",
            "fail": "无字面支撑 —— 不许启用类型级放宽;与类型无关的字段照常路由。",
            "unavailable": "无类型声明、映不进词表、或 OCR 不可用 —— 类型级规则保持关闭。",
        },
    },
}


def tooltip(gate_id: str, verdict: str, lang: str = "zh") -> str:
    """一个门禁 chip 的悬停说明:这门查什么 + 当前状态在这行意味着什么。"""
    gate = _INFO.get(lang, _INFO["en"]).get(gate_id)
    if not gate:
        return gate_id
    state = gate.get(verdict) or gate.get("unavailable", "")
    return f"{gate['intro']}{state}"
