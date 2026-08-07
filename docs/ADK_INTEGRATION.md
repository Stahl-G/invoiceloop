# InvoiceLoop × Google ADK

**ADK 给 agent 能力;InvoiceLoop 让 agent 的行为可追责。**

这份文档只描述**代码里真的在跑的东西**。任何在这里出现的能力,都能用
`tests/test_agents_adk_pipeline.py` 里的一条测试指出来。

> **2026-08-07 更正。** 本文上一版声称有 Extractor Agent、Vision Inspector
> Agent、以及一个「检查空间 OCR 邻域」的 Party Identification Agent,并说
> 改进循环「由 SequentialAgent 和 LoopAgent 编排」。这些都不成立:
> - `run_improve_loop` 里 `_pipeline = build_adk_pipeline(...)` 构造完就被丢掉,
>   Runner 从未被调用;
> - Vision Agent 收到的输入只有 doc_id / 字段名 / 已有值,**没有任何图像**;
> - Party Agent 收到的是 OCR 前 40 行**纯文本**,没有 bbox,没有几何。
>
> Vision 与 Party 已删除。抽取始终由 DWS 承担,从来没有 Extractor Agent。
> 本文余下部分描述的是执行路径。

---

## 1. ADK 在哪一段,以及为什么只在这一段

```text
   PDF ──► Nutrient DWS 抽取 ──► field_drafts.json(无 ID)
                                        │
        ═══════════════════════ 信任内核(确定性 Python,ADK 一个字节都不写)═══
        冻结事务(Python 分配 FC ID) → 六门禁 → 支持矩阵 → 路由 → 人工裁决账本
        ═══════════════════════════════════════════════════════════════════
                                        │
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │  ADK Runner.run_async()                  │
                    │  SequentialAgent "improve_pipeline"      │
                    │                                          │
                    │  LlmAgent  miner     → state.miner       │
                    │  LlmAgent  proposer  → state.proposals   │
                    │  BaseAgent evaluator → state.counterfactual  ← 确定性
                    │  LlmAgent  critic    → state.critic      │
                    └──────────────────┬───────────────────────┘
                                       │  improve/adk_loop_report.json(纯建议)
                                       ▼
                          人读 → 人签字 → Gate 2 → promote
```

**为什么 ADK 只出现在改进循环里。** 抽取那一段没有可编排的判断 —— DWS 抽,
Python 冻结。信任内核那一段被三套重放测试钉死(`test_binding_regression`
逐行复现 454 行冻结判定、`test_port_fidelity` 与原始实现对拍、heldout 零 diff),
让一个非确定性调度器进去只会破坏可复现性。改进循环是唯一有真分工的地方:
哪些复核模式值得成规则、规则怎么写才不过宽、这条规则会不会丢掉真值。

---

## 2. 四个阶段

| 阶段 | 类型 | state 键 | 结构化输出 | 判断内容 |
|---|---|---|---|---|
| `miner` | `LlmAgent` | `miner` | `MinerFindings` | 哪些复核模式稳定到值得成规则 |
| `proposer` | `LlmAgent` | `proposals` | `ProposalSet` | 规则怎么写才不过宽 |
| `evaluator` | `BaseAgent` | `counterfactual` | — | **确定性**:`improve.propose` + `improve.evaluate` |
| `critic` | `LlmAgent` | `critic` | `CriticReview` | 拿着反事实数字反驳提案 |

### Evaluator 为什么是自定义 `BaseAgent` 而不是工具

工具由模型决定调不调。宪章四说跑不了的检查不算通过,所以反事实评测**必须**
每次都跑。`SequentialAgent` 按顺序执行子节点 —— 没有任何模型输出能跳过它。

评测失败**不吞**:记 `blocking: true` + `blocking_reason`,交给 Critic 与报告。
(上一版是 `except Exception: pre_evals[field] = {}`,Critic 于是拿着空反事实
照样能点头。)

反事实按**整个 cohort 的规范化形式**键控,不是按 `field` —— 按 field 键控会让
同字段的多条候选互相覆盖,Critic 拿到别条候选的证据。

