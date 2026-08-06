"""suggest:让模型读复核笔记,写**提案草稿** —— 人读完才算数。

宪章位置(与 `vision_ingest` 完全同款,不是新机制):
模型只写草稿文件(`improve/suggestions.json`,无 ID、无策略、不进账本);
要不要变成候选,由人在工作台上读完原话与草稿后点一下,再走既有的
`propose → evaluate → promote` —— 反事实评估、人工晋升、QA 探针一个不少。

**它不在改进控制面里。** `improve` 的四个子命令仍然全确定性零模型;
suggest 是旁挂的顾问层,输出带 `advisory: true` 与被引用的笔记 id。
理由是 `gates.py` 首行那条:确定性路径不调模型。让模型提议放松安全规则
而没有人复核,是这套架构存在意义的反面;让模型帮人**读** 123 行笔记,
则只是把人从翻账本里解放出来 —— 差别全在「谁签字」。

草稿的硬约束(写入前逐条校验,违反即拒):
- 只能引用 mine_report 里已有的 cohort 特征(field/tier/strength/route),
  不许出现 doc_id、期望值或任何单文档硬编码 —— 与 routing 的 cohort
  白名单同一条纪律;
- 每条建议必须给出它读的笔记(`cites`),空引用的建议直接丢弃 ——
  没有出处的建议就是模型的意见,不是从证据来的;
- 只提 `auto_accept` / `absent_expected` / `revoke` 三种动作,别的不收。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .routing import ROUTES  # noqa: F401  (词表来源,便于读者定位)

#: cohort 类动作(改路由策略)
_COHORT_ACTIONS = ("auto_accept", "absent_expected", "revoke")
#: schema 类动作(改抽取字段描述)—— 2026-08-06 加入。理由:复核负载里
#: 最大的一块是「DWS 什么都没返回」(88 份实测 138/485 槽),cohort 够不着它,
#: 只有字段描述能。约束比 cohort 更紧:只改已有受评字段的 description,
#: 增删字段 / 加 required / 改 type 由 improve.lint_schema 挡在提案之前。
_SCHEMA_ACTIONS = ("schema_description",)
ACTIONS = _COHORT_ACTIONS + _SCHEMA_ACTIONS
#: cohort 只许引用通用特征 —— 与 improve._COHORT_KEYS 同源,不许放宽。
#: **按动作分开**:absent_expected 是字段级规则(「这个字段在这类发票上
#: 本来就没有」是字段的属性,与证据强度、TIER 无关),improve._ABSENT_KEYS
#: 只认 field。2026-08-06 之前两类共用一张表,于是模型给 absent_expected
#: 配上 tier/strength,人在工作台点「采纳」必被 lint 拒 ——
#: **草稿在构造上就不可能被采纳**。校验层要和下游同一口径,否则它放行的
#: 东西下游照样拒,人白点一次。
_ALLOWED_COHORT_KEYS = ("field", "tier", "strength")
_ALLOWED_ABSENT_KEYS = ("field",)


def _cohort_keys_for(action: str) -> tuple[str, ...]:
    return (_ALLOWED_ABSENT_KEYS if action == "absent_expected"
            else _ALLOWED_COHORT_KEYS)
#: description 上限 —— 提示词是发给 DWS 的,不是让模型写小作文的地方
_MAX_DESCRIPTION = 400

_PROMPT = """你在读一份发票复核系统的 cohort 统计、当前抽取字段描述,
以及复核者手写笔记。

你的任务:提出**候选改动**,供人类复核后决定是否采纳。你没有决定权。

你可以提两类改动:

**A. 路由策略(cohort)** —— action 为:
- `auto_accept`:该 cohort 可自动放行
- `absent_expected`:该字段的缺失是预期的(如美国发票没有 VAT 号)
- `revoke`:应撤销某条已生效的放松
cohort 只能用 field / tier / strength 描述,禁止出现 doc_id、具体金额、
具体发票号等单文档特征。

