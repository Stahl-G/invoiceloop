"""六门的一句话说明 —— 悬停提示的数据源(workbench 与静态 panel 共用)。

每条都对照 gates.py 的实现与 THRESHOLDS.md 的预注册结论写过(宪章六:
不说门禁实际不查的东西)。2026-08-03 保真复核抓出并已修正三处失真:
- 118 行错位是**冻结事务的文档级绑定**抓的(token ≥80% 对整份文档 OCR),
  不是引用门 —— 引用门的作用对象已接纳值,实测记录是第三轮把 T1 静默
  从 4.4% 压到 3.1%(约一半观测可判定)
- 读图相对 DWS 的独立性**过了**预注册线(lift 1.29×/1.33× < 1.5);
  只警示不否决的真实理由是读者自身静默错误 8.6–15.8% 远超 1% 线、
  弃权 59–61%
- 第六轮结论只建立在**两位**读者上(GPT 5.6 SOL 的 359 行因 63.1% 内容
  出现在别的文档被整体作废,不进判定)

实现依据:算术 C1/C2/C3(容差 0.02)、形态 C4-C6、在场 C7、
引用 round3.citation_holds(`want in have` 子串,AMOUNT/CODE,首引用框)、
双模式 paired.agree(双缺=一致;两模式相关,一致≠对)、
读图 WARNING 不否决(gates.py「读图自己也错得起」)。
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
    },
}


def tooltip(gate_id: str, verdict: str, lang: str = "zh") -> str:
    """一个门禁 chip 的悬停说明:这门查什么 + 当前状态在这行意味着什么。"""
    gate = _INFO.get(lang, _INFO["en"]).get(gate_id)
    if not gate:
        return gate_id
    state = gate.get(verdict) or gate.get("unavailable", "")
    return f"{gate['intro']}{state}"