---

## 3. 权限边界

| 层 | 能做 | 不能做 |
|---|---|---|
| ADK / Gemini | 提出无 ID 候选、生成建议报告 | 写账本、分配 ID、改门禁、判 pass、promote |
| Python 控制面 | 分配 ID、冻结、确定性评测、记录失败 | 编造字段值、替人批准 |
| 人 | 接受/拒绝/修改候选、签字 promote | 改写已冻结的输入 |
| Gate 2 / 3 | 判候选是否具备晋升资格 | 按模型措辞放宽规则 |

**措辞即权限。** 模型的输出字段叫 `recommend_for_human_review`,不叫
`accepted` / `approved` / `safe`。报告顶层是 `recommended_for_human_review`,
不是 `approved_by_critic`。`test_report_says_recommend_never_approved` 会在
这些词回来的时候失败。

**写入边界。** 只写 `improve/adk_loop_report.json`。`improve/suggestions.json`
归 `suggest.py` —— 两个生产者不许写同一个文件
(`test_does_not_touch_suggestions_json`)。

---

## 4. 零 API 重放

`invoiceloop/agents/adk_replay.py` 挂在每个 `LlmAgent` 的
`before_model_callback` / `after_model_callback` 上。ADK 文档写明 before 回调
返回 `LlmResponse` 时模型调用被跳过 —— 所以重放模式下**一个请求都不发**,
而 Runner、SequentialAgent、状态传递、事件流全部照常执行。

录音的键是**整个请求的摘要**:

```
sha256(model ‖ system_instruction ‖ contents ‖ response schema ‖ mime)
```

不是调用点起的名字。上一版用 `critic_{field}` / `party_{doc_id}` 这类手写
call_id,model / prompt / schema 都不在身份里 —— 改了模型或提示词之后,旧录音
仍会被当成本次调用的结果返回。**这不是理论风险**:被删掉的
`test_agents_party.py` 与 `test_agents_vision.py` 的录音写着 `gemini-2.5-flash`,
而运行时默认早已是 `gemini-3.6-flash`,测试照过。

现在换模型、换提示词、换 schema 都会导致摘要不同 → `ReplayRecordingMissing`
→ 阻断。缺录音是阻断,不是「就当模型说了这个」(宪章四)。

| 测试 | 钉住什么 |
|---|---|
| `test_replay_serves_the_recording_and_never_calls_the_model` | 重放时模型零调用,报告逐字节相同 |
| `test_replay_refuses_a_recording_made_under_a_different_model` | 换模型 → 阻断 |
| `test_replay_refuses_a_recording_made_under_a_different_prompt` | 换提示词 → 阻断 |

---

## 5. 结构化输出

只有一条路径:`LlmAgent(output_schema=<Pydantic 模型>)`,由 ADK 交给
`google-genai`。非结构化的 `call_gemini_model` **已删除** —— 它会吞掉 JSON
解析错误,机器消费的结果不许走那条路。

模型:`gemini-3.6-flash`(`runtime.DEFAULT_GEMINI_MODEL`),可用
`GEMINI_MODEL` 覆盖。凭据缺失且未开重放 → `GeminiCredentialMissing`,不是静默降级。

---

## 6. 已知限制(照登)

1. **`SequentialAgent` 在 google-adk 2.6.2 里已标记 deprecated**,官方建议迁到
   `Workflow`。`Workflow` 是另一套 graph/edges API,不是 drop-in;当前仍用
   `SequentialAgent`,功能正常,测试会打 DeprecationWarning。
2. **尚无 live 调用取证。** 上面全部测试跑在脚本化模型或录音上。在拿到一次
   真实 `gemini-3.6-flash` 调用并落盘之前,不得声称「已接通 Gemini」。
3. **Critic 的判断质量未测量。** 现有测试证明的是**权限与管道**正确
   (它拿得到确定性反事实、它的输出只是建议),不是「它判得准」。
   宪章六:不说工件证明不了的话。

---

## 7. 复算

```bash
venv/bin/python -m pytest tests/test_agents_adk_pipeline.py -q
```

九条,零网络。
