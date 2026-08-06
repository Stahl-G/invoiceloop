"""工程词 → 业务话。给不写代码的应付会计(AP)看的那一层。

为什么单独一个模块:工作台的改进循环页原本直接印内部词表 ——
`cohort`、`HAR-0005`、`absent_expected`、`TIER1 · unsupported · review`、
`silent_absent 0→0`。这些是**账本里的**名字,是可复算、可对拍的前提,
不能改;但它们不该是**人眼前**的名字。两者分开,页面翻译,工件不动。

纪律:
- 只翻译,不改变含义,更不柔化风险。「漏掉真实存在的值」就是要让人
  看懂它有多糟,不许说成「轻微偏差」;
- 找不到译名时**原样回退**,不猜 —— 页面上出现一个没译的英文词,
  是「这里还没做」的诚实信号,比编一个好听的名字强;
- 内部标识(harness id、digest、doc_id)不翻译,收进「技术细节」折叠区。
"""

from __future__ import annotations

import re

#: 十个受评字段的业务名。AP 认的是「税额」,不是 total_vat。
FIELDS = {
    "invoice_number": ("发票号", "Invoice no."),
    "issue_date": ("开票日期", "Issue date"),
    "due_date": ("付款到期日", "Due date"),
    "seller_name": ("供应商名称", "Supplier"),
    "seller_vat_id": ("供应商税号", "Supplier tax ID"),
    "buyer_name": ("买方名称", "Buyer"),
    "total_net": ("不含税金额", "Net amount"),
    "total_vat": ("税额", "VAT amount"),
    "total_gross": ("含税总额", "Gross total"),
    "amount_due": ("应付金额", "Amount due"),
}

#: 复核时点的那个「问题类型」
REASONS = {
    "WRONG_VALUE": ("值抄错了", "Wrong value"),
    "WRONG_FIELD_MAPPING": ("取成了别的字段", "Wrong field taken"),
    "BAD_SOURCE_BINDING": ("在单据上的位置标错了", "Wrong place on the page"),
    "MISSING_EXTRACTION": ("单据上有,但没抽到", "On the page but not captured"),
    "NORMALIZATION_ERROR": ("格式判断错了", "Formatting misjudged"),
    "ROUTING_FALSE_NEGATIVE": ("该拦下来却放过了", "Should have been flagged"),
    "ROUTING_FALSE_POSITIVE": ("不该拦却拦下了", "Flagged without cause"),
    "CONFIRMED_ABSENT": ("单据上确实没有", "Genuinely not on the page"),
    "NOT_APPLICABLE": ("这张单据不适用", "Not applicable here"),
    "AMBIGUOUS_DOCUMENT": ("单据本身说不清", "The document itself is unclear"),
    "PROVIDER_FAILURE": ("抽取服务出错", "Extraction service failed"),
    "REVIEWER_PREFERENCE": ("按我们内部习惯", "Our internal convention"),
    "OTHER": ("其他", "Other"),
}

#: 人做的动作
DECISIONS = {
    "accept": ("认可", "Accepted"),
    "correct": ("改正", "Corrected"),
    "reject": ("驳回", "Rejected"),
    "confirm_absent": ("确认没有", "Confirmed absent"),
    "not_applicable": ("不适用", "Not applicable"),
    "abstain": ("拿不准", "Undecided"),
}

#: 证据强度 —— 说的是「有几路来源互相印证」,不是「有多准」
STRENGTHS = {
    "unsupported": ("没有旁证", "No corroboration"),
    "single_source": ("只有一路来源", "Single source"),
    "corroborated": ("多路来源对上了", "Corroborated"),
}

#: 槽位去向
ROUTES = {
    "auto_accept": ("系统直接采用", "Taken automatically"),
    "auto_absent": ("按规则记为「没有」", "Recorded absent by rule"),
    "review": ("交给你看", "Sent to you"),
    "block": ("阻断", "Blocked"),
    "escalate": ("升级处理", "Escalated"),
}

#: 字段等级
TIERS = {
    "TIER1": ("关键字段", "Key field"),
    "TIER2": ("一般字段", "Secondary field"),
}


def _pick(table: dict, key, lang: str) -> str:
    """查表;查不到就原样回退 —— 没译名比编一个好听的名字诚实。"""
    row = table.get(key)
    if row is None:
        return str(key) if key is not None else "—"
    return row[1] if lang == "en" else row[0]


def field(name, lang: str = "zh") -> str:
    return _pick(FIELDS, name, lang)


def reason(code, lang: str = "zh") -> str:
    return _pick(REASONS, code, lang)


def decision(name, lang: str = "zh") -> str:
    return _pick(DECISIONS, name, lang)


def strength(name, lang: str = "zh") -> str:
    return _pick(STRENGTHS, name, lang)


def route(name, lang: str = "zh") -> str:
    return _pick(ROUTES, name, lang)


def tier(name, lang: str = "zh") -> str:
    return _pick(TIERS, name, lang)


def headline(action: str, target: str, lang: str = "zh") -> str:
    """一条建议/改动做什么 —— 一句话,主语是「系统」,宾语是 AP 的活。

    target 是字段业务名(cohort 类)或字段业务名(schema 类)。
    """
    zh = {
        "absent_expected":
            f"以后「{target}」在单据上找不到时,不再逐张问你",
        "auto_accept":
            f"以后「{target}」在证据对得上时,系统直接采用,不再问你",
        "revoke":
            f"收回一条已经生效的自动放行:「{target}」重新交给你看",
        "schema_description":
            f"改进「{target}」的抽取说明,让系统更容易在单据上找到它",
    }
    en = {
        "absent_expected":
            f"Stop asking you about “{target}” when it is not on the page",
        "auto_accept":
            f"Take “{target}” automatically when the evidence lines up",
        "revoke":
            f"Withdraw an active auto-accept: send “{target}” back to you",
        "schema_description":
            f"Reword how “{target}” is described so it gets found more often",
    }
    table = en if lang == "en" else zh
    return table.get(action, f"{action} · {target}")


def confidence(level, lang: str = "zh") -> str:
    table = {"high": ("高", "High"), "medium": ("中", "Medium"),
             "low": ("低", "Low")}
    return _pick(table, level, lang)


def invoices(n: int, lang: str = "zh") -> str:
    """张数 —— AP 的计量单位是「几张发票」,不是「n=9」。"""
    return f"{n} invoice{'s' if n != 1 else ''}" if lang == "en" else f"{n} 张发票"


#: 携带溯源前缀 —— 展示层剥掉,工件保留
_REPLAY = re.compile(r"^\s*\[replay [^\]]*\]\s*")


def quote(text: str, lang: str = "zh") -> tuple[str, bool]:
    """复核原话 → (给人看的正文, 是不是上一轮携带过来的)。

    账本里的原话带 `[replay run-0002 HD-0009]` 前缀 —— 那是携带溯源,
    对复核者本人毫无意义(他只想看见自己写的「页面上没有」)。
    **只在展示层剥掉**:工件、mine 报告、AI 读到的包一律保留原文。
    """
    raw = (text or "").strip()
    stripped = _REPLAY.sub("", raw)
    return stripped, stripped != raw