**B. 抽取字段描述(schema)** —— action 为 `schema_description`。
给出 field 与新的英文 description。用在这种情况:笔记显示抽取器**根本没返回值**
或**返回了错误的那个字段**,而原因看起来是描述没说清这个字段在真实发票上
长什么样。只改措辞,不要要求必填、不要新增字段。

规则:
1. 每条建议必须引用它依据的笔记(给出 note 的序号)。没有出处的建议不要提。
2. 证据弱就说弱。宁可少提一条,不要凑数。
3. 你看到的是「没产生修正的复核」,这不等于「这些复核没价值」——
   没被抽查不等于没有错。
4. `prediction` 要写出你预期**会伤害什么**,不只是会改善什么。

按这个 JSON 结构回答,不要有别的文字:
{"suggestions": [
  {"action": "absent_expected", "cohort": {"field": "..."},
   "finding": "你从笔记里读到的事实", "prediction": "采纳后你预期会发生什么",
   "confidence": "high|medium|low", "cites": [0, 3]},
  {"action": "schema_description", "field": "...",
   "description": "新的英文字段描述",
   "finding": "...", "prediction": "...", "confidence": "...", "cites": [5]}]}
"""


def _packet(report: dict, schema: dict | None = None) -> tuple[str, list[dict]]:
    """mine_report(+ 当前抽取 schema)→ (给模型的文本, 笔记表)。笔记表是
    引用的锚,模型给的 cites 下标必须落在它里面,否则该条建议丢弃。

    schema 进包的理由:让模型提的是**对现状的 diff**,而不是凭空写一段
    描述 —— 它得先看见 due_date 现在只写了 "Payment due date."。
    """
    notes: list[dict] = []
    lines = []
    if schema:
        lines.append("## 当前抽取字段描述(schema_description 的改动对象)\n")
        for name, spec in sorted((schema.get("properties") or {}).items()):
            lines.append(f"- {name}: {spec.get('description', '')!r}")
        lines.append("")
    lines.append("## cohort 统计\n")
    for c in report.get("cohorts", []):
        lines.append(
            f"- field={c['field']} tier={c['tier']} "
            f"strength={c.get('support_strength')} route={c.get('route')} "
            f"复核{c['reviewed']} 接受{c['accepted']} 修正{c['corrected']} "
            f"拒绝{c['rejected']} 确认缺失{c['confirmed_absent']}")
        for n in c.get("notes", []):
            notes.append({**n, "field": c["field"]})
    if report.get("overturned_auto_accepts"):
        lines.append("\n## 自动放行被人推翻(收紧信号,优先看)\n")
        for o in report["overturned_auto_accepts"]:
            lines.append(f"- field={o['field']} 人做了 {o['human_action']}"
                         f"({o.get('reason_code')}):{o.get('rationale', '')}")
            notes.append({"doc_id": o["doc_id"], "field": o["field"],
                          "decision": o["human_action"],
                          "reason_code": o.get("reason_code"),
                          "rationale": o.get("rationale", "")})
    lines.append("\n## 复核者原话(编号即引用下标)\n")
    for i, n in enumerate(notes):
        lines.append(f"[{i}] field={n['field']} 决策={n.get('decision')} "
                     f"心码={n.get('reason_code')}:{n['rationale']}")
    return "\n".join(lines), notes


def validate(raw: dict, notes: list[dict]) -> tuple[list[dict], list[str]]:
    """草稿 → (可用建议, 丢弃理由)。**纯函数,可单测,不碰网络。**

    两类建议共用「必须给出处」这一条;各自的形状约束分开查。
    """
    from .fields import FIELD_KINDS

    kept, dropped = [], []
    for i, s in enumerate(raw.get("suggestions") or []):
        label = f"suggestion[{i}]"
        action = s.get("action")
        if action not in ACTIONS:
            dropped.append(f"{label}:action {action!r} 不在词表")
            continue

        entry: dict = {}
        if action in _SCHEMA_ACTIONS:
            field = s.get("field")
            if field not in FIELD_KINDS:
                dropped.append(
                    f"{label}:field {field!r} 不是受评字段 —— "
                    f"schema 建议只能改已有的十个字段")
                continue
            description = str(s.get("description") or "").strip()
            if not description:
                dropped.append(f"{label}:schema 建议没给 description")
                continue
            if len(description) > _MAX_DESCRIPTION:
                dropped.append(
                    f"{label}:description 超过 {_MAX_DESCRIPTION} 字 —— "
                    f"字段描述不是写小作文的地方")
                continue
            entry = {"kind": "schema", "field": field,
                     "description": description}
        else:
            cohort = s.get("cohort")
            if not isinstance(cohort, dict) or not cohort:
                dropped.append(f"{label}:没有 cohort")
                continue
            # 两种「多余的键」必须分开处理,合并处理会开后门:
            #   1. 压根不在策略词表里的(doc_id、具体金额、发票号)——
            #      **整条丢弃**。这是反硬编码纪律,剪掉再放行等于绕过它;
            #   2. 在词表里、但这个动作用不上的(absent_expected 配了
            #      tier/strength)—— 剪掉即可。形状用错不是内容有问题,
            #      丢整条 = 一条有出处的建议因为多写两个字被扔了。
            outside = [k for k in cohort if k not in _ALLOWED_COHORT_KEYS]
            if outside:
                dropped.append(
                    f"{label}:cohort 出现非白名单键 {outside} —— "
                    f"单文档特征不许进策略")
                continue
            allowed = _cohort_keys_for(action)
            extra = [k for k in cohort if k not in allowed]
            if extra:
                cohort = {k: v for k, v in cohort.items() if k in allowed}
                if not cohort:
                    dropped.append(
                        f"{label}:去掉 {action} 用不上的特征"
                        f"({'、'.join(extra)})之后就空了 —— 没有可路由的东西")
                    continue
                dropped.append(
                    f"{label}:已剪掉 {action} 用不上的特征"
                    f"({'、'.join(extra)}),建议保留;它是字段级规则,只认 "
                    f"{'、'.join(allowed)}")
            entry = {"kind": "cohort", "cohort": cohort}

        cites = [c for c in (s.get("cites") or [])
                 if isinstance(c, int) and 0 <= c < len(notes)]
        if not cites:
            dropped.append(f"{label}:引用为空或越界 —— 没出处的建议不收")
            continue
        kept.append({
            **entry,
            "action": action,
            "finding": str(s.get("finding", ""))[:500],
            "prediction": str(s.get("prediction", ""))[:500],
            "confidence": s.get("confidence") if s.get("confidence") in
            ("high", "medium", "low") else "low",
            "cites": cites,
            "cited_notes": [notes[c] for c in cites],
        })
    return kept, dropped


def suggest(workspace: Path, *, model: str | None = None,
            api_key: str | None = None) -> dict:
    """读 mine_report → 调模型 → 校验 → 写 improve/suggestions.json。

    没有 mine_report 就先跑 `improve mine`。缺 key 时抛错而不是静默跳过
    (宪章四:跑不了要说,不要压成一个空结果)。
    """
    workspace = Path(workspace)
    report_path = workspace / "improve" / "mine_report.json"
    if not report_path.exists():
        raise FileNotFoundError(
            f"没有 {report_path} —— 先跑 improve mine")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    try:
        from .harness import load_active
        active_schema = load_active(workspace).get("schema")
    except Exception:  # noqa: BLE001 —— 拿不到 schema 就只提 cohort,不中断
        active_schema = None
    packet, notes = _packet(report, active_schema)
    if not notes:
        out = {"advisory": True, "model": model or "", "suggestions": [],
               "dropped": [], "note_count": 0,
               "reason": "没有可引用的复核笔记 —— 模型无从读起,不编"}
        _write(workspace, out)
        return out

    from .vision_ingest import _credentials

    key_env, base_url, default_model = _credentials()
    key = api_key or key_env
    if not key:
        raise RuntimeError(
            "缺 ANTHROPIC_API_KEY —— suggest 是顾问层,没有 key 就没有建议;"
            "改进控制面(improve mine/propose/evaluate/promote)不受影响")
    # 选定的模型只算一次,调用与记录用**同一个变量**。2026-08-06 之前
    # 这两处是两个不同的表达式(调用带 INVOICELOOP_SUGGEST_MODEL,记录不带),
    # 于是 suggestions.json 会写着一个根本没被调用过的模型名 ——
    # 顾问层的工件对「谁写的这份草稿」说了假话,溯源就断在这里(宪章六)。
    chosen = (model or os.environ.get("INVOICELOOP_SUGGEST_MODEL")
              or default_model)
    raw = _ask(packet, key=key, base_url=base_url, model=chosen)
    kept, dropped = validate(raw, notes)
    out = {
        "advisory": True,
        "model": chosen,
        "note_count": len(notes),
        "suggestions": kept,
        "dropped": dropped,
        "disclaimer": "模型草稿,不是系统发现。采纳与否由人决定,"
                      "采纳后仍走 propose → evaluate → promote 与 QA 探针。",
    }
    _write(workspace, out)
    return out


def _write(workspace: Path, payload: dict) -> Path:
    out_dir = Path(workspace) / "improve"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / "suggestions.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


#: 输出预算。推理型模型会先写一大段 thinking 块,预算给小了就全烧在推理上:
#: deepseek-v4-flash 实测 2000 与 8000 都被整段吃掉(stop_reason=max_tokens、
#: content 里只有一个 thinking 块,一个 text 块都没轮到)。给足,别让预算
#: 成为「模型没说话」的伪装。`INVOICELOOP_SUGGEST_MAX_TOKENS` 可覆盖。
_MAX_TOKENS = 32000
#: 思考预算(effort)。留空 = 不传,由服务端默认;设了就按 Anthropic 的
#: extended thinking 形状传 `thinking.budget_tokens`。
_THINKING_ENV = "INVOICELOOP_SUGGEST_THINKING_BUDGET"


def _budget() -> int:
    raw = os.environ.get("INVOICELOOP_SUGGEST_MAX_TOKENS")
    try:
        return max(int(raw), 1024) if raw else _MAX_TOKENS
    except ValueError:
        return _MAX_TOKENS


def _ask(packet: str, *, key: str, base_url: str, model: str) -> dict:
    """一次 messages 调用,取回 JSON。解析失败如实抛,不猜。"""
    import requests

    from .vision_ingest import API_VERSION

    budget = _budget()
    payload = {"model": model, "max_tokens": budget,
               "messages": [{"role": "user",
                             "content": f"{_PROMPT}\n\n{packet}"}]}
    thinking = os.environ.get(_THINKING_ENV)
    if thinking:
        payload["thinking"] = {"type": "enabled",
                               "budget_tokens": int(thinking)}
    response = requests.post(
        f"{base_url.rstrip('/')}/v1/messages",
        headers={"x-api-key": key, "anthropic-version": API_VERSION,
                 "content-type": "application/json"},
        json=payload,
        timeout=600,
    )
    response.raise_for_status()
    body = response.json()
    # thinking 块没有 text 键,天然被跳过;这里只收模型真正写出来的答案
    text = "".join(b.get("text", "") for b in body.get("content", []))
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        # 宪章四:说清楚到底怎么了。「没返回 JSON」把「预算被推理烧光」
        # 说成了「模型没说话」,照着这句话去调 prompt 会白费功夫
        stop = body.get("stop_reason")
        used = (body.get("usage") or {}).get("output_tokens")
        kinds = [b.get("type") for b in body.get("content", [])]
        if stop == "max_tokens":
            raise ValueError(
                f"模型在写完 JSON 之前用光了输出预算(stop_reason=max_tokens,"
                f"output_tokens={used}/{budget},"
                f"返回的块={kinds})—— 调大 _MAX_TOKENS 或换个话少的模型")
        raise ValueError(
            f"模型没有返回 JSON(stop_reason={stop},块={kinds}):{text[:200]!r}")
    return json.loads(text[start:end + 1])
