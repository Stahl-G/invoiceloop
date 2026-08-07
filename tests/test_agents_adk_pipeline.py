"""ADK 是否**真的在跑** —— 不是构造一个图然后丢掉。

前一版 `run_improve_loop` 里有一行 `_pipeline = build_adk_pipeline(model_name)`,
之后再也没被引用,注释自称「to demonstrate architectural integration」。
文档却说由 SequentialAgent 编排。这组测试钉死「Runner 执行过」这件事:
事件真的从四个阶段发出来,状态真的在阶段之间传递。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ADK/GenAI 是可选依赖(`pip install -e ".[gemini]"`)。没装就跳过,
# 不要让整个 tests/ 收集不起来 —— 干净 clone 必须能跑通测试。
pytest.importorskip("google.adk", reason="需要 invoiceloop[gemini]")

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from invoiceloop.agents.improve_loop import run_improve_loop

STAGES = ["miner", "proposer", "evaluator", "critic"]
DOC = "acme-001"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """能真正跑通 `improve.propose` 的 workspace(与 test_improve.py 同构)。

    上面那些用例用的是裸 workspace,`propose` 在那里恒失败,于是
    「blocking」断言恒真。要检验提案本身对不对,必须有一个**本来会成功**
    的环境。
    """
    from invoiceloop import ocr
    from invoiceloop.pipeline import run as pipeline_run
    from tests.conftest import pin_corpus

    d = tmp_path / "ws"
    (d / "input" / "pdfs").mkdir(parents=True)
    (d / "input" / "pdfs" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "ocr").mkdir()
    (d / "ocr" / f"{DOC}.json").write_text(json.dumps({"pages": [{
        "page_idx": 0, "dimensions": [612, 792],
        "blocks": [{"lines": [{"words": [
            {"value": v, "confidence": 0.99, "geometry": [[x, 0.1], [x + 0.08, 0.13]]}
            for v, x in (("INV-42", 0.10), ("Total", 0.20), ("100.00", 0.30))]}]}],
    }]}))
    (d / "raw").mkdir()
    data = {"invoice_number": "INV-42", "total_gross": "100.00"}
    for mode in ("understand", "agentic"):
        (d / "raw" / f"{DOC}.{mode}.json").write_text(json.dumps(
            {"doc_id": DOC, "document": f"{DOC}.pdf", "mode": mode,
             "http_status": 200,
             "body": {"output": {"data": data, "metadata": {},
                                 "pages": [{"page": 1, "width": 612,
                                            "height": 792}]}}}))
    pin_corpus(monkeypatch, d)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    pipeline_run([DOC], d / "runs" / "run-0001", include_vision=False,
                 out_of_calibration=True)
    yield d


class ScriptedLlm(BaseLlm):
    """按顺序吐预设 JSON 的 BaseLlm。

    这不是「mock 掉被测代码」—— Runner、SequentialAgent、状态传递、事件
    全是真的 ADK,只有网络出口被换成脚本。生产路径上这个位置是录放回放
    (`adk_replay.before_model`),同样不发请求。
    """

    script: list[str] = []
    #: 每次调用的 system_instruction —— 状态传递就发生在这里。
    #: **不要**断言在 contents 上:ADK 默认把前序对话history 带进 contents,
    #: 于是「上一阶段的输出出现在下一阶段的请求里」即便状态传递被拆掉也成立。
    #: 这两条测试第一版就是这么假过的(变异测试抓到)。
    instructions: list[str] = []
    bodies: list[str] = []

    async def generate_content_async(self, llm_request, stream=False):
        self.instructions.append(
            str(getattr(llm_request.config, "system_instruction", "") or "")
        )
        self.bodies.append("\n".join(
            p.text or "" for c in llm_request.contents for p in (c.parts or [])
        ))
        text = self.script[min(len(self.instructions) - 1, len(self.script) - 1)]
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=text)])
        )


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "improve").mkdir(parents=True, exist_ok=True)
    (tmp_path / "improve" / "mine_report.json").write_text(
        json.dumps({
            "cohorts": [],
            "buckets": {"zero_corrections": 5},
            "low_yield_candidates": [
                {"field": "total_vat", "tier": "TIER1",
                 "support_strength": "unsupported", "reviewed": 9},
            ],
        }),
        encoding="utf-8",
    )
    return tmp_path


def _script() -> list[str]:
    return [
        json.dumps({"candidates": [
            {"field": "total_vat", "tier": "TIER1", "reviewed": 9,
             "why": "9 reviews, zero corrections"},
        ]}),
        json.dumps({"proposals": [
            {"action": "auto_accept",
             "cohort": {"field": "total_vat", "tier": "TIER1"},
             "finding": "always corroborated",
             "prediction": "saves review slots"},
        ]}),
        json.dumps({"verdicts": [
            {"cohort_field": "total_vat", "recommend_for_human_review": True,
             "risk": "LOW", "reason": "counterfactual shows no silent errors",
             "values_at_risk": []},
        ]}),
    ]


def _run(ws: Path, script=None) -> tuple[dict, ScriptedLlm]:
    llm = ScriptedLlm(model="scripted", script=script or _script())
    return run_improve_loop(ws, model=llm), llm


def test_runner_emits_an_event_from_every_pipeline_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    report, _ = _run(_workspace(tmp_path))

    assert report["adk"]["executed"] is True
    assert report["adk"]["event_authors"] == STAGES


def test_session_state_carries_miner_output_into_the_proposer_prompt(
    tmp_path, monkeypatch
):
    """状态传递是真的:proposer 看得到 miner 写进 state 的那句话。"""
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    _, llm = _run(_workspace(tmp_path))

    assert "9 reviews, zero corrections" not in llm.instructions[0]
    assert "9 reviews, zero corrections" in llm.instructions[1]


def _unmined_script() -> list[str]:
    """一条挖掘报告里没有的 cohort —— 必定被 `resolve_cohort` 拒。

    这两条用例原先靠的是「裸 workspace 上 propose 必然失败」。那句话在
    2026-08-07 之前**碰巧**是真的,而且真因是提案缺 id 这个缺陷本身:
    修好之后裸 workspace 反而跑通了,两条用例一起变红。
    也就是说它们当时钉住的不是宪章四,是那个 bug。
    现在故意造一个**说得清理由**的失败。
    """
    script = _script()
    script[1] = json.dumps({"proposals": [
        {"action": "auto_accept",
         "cohort": {"field": "amount_due", "tier": "TIER1"},
         "finding": "模型凭空造的",
         "prediction": "挖掘报告里没有这条"},
    ]})
    return script


def test_critic_prompt_carries_the_deterministic_counterfactual(tmp_path, monkeypatch):
    """Critic 的指令里带着确定性评测结果,不是让它自己想象。"""
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    _, llm = _run(_workspace(tmp_path), _unmined_script())

    critic_instruction = llm.instructions[2]
    assert "blocking_reason" in critic_instruction
    assert "amount_due" in critic_instruction


def test_failed_evaluation_becomes_blocking_not_an_empty_dict(tmp_path, monkeypatch):
    """宪章四:评测跑不了 = 阻断。不许压成 {} 让 Critic 照样点头。"""
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    report, _ = _run(_workspace(tmp_path), _unmined_script())

    entry = report["counterfactual"][0]
    assert entry["blocking"] is True
    assert "挖掘报告" in entry["blocking_reason"]
    assert entry["evaluation"] is None
    assert report["blocking_evaluations"] == 1


def test_two_cohorts_on_one_field_get_separate_counterfactuals(tmp_path, monkeypatch):
    """反事实按整个 cohort 键控 —— 按 field 键控会让同字段候选互相覆盖。"""
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    script = _script()
    script[1] = json.dumps({"proposals": [
        {"action": "auto_accept", "cohort": {"field": "total_vat", "tier": "TIER1"},
         "finding": "a", "prediction": "a"},
        {"action": "auto_accept", "cohort": {"field": "total_vat", "tier": "TIER2"},
         "finding": "b", "prediction": "b"},
    ]})
    report, _ = _run(_workspace(tmp_path), script)

    keys = [r["key"] for r in report["counterfactual"]]
    assert len(report["counterfactual"]) == 2
    assert len(set(keys)) == 2


#: 真 workspace 上的一组:上面那些用的是**裸** workspace(只有
#: improve/mine_report.json),`improve.propose` 在那里必然因为「没有 active
#: harness」而失败 —— 于是 `blocking is True` 恒真,把提案本身的毛病全遮住了。
#: 2026-08-07 在 195 条真复核事件上跑 ADK 才暴露出来:两条提案都因为
#: 「cohort 缺 id」阻断,而模型**本来就不许**发 id(宪章一)。
class TestProposalToCohortOnARealWorkspace:
    def _mine_report(self, ws, *, absence=(), low_yield=()):
        (ws / "improve").mkdir(parents=True, exist_ok=True)
        (ws / "improve" / "mine_report.json").write_text(json.dumps({
            "cohorts": [{"field": f, "tier": t, "reviewed": 9}
                        for f, t in low_yield],
            "buckets": {"zero_corrections": 9},
            "low_yield_candidates": [{"field": f, "tier": t, "reviewed": 9}
                                     for f, t in low_yield],
            "absence_candidates": [{"field": f, "total": 9, "absentish": 9}
                                   for f in absence],
        }), encoding="utf-8")
        return ws

    def _script(self, cohort):
        return [
            json.dumps({"candidates": [
                dict(cohort, reviewed=9, why="9 reviews, zero corrections")]}),
            json.dumps({"proposals": [
                {"action": "CREATE_COHORT", "cohort": cohort,
                 "finding": "zero corrections across 9 reviews",
                 "prediction": "can be skipped"},
            ]}),
            json.dumps({"verdicts": []}),
        ]

    def test_python_assigns_the_cohort_id_the_model_may_not_send(
            self, ws, monkeypatch):
        """宪章一:模型不发 ID,Python 分配。

        模型发的 cohort 是 `{field, tier}`,没有 id —— 这是**对的**。
        缺的是 Python 这一侧:EvaluatorNode 直接把它塞给 improve.propose,
        而 lint 要求 cohort 带 id,于是每条提案都以「cohort 缺 id」阻断。
        实测(runs/hitl-sealed,195 事件):2 提案 / 2 阻断,全是这个原因。
        """
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        self._mine_report(ws, low_yield=[("total_vat", "TIER1")])
        report, _ = _run(ws, self._script({"field": "total_vat",
                                           "tier": "TIER1"}))

        entry = report["counterfactual"][0]
        assert entry["blocking"] is False, entry.get("blocking_reason")
        assert entry["evaluation"] is not None
        assert entry["cohort"]["id"], "Python 必须补上 cohort id"

    def test_absence_pattern_becomes_absent_expected_with_its_qa_probe(
            self, ws, monkeypatch):
        """缺席模式必须走 `absent_expected`,不能当成 auto_accept 放行。

        两者安全性不同:`absent_expected` 强制挂 QA 探针(缺席是否仍成立要
        持续观测),`auto_accept` 不挂。让模型选 kind 等于把这个安全选择交给
        模型 —— 所以 kind 由 Python 从确定性挖掘报告推定:字段出现在
        `absence_candidates` 里就是缺席规则。
        """
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        self._mine_report(ws, absence=["total_vat"])
        report, _ = _run(ws, self._script({"field": "total_vat",
                                           "tier": "TIER1"}))

        entry = report["counterfactual"][0]
        assert entry["blocking"] is False, entry.get("blocking_reason")
        assert entry["kind"] == "absent_expected"
        # 缺席 cohort 是字段级规则,带 tier 会被 lint 拒 —— Python 负责剥掉
        assert "tier" not in entry["cohort"]
        cand = json.loads((ws / "harnesses" / entry["candidate"]
                           / "routing_policy.json").read_text(encoding="utf-8"))
        assert cand["qa"]["absent_expected_rate"] > 0

    def test_running_the_loop_twice_reuses_the_candidate(self, ws, monkeypatch):
        """重复跑不许堆重复候选,报告也不许因此漂移。

        没有这条的话:第二遍造 HAR-0003,候选名与政策摘要都变,报告不可复现,
        而且这些字段一旦进了 Critic 提示词,录放会直接失配。
        """
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        self._mine_report(ws, low_yield=[("total_vat", "TIER1")])
        script = self._script({"field": "total_vat", "tier": "TIER1"})

        first, _ = _run(ws, script)
        second, _ = _run(ws, script)

        assert first["counterfactual"][0]["candidate"] \
            == second["counterfactual"][0]["candidate"]
        machine = [p for p in (ws / "harnesses").glob("HAR-*")
                   if json.loads((p / "manifest.json").read_text(
                       encoding="utf-8")).get("provenance") == "machine_proposed"]
        assert len(machine) == 1, [p.name for p in machine]

    def test_the_critic_never_sees_bookkeeping_that_drifts(self, ws, monkeypatch):
        """候选目录名与政策摘要不进 Critic 提示词。

        它们是账本的溯源字段,不是「这条规则安不安全」的判断依据,而且每造
        一个新候选就变一次 —— 进了提示词就等于请求摘要会漂,录放绑不住。
        """
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        self._mine_report(ws, low_yield=[("total_vat", "TIER1")])
        report, llm = _run(ws, self._script({"field": "total_vat",
                                             "tier": "TIER1"}))

        critic_prompt = llm.instructions[2]
        entry = report["counterfactual"][0]
        assert entry["candidate"] not in critic_prompt
        assert entry["evaluation"]["candidate_policy_digest"] not in critic_prompt
        # 判断依据仍然在
        assert "review_load_candidate" in critic_prompt
        assert "total_vat" in critic_prompt

    def test_critic_gets_deltas_and_the_gate_verdict_not_raw_numbers(self):
        """Critic 拿到的是**差值 + 门禁判定**,不是让它自己做减法。

        2026-08-07,第一次在真复核历史(195 事件)上跑 ADK 循环:Critic 对两条
        提案都投反对,理由写的是「留下 5 个静默错值暴露在外」。数字是真的 ——
        `silent_wrong_baseline: 5`。因果是错的:候选也是 5,**这条规则一个都
        没多留**,那 5 个基线上本来就有。它把基线数当成了改动的代价。

        减法交给 Python:`gate_verdict` 是预注册的确定性判定,Critic 的活是
        争论门禁看不见的东西(规则是不是太宽、哪些值有风险),不是重算门禁。
        """
        from invoiceloop.agents.improve_loop import _critic_view

        view = _critic_view({"results": [{
            "cohort": {"id": "AE-total_vat", "field": "total_vat"},
            "kind": "absent_expected", "key": "k", "blocking": False,
            "candidate": "HAR-0006",
            "evaluation": {
                "safety_status": "scored", "basis": "evo_truth_replay",
                "silent_absent_baseline": 0, "silent_absent_candidate": 0,
                "silent_wrong_baseline": 5, "silent_wrong_candidate": 5,
                "review_load_baseline": 0.5666666666666667,
                "review_load_candidate": 0.55,
                "candidate_policy_digest": "deadbeef",
            },
        }]})
        entry = view["results"][0]
        assert entry["evaluation"]["silent_wrong_delta"] == 0
        assert entry["evaluation"]["silent_absent_delta"] == 0
        assert entry["gate"]["ok"] is True, "静默错不升 + 负载不升 = Gate 2 通过"
        # 记账字段仍然不给它看
        assert "candidate_policy_digest" not in entry["evaluation"]

    def test_critic_sees_the_resolved_cohort_not_the_models_draft(
            self, ws, monkeypatch):
        """提案在提示词里只出现**一次**,而且是 Python 解析后的那一份。

        实测(2026-08-07 真数据):模型提的是 `{field, tier}`,Python 解析成
        字段级 `absent_expected`(缺席与 TIER 无关,tier 被剥掉)。Critic 同时
        看到原稿和解析结果,于是把规则描述成「across all TIER1 documents」——
        实际范围是**所有**文档,比它写的更宽。给人看的建议里,规则的范围写
        错了方向,而且是往轻里写。
        """
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        self._mine_report(ws, absence=["total_vat"])
        _, llm = _run(ws, self._script({"field": "total_vat",
                                        "tier": "TIER1"}))

        critic_prompt = llm.instructions[2]
        assert "TIER1" not in critic_prompt, \
            "解析后的缺席 cohort 没有 tier,提示词里不该还留着模型的原稿"
        assert "zero corrections across 9 reviews" in critic_prompt, \
            "模型自己写的 finding 仍要给它看 —— 那是它要争论的主张"

    def test_a_gate_failing_candidate_is_shown_as_failing(self):
        """门禁判定必须真的判 —— 静默错上升时给 Critic 的是 ok=False。"""
        from invoiceloop.agents.improve_loop import _critic_view

        view = _critic_view({"results": [{
            "cohort": {"id": "AE-x", "field": "due_date"}, "blocking": False,
            "evaluation": {
                "safety_status": "scored", "basis": "evo_truth_replay",
                "silent_absent_baseline": 0, "silent_absent_candidate": 3,
                "silent_wrong_baseline": 5, "silent_wrong_candidate": 5,
                "review_load_baseline": 0.6, "review_load_candidate": 0.5,
            },
        }]})
        entry = view["results"][0]
        assert entry["evaluation"]["silent_absent_delta"] == 3
        assert entry["gate"]["ok"] is False
        assert any("silent_absent" in r for r in entry["gate"]["refusals"])

    def test_a_cohort_the_miner_never_found_is_refused(self, ws, monkeypatch):
        """模型只能在**挖掘报告里已有的** cohort 中选,不能凭空造一条。

        否则「确定性挖掘 → 模型判断」这条链断了:模型可以提出一条没有任何
        复核事件支撑的规则,而系统会照样给它跑反事实、照样呈给人签字。
        """
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        self._mine_report(ws, low_yield=[("total_vat", "TIER1")])
        report, _ = _run(ws, self._script({"field": "amount_due",
                                           "tier": "TIER1"}))

        entry = report["counterfactual"][0]
        assert entry["blocking"] is True
        assert "挖掘报告" in entry["blocking_reason"]

    def test_a_cohort_already_in_the_active_policy_is_refused(
            self, ws, monkeypatch):
        """已经在生效政策里的 cohort 再提一次不是改进,是空转。

        lint 对「id 已存在」是 `continue`(既有条目不动),所以它不会报错 ——
        候选会被造出来、跑完反事实、显示为一条可晋升提案,而它什么也没改。
        """
        monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
        self._mine_report(ws, low_yield=[("total_vat", "TIER1")])
        script = self._script({"field": "total_vat", "tier": "TIER1"})
        first, _ = _run(ws, script)
        cohort_id = first["counterfactual"][0]["cohort"]["id"]

        from invoiceloop import improve as _imp
        _imp.promote(ws, first["counterfactual"][0]["candidate"],
                     approved_by="y", rationale="进政策",
                     approved_at="2026-08-07T00:00:00Z")

        second, _ = _run(ws, script)
        entry = second["counterfactual"][0]
        assert entry["blocking"] is True, \
            f"{cohort_id} 已在生效政策里,不该再造一个空转候选"
        assert "已在生效政策" in entry["blocking_reason"]


def test_report_says_recommend_never_approved(tmp_path, monkeypatch):
    """模型没有放行权,报告的措辞不许暗示它有。"""
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    report, _ = _run(_workspace(tmp_path))

    blob = json.dumps(report, ensure_ascii=False)
    for banned in ("approved_by_critic", '"accepted"', "safe_to_release"):
        assert banned not in blob, f"报告里出现了越权措辞:{banned}"
    assert report["advisory"] is True
    assert "recommended_for_human_review" in report


# ── 零 API 重放:ADK 模型出口的录放 ────────────────────────────────

def test_replay_serves_the_recording_and_never_calls_the_model(tmp_path, monkeypatch):
    """录一次,重放时模型一次都不被调用,报告逐字节相同。"""
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    ws = _workspace(tmp_path)

    recorded, live = _run(ws)                      # 录制
    assert len(live.instructions) == 3

    monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
    replayed, silent = _run(ws)                    # 重放

    assert silent.instructions == [], "重放模式下模型仍被调用了"
    assert json.dumps(replayed, sort_keys=True) == json.dumps(recorded, sort_keys=True)


def test_replay_refuses_a_recording_made_under_a_different_model(tmp_path, monkeypatch):
    """录音必须绑定 model —— 换了模型还接受旧录音就是伪造。"""
    from invoiceloop.agents.runtime import ReplayRecordingMissing

    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    ws = _workspace(tmp_path)
    _run(ws)

    monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
    other = ScriptedLlm(model="a-different-model", script=_script())
    with pytest.raises(ReplayRecordingMissing):
        run_improve_loop(ws, model=other)


def test_replay_refuses_a_recording_made_under_a_different_prompt(tmp_path, monkeypatch):
    """改了 mine_report(→ 改了指令)就必须重新取证,不许复用旧录音。"""
    from invoiceloop.agents.runtime import ReplayRecordingMissing

    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    ws = _workspace(tmp_path)
    _run(ws)

    (ws / "improve" / "mine_report.json").write_text(
        json.dumps({"cohorts": [], "buckets": {"zero_corrections": 99},
                    "low_yield_candidates": []}), encoding="utf-8")

    monkeypatch.setenv("INVOICELOOP_REPLAY", "1")
    with pytest.raises(ReplayRecordingMissing):
        _run(ws)


def test_string_model_without_a_credential_raises_our_error(tmp_path, monkeypatch):
    """ADK 自己建 client,读的是进程环境,不认 invoiceloop 的 .env。

    桥接没做的时候,用户看到的是 ADK 的通用 "No API key was provided",
    而不是我们那条说清「或者设 INVOICELOOP_REPLAY=1」的错误。
    """
    from invoiceloop.agents.runtime import GeminiCredentialMissing

    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    monkeypatch.delenv("INVOICELOOP_REPLAY", raising=False)
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(GeminiCredentialMissing):
        run_improve_loop(_workspace(tmp_path), model="gemini-3.6-flash")
