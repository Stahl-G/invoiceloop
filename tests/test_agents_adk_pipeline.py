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

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from invoiceloop.agents.improve_loop import run_improve_loop

STAGES = ["miner", "proposer", "evaluator", "critic"]


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


def test_critic_prompt_carries_the_deterministic_counterfactual(tmp_path, monkeypatch):
    """Critic 的指令里带着确定性评测结果,不是让它自己想象。"""
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    _, llm = _run(_workspace(tmp_path))

    critic_instruction = llm.instructions[2]
    assert "blocking_reason" in critic_instruction
    assert "total_vat" in critic_instruction


def test_failed_evaluation_becomes_blocking_not_an_empty_dict(tmp_path, monkeypatch):
    """宪章四:评测跑不了 = 阻断。不许压成 {} 让 Critic 照样点头。"""
    monkeypatch.setenv("INVOICELOOP_NO_DOTENV", "1")
    report, _ = _run(_workspace(tmp_path))

    # 裸 workspace 上 improve.propose 必然失败
    entry = report["counterfactual"][0]
    assert entry["blocking"] is True
    assert entry["blocking_reason"]
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
