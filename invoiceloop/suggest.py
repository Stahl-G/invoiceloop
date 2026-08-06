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

ACTIONS = ("auto_accept", "absent_expected", "revoke")
#: cohort 只许引用通用特征 —— 与 improve._COHORT_KEYS 同源,不许放宽
_ALLOWED_COHORT_KEYS = ("field", "tier", "strength")

_PROMPT = """你在读一份发票复核系统的 cohort 统计与复核者手写笔记。

你的任务:提出**候选策略改动**,供人类复核后决定是否采纳。你没有决定权。

规则:
1. 每条建议必须引用它依据的笔记(给出 note 的序号)。没有出处的建议不要提。
2. cohort 只能用 field / tier / strength 描述,禁止出现 doc_id、具体金额、
   具体发票号等单文档特征。
3. action 只能是:auto_accept(该 cohort 可自动放行)、
   absent_expected(该字段的缺失是预期的)、revoke(应撤销某条已生效的放松)。
4. 证据弱就说弱。宁可少提一条,不要凑数。
5. 你看到的是「没产生修正的复核」,这不等于「这些复核没价值」——
   没被抽查不等于没有错。

按这个 JSON 结构回答,不要有别的文字:
{"suggestions": [{"action": "...", "cohort": {"field": "..."},
  "finding": "你从笔记里读到的事实", "prediction": "采纳后你预期会发生什么",
  "confidence": "high|medium|low", "cites": [0, 3]}]}
"""


def _packet(report: dict) -> tuple[str, list[dict]]:
    """mine_report → (给模型的文本, 笔记表)。笔记表是引用的锚,
    模型给的 cites 下标必须落在它里面,否则该条建议丢弃。"""
    notes: list[dict] = []
    lines = ["## cohort 统计\n"]
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
    """草稿 → (可用建议, 丢弃理由)。**纯函数,可单测,不碰网络。**"""
    kept, dropped = [], []
    for i, s in enumerate(raw.get("suggestions") or []):
        label = f"suggestion[{i}]"
        if s.get("action") not in ACTIONS:
            dropped.append(f"{label}:action {s.get('action')!r} 不在词表")
            continue
        cohort = s.get("cohort")
        if not isinstance(cohort, dict) or not cohort:
            dropped.append(f"{label}:没有 cohort")
            continue
        bad = [k for k in cohort if k not in _ALLOWED_COHORT_KEYS]
        if bad:
            dropped.append(f"{label}:cohort 出现非白名单键 {bad} —— "
                           f"单文档特征不许进策略")
            continue
        cites = [c for c in (s.get("cites") or [])
                 if isinstance(c, int) and 0 <= c < len(notes)]
        if not cites:
            dropped.append(f"{label}:引用为空或越界 —— 没出处的建议不收")
            continue
        kept.append({
            "action": s["action"], "cohort": cohort,
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
    packet, notes = _packet(report)
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
    raw = _ask(packet, key=key, base_url=base_url,
               model=model or os.environ.get("INVOICELOOP_SUGGEST_MODEL")
               or default_model)
    kept, dropped = validate(raw, notes)
    out = {
        "advisory": True,
        "model": model or default_model,
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


def _ask(packet: str, *, key: str, base_url: str, model: str) -> dict:
    """一次 messages 调用,取回 JSON。解析失败如实抛,不猜。"""
    import requests

    from .vision_ingest import API_VERSION

    response = requests.post(
        f"{base_url.rstrip('/')}/v1/messages",
        headers={"x-api-key": key, "anthropic-version": API_VERSION,
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": 2000,
              "messages": [{"role": "user",
                            "content": f"{_PROMPT}\n\n{packet}"}]},
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    text = "".join(b.get("text", "") for b in body.get("content", []))
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"模型没有返回 JSON:{text[:200]!r}")
    return json.loads(text[start:end + 1])
