# Gemini 3.6-flash 实时调用取证(2026-08-07)

在此之前,ADK 层的全部测试都跑在脚本化模型或人造录音上,所以不能说
「接通了 Gemini」。这份目录是第一次真实调用的落盘证据。

## 跑的是什么

```bash
python3 -m invoiceloop agents improve-loop --workspace runs/adk-live
```

`Runner.run_async()` 驱动 `SequentialAgent(improve_pipeline)`,四阶段全部执行,
其中三个 `LlmAgent` 各发一次真实请求。

| 项 | 值 |
|---|---|
| 模型 | `gemini-3.6-flash` |
| 端点 | Gemini Developer API(`google-genai` 2.17.0) |
| 框架 | `google-adk` 2.6.2 |
| 真实请求数 | 3(miner / proposer / critic) |
| 墙钟 | 15.3s |
| 语料 | `invoiceloop demo` 内嵌 2 份 PDF,3 条人工裁决 |

## 文件

| 文件 | 内容 |
|---|---|
| `adk_84e0b5061ee029cc.json` | miner 的请求身份 + 响应 |
| `adk_3d87b1a694adf736.json` | proposer 的请求身份 + 响应 |
| `adk_c43819abc8f3b53a.json` | critic 的请求身份 + 响应 |
| `mine_report.json` | 三次调用的输入 |
| `adk_loop_report.json` | 产出(纯建议) |

每份录音的 `identity` 字段带全部身份分量:
`model` / `system_instruction` / `contents` / `response_schema` / `response_mime_type`。
文件名就是这些分量的 sha256 前 16 位。

## 结果说了什么

三个模型都返回空列表:`{"candidates":[]}` → `{"proposals":[]}` → `{"verdicts":[]}`。

**这是对的,不是失败。** demo 语料只有 2 份文档、3 条裁决,形不成任何
「高频复核零修正」模式(`improve mine` 同样给出 `cohorts: 0`)。模型没有
为了显得有用而编一条规则出来。要看非空的循环,需要一个有真实复核历史的
workspace。

## 复算(零 API,不需要密钥)

把本目录的三份录音放进某个 workspace 的 `agent_calls/`,然后:

```bash
env -u GEMINI_API_KEY -u GOOGLE_API_KEY \
  INVOICELOOP_REPLAY=1 python3 -m invoiceloop agents improve-loop --workspace <ws>
```

实测:**在完全没有凭据的环境下**跑通,产出与实时报告
`diff` 零差异。

## 身份绑定的反证(在真实录音上做的)

| 改动 | 结果 |
|---|---|
| `--model gemini-3.5-flash` | `ReplayRecordingMissing: adk_506fd273d67f2ede` ✅ 拒绝 |
| `mine_report.events` 改成 999(→ 改了提示词) | `ReplayRecordingMissing: adk_d947a753ce1c78e4` ✅ 拒绝 |

上一版的手写 call_id(`critic_{field}`)在这两种情况下都会**照常返回旧录音**。

## 还不能说的话

- 不能说「Critic 判得准」。这三次调用没有任何提案可判。权限与管道被测试
  钉死了,判断质量**没有测量**(宪章六)。
- 不能说「循环在真实语料上有效」。这是一次 demo 语料上的连通性取证。
