"""Gemini GenAI SDK & ADK Agent Layer for InvoiceLoop.

改进循环由 ADK `Runner` 真正执行(见 `improve_loop`),模型出口挂录放
回调做零 API 重放(见 `adk_replay`)。模型只产建议:不分配 ID、不写账本、
不决定门禁跑不跑、不晋升。

只有结构化调用一条路径 —— `call_gemini_structured`。非结构化的
`call_gemini_model` 已删除:它会吞掉 JSON 解析错误,机器消费的结果
不许走那条路。
"""

from __future__ import annotations

from .runtime import (
    AgentCallRecorder,
    GeminiCredentialMissing,
    GeminiSDKMissing,
    ReplayHarness,
    ReplayRecordingMissing,
    call_gemini_structured,
    is_replay_mode,
)

__all__ = [
    "AgentCallRecorder",
    "GeminiCredentialMissing",
    "GeminiSDKMissing",
    "ReplayHarness",
    "ReplayRecordingMissing",
    "call_gemini_structured",
    "is_replay_mode",
]
