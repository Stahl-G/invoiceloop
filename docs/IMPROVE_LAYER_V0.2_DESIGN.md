# InvoiceLoop Improve Layer v0.2 版本设计

**副标题：Evidence-Bound, Eval-Gated, Human-Promoted Harness Improvement**  
**状态：建议冻结为实施基线**  
**评估仓库：`b5fe7a0368ab7ef473edf8faebf061daa1ea847c`**  
**日期：2026-08-05**

---

## 0. 裁决摘要

### 0.1 选择的方案

选择 **Guarded Improvement Control Plane（受控改进控制面）**：

```text
真实使用与人工复核
→ 结构化反馈事件
→ 重复失败/无效复核模式
→ 有边界的 Harness Candidate
→ Targeted Eval + Regression Eval + Promotion Eval
→ 人类批准晋升
→ 新 Harness 版本影响未来 run
```

它既不是：

- “人工改完当前发票就算闭环”；
- “按历史修正率重新排个序”；
- “agent 自动修改整个 repo 并直接上线”；
- “用同一批 DocILE 反复调到好看”。

### 0.2 产品主张

> **InvoiceLoop starts conservative, then turns every reviewed invoice into evidence for safely reviewing fewer fields next time.**

中文：

> **InvoiceLoop 从保守策略开始，把每一次人工复核变成下一版 Harness 的评测证据，在不增加关键静默错误的前提下逐步减少人工复核。**

### 0.3 核心实验

以修正后的真实 R0 基线为起点，目标把：

```text
TIER1 mandatory field review load
约 41% → ≤30%
```

同时满足：

```text
关键字段广义静默风险不劣于 R0
关键错误路由召回不显著下降
实际 reviewer minutes per invoice 下降
审计与绑定不变量全部通过
```

**30% 是产品目标，不是自然科学常数。** 真正的研究结论是风险—覆盖前沿向左下移动，而不是恰好跨过 30%。

### 0.4 对外命名

实施前和只有开发集结果时：

> feedback-driven, eval-gated harness improvement

完成至少一次“反馈→候选→未见数据资格评测→人类晋升→未来 run 使用新版本”后：

> human-steered self-improving harness

没有 fresh sealed evaluation 前，禁止宣称 autonomous self-improvement。

---

# 1. 当前设计为什么必须重切

现有 `docs/IMPROVE_LOOP_DESIGN.md` 有正确纪律，但第一刀不能支撑目标。

## 1.1 正确的部分

现有设计已经坚持：

- 提案不是权威；
- 不自动改门禁，不自动上线；
- 人工裁决是重要反馈来源；
- 需要风险—覆盖评测；
- 不能反复使用同一留出集；
- 不能把读图模型作答当真值。

这些全部保留。

## 1.2 必须推翻的部分

### A. “Tax AI 依赖完备自动神谕”并不准确

Tax AI 的关键不是完备的税务 reference implementation，而是：

```text
专家修正
→ 完整产品 trace
→ 区分真实失败与工作流噪声
→ 重复模式变成 targeted eval
→ 有边界的工程任务
→ targeted + regression 验证
→ 人类负责架构与发布
```

InvoiceLoop 已经拥有 Tax AI 所需的大部分 trace 地基，缺的是从裁决到 finding、eval 和候选版本的后半环。

### B. “DWS 是黑盒，所以没有可学旋钮”不成立

即使不能修改 DWS 权重，InvoiceLoop 仍可改进：

- extraction schema；
- routing policy；
- warning / blocker 分类；
- required / absent / not-applicable 语义；
- understand→agentic 升级策略；
- review priority；
- field playbook；
- normalization 和 mapping；
- 文档类型的 policy profile。

这些都是 Harness，而不是模型权重。

### C. “同档内重排”无法把 41% 降到 30%

如果 `requires_adjudication` 集合不变，重排只改变人看的先后：

```text
review load 不变
automation coverage 不变
silent failure 不变
```

它只适合优化：

```text
critical error recall@固定人工预算
precision@k
time-to-first-critical-error
reviewer minutes to find 80% critical errors
```

所以第一刀必须允许一个**受限的 routing policy candidate**改变哪些软风险进入人工，同时冻结硬性 blocker。

### D. 只统计人工裁决存在严重选择偏差

当前策略决定了哪些字段能被人看到。若只看已复核字段：

- 被自动接受的区域没有标签；
- “从未被纠正”可能只是“从未被抽查”；
- 系统会错误地学习当前策略的盲点。

因此必须加入随机/分层 QA 抽查，并记录每个字段被复核的概率。

### E. Harness 身份尚未进入执行身份

当前 `snapshot.build_input_manifest()` 的指纹主要绑定 PDF、OCR、DWS 响应、schema 和 vision 输入，但未来 routing / escalation policy 改变时，同一输入必须形成不同 execution identity。

否则新 Harness 可能重放旧 run，无法证明哪一版策略处理了哪张发票。

---

# 2. 四条不可妥协的设计公理

## 公理一：Feedback is evidence, not permission

一条人工修正是证据，不是自动修改生产策略的授权。

## 公理二：Proposal is not policy

agent 只能生成 candidate；active harness 只能由显式 promotion record 指定。

## 公理三：Evaluator stays outside the loop

候选不能修改或读取：

- 私有 ground truth；
- sealed eval 集；
- eval scorer；
- 关键字段定义；
- safety gate；
- promotion rules。

## 公理四：Review reduction is not improvement unless risk is preserved

任何通过以下手段降低人工率的候选都算失败：

- 把错误改叫 `not_applicable`；
- 删除字段；
- 放宽 evaluator normalization；
- 把 warning 隐藏；
- 对所有文档多跑昂贵模型且不报成本；
- 只在开发集好看；
- 牺牲 TIER1 静默错误来换覆盖率。

---

# 3. 软件总架构

```text
┌──────────────────────────────────────────────────────────────┐
│                      EVALUATION AUTHORITY                    │
│ private labels · frozen scorers · sealed sets · promotion   │
│ rules · integrity tests                                     │
│              （只读候选，不可被候选修改）                    │
└──────────────────────────┬───────────────────────────────────┘
                           │ qualification result
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                IMPROVEMENT CONTROL PLANE                     │
│ feedback compiler → weakness miner → finding → proposer      │
│ → candidate sandbox → eval orchestrator → promotion manager │
└───────────────┬───────────────────────────────┬──────────────┘
                │ read-only traces              │ candidate diff
                ▼                               ▼
┌─────────────────────────────┐      ┌──────────────────────────┐
│       FEEDBACK PLANE        │      │ VERSIONED HARNESS PLANE  │
│ review events · QA events   │      │ routing · escalation     │
│ reason codes · actionability│      │ schema · field playbooks │
│ reviewer confidence         │      │ immutable versions/digest│
└───────────────┬─────────────┘      └─────────────┬────────────┘
                │ derived from                     │ selected by
                ▼                                  ▼
┌──────────────────────────────────────────────────────────────┐
│                       RUNTIME PLANE                          │
│ DWS → freeze → gates → routing → review → deliverable       │
│ every run binds exact harness_id + execution_fingerprint    │
└──────────────────────────┬───────────────────────────────────┘
                           │ immutable evidence
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                         TRUST KERNEL                         │
│ raw responses · artifact registry · evidence spans · field  │
│ ledger · review snapshot · adjudication ledger · bundle     │
│ verifier                                                    │
│                   （Improve 永远只读）                        │
└──────────────────────────────────────────────────────────────┘
```

## 3.1 Trust Kernel

保留并强化现有：

- `input_manifest.json`
- `artifact_registry.json`
- `evidence_span_registry.json`
- `field_ledger.json`
- `gate_report.json`
- `review_snapshot.json`
- `adjudication_ledger.jsonl`
- bundle manifest / verifier

Improve Layer 对以上内容只有读取权。

## 3.2 Runtime Plane

Runtime 使用一个已晋升 Harness 版本，生成：

- 抽取结果；
- 冻结声明；
- 确定性门禁；
- `routing_report.json`；
- support matrix；
- 人工队列；
- deliverable。

## 3.3 Versioned Harness Plane

第一版 Harness 由纯配置文件组成：

```text
harnesses/
  HAR-0001/
    manifest.json
    extraction_schema.json
    routing_policy.yaml
    escalation_policy.yaml
    review_priority.yaml
    field_playbooks/
      amount_due.yaml
      total_gross.yaml
      seller_tax_id.yaml
```

每个 Harness 不可变。新版本必须新建目录，不能覆盖旧版本。

## 3.4 Feedback Plane

人工裁决账本仍是权威。Feedback Plane 是从权威工件派生的、可重建的数据产品，不反向修改裁决。

## 3.5 Improvement Control Plane

负责：

```text
compile → mine → propose → lint → evaluate → qualify → promote
```

它不负责：

- 改写生产证据；
- 直接判定发票真值；
- 自动上线；
- 修改 evaluator。

## 3.6 Evaluation Authority

这是 Improve Layer 的外部宪法，包括：

- 私有标签；
- 数据集划分；
- scorer；
- promotion gates；
- integrity / regression suites；
- query budget；
- final sealed evaluation。

---

# 4. 当前 repo 的实施前置条件（P0）

Improve Layer 建立在反馈正确、版本可归因和交付值可信的前提上。以下必须先完成，且不算 41%→30% 的“学习成果”。

## P0-1 最终值只能来自冻结权威

当前 `deliver.py` 的 `accept` 路径直接取 `support_matrix.json` 的 `row["value"]`。矩阵按架构是投影，不应成为最终值权威。

修正：

```text
accept_claim → 必须有 claim_id
最终值 → 从 field_ledger 对应 claim 读取
correct → 从人工 corrected_value 读取
```

bundle verify 必须验证：

```text
accepted final value == frozen claim value
corrected final value == adjudication corrected_value
```

## P0-2 拆开人工决策语义

将当前：

```text
accept / reject / correct / abstain
```

升级为：

```text
accept_claim       确认一个已有 claim，必须有 claim_id
correct            人工给出新值
reject_claim       拒绝已有 claim
confirm_absent     确认页面确实没有该字段
not_applicable     该字段对这类文档不适用
abstain            人也无法判定，保持未决
```

否则 Improve Layer 无法区分：

- 抽取漏值；
- 合法缺失；
- 字段不适用；
- 人无法看清。

## P0-3 增加独立 routing authority

从 `matrix.py` 中抽出：

```text
invoiceloop/routing.py
```

生成：

```json
{
  "doc_id": "...",
  "field": "amount_due",
  "claim_id": "FC-0012",
  "route": "auto_accept | review | block | escalate",
  "reason_codes": ["..."],
  "harness_id": "HAR-0001",
  "policy_digest": "...",
  "review_probability": 1.0
}
```

`support_matrix.json` 继续是展示投影；`deliverable.json` 使用冻结 ledger、routing report 和人工裁决重建。

## P0-4 Harness 必须进入 execution fingerprint

新增：

```text
execution_fingerprint = hash(
  input_fingerprint,
  code_revision,
  harness_id,
  extraction_schema_digest,
  routing_policy_digest,
  escalation_policy_digest,
  normalization_version,
  gate_version
)
```

同一 PDF 在不同 Harness 下必须开新 run，不能重放旧 run。

## P0-5 产品 normalization 与 eval normalization 分离

```text
invoiceloop/product_normalization.py  # 可作为候选演化面
invoiceloop/eval/reference_normalization.py  # 冻结，不可编辑
```

否则候选可以通过放宽“相等”定义来提高分数。

## P0-6 取消无冲突 TIER1 的伪人工审批

系统自动放行必须记录为：

```text
policy_accept
```

而不是生成或要求一条人类 `accept`。

只有完成这一点，41.1% 才能作为真实 mandatory field review load，而不是反事实分诊率。

---

# 5. 核心数据契约

## 5.1 HarnessManifest

```json
{
  "harness_id": "HAR-0003",
  "parent_harness_id": "HAR-0002",
  "status": "candidate",
  "created_from_findings": ["FIND-0012"],
  "components": {
    "routing_policy.yaml": "sha256:...",
    "escalation_policy.yaml": "sha256:...",
    "extraction_schema.json": "sha256:..."
  },
  "code_revision": "...",
  "schema_version": 1
}
```

## 5.2 FeedbackEvent

FeedbackEvent 必须绑定原始裁决和当时 Harness：

```json
{
  "feedback_id": "FB-000042",
  "decision_id": "HD-0031",
  "run_id": "run-0017",
  "review_snapshot_id": "...",
  "execution_fingerprint": "...",
  "harness_id": "HAR-0001",

  "doc_id": "...",
  "field": "amount_due",
  "tier": "TIER1",
  "claim_id": "FC-0012",
  "predicted_value": "850.00",
  "final_value": "1000.00",

  "human_action": "correct",
  "reason_code": "WRONG_FIELD_MAPPING",
  "error_stage": "semantic_mapping",
  "severity": "critical",
  "reviewer_confidence": "high",
  "actionable": true,

  "route_reason_codes": ["LABEL_CONVENTION", "SINGLE_SOURCE"],
  "review_probability": 1.0,
  "evidence_refs": ["ES-0012", "ES-0014"]
}
```

### Reason code 最小集合

```text
WRONG_VALUE
WRONG_FIELD_MAPPING
BAD_SOURCE_BINDING
MISSING_EXTRACTION
NORMALIZATION_ERROR
ROUTING_FALSE_NEGATIVE
ROUTING_FALSE_POSITIVE
CONFIRMED_ABSENT
NOT_APPLICABLE
AMBIGUOUS_DOCUMENT
PROVIDER_FAILURE
REVIEWER_PREFERENCE
```

### 反馈可用性

只有以下事件可直接进入改进标签：

```text
reviewer_confidence = high/medium
AND actionability = true
AND action != abstain
AND 无 reviewer conflict
```

`REVIEWER_PREFERENCE`、`AMBIGUOUS_DOCUMENT` 不能作为自动放行规则的负样本。

## 5.3 Finding

```yaml
finding_id: FIND-AMOUNT-DUE-0012
status: confirmed
scope:
  field: amount_due
  tier: TIER1
  cohort_expression:
    support_strength: corroborated
    cross_mode_agreement: pass
    citation_holds: pass
    warning_subset: [visual_corroboration_unavailable]
observations:
  reviewed: 43
  corrected_critical: 0
  accepted_unchanged: 40
  abstained: 3
  randomized_qa_cases: 8
hypothesis:
  component: routing_policy
  statement: >
    This warning cohort creates low-yield reviews and may be eligible
    for policy acceptance when no hard blocker is present.
preserve:
  - arithmetic failures remain review
  - citation failures remain review
  - label-convention disputes remain review
prediction:
  review_load_delta_pp: -4.0
  critical_silent_error_delta: 0
  dws_credit_delta: 0
```

## 5.4 CandidateManifest

```yaml
candidate_id: CAND-0012-A
parent_harness_id: HAR-0001
finding_ids: [FIND-AMOUNT-DUE-0012]
component: routing_policy
editable_files:
  - harness/routing_policy.yaml
forbidden_files_digest: sha256:...
max_diff_lines: 80
prediction_contract:
  review_load_delta_pp: [-6.0, -2.0]
  critical_silent_errors_added: 0
resource_budget:
  extra_dws_credits_per_invoice: 0
  extra_latency_ms: 0
eval_plan_id: EP-0012
```

## 5.5 EvalResult

结果必须同时记录 baseline 与 candidate，并绑定数据集指纹：

```json
{
  "candidate_id": "CAND-0012-A",
  "baseline_harness_id": "HAR-0001",
  "dataset_fingerprints": {
    "targeted": "...",
    "regression": "...",
    "promotion": "..."
  },
  "integrity": "PASS",
  "metrics": {
    "baseline": {},
    "candidate": {},
    "paired_delta": {}
  },
  "qualification": "PASS",
  "failure_reasons": []
}
```

## 5.6 PromotionRecord

```json
{
  "promotion_id": "PROM-0004",
  "candidate_id": "CAND-0012-A",
  "from_harness_id": "HAR-0001",
  "to_harness_id": "HAR-0002",
  "decision": "promote",
  "approved_by": "...",
  "approved_at": "...",
  "rationale": "...",
  "rollback_harness_id": "HAR-0001"
}
```

---

# 6. 状态机

## 6.1 Finding

```text
draft
→ confirmed_actionable
→ candidate_opened
→ resolved | rejected | deferred
```

模糊或不可行动：

```text
draft → non_actionable
```

## 6.2 Candidate

```text
draft
→ lint_passed
→ targeted_passed
→ regression_passed
→ promotion_qualified
→ promoted | rejected | deferred
```

任一阶段失败即停止，不自动“修到过”。新尝试必须新建 candidate ID。

## 6.3 Harness

```text
candidate → qualified → active → retired
```

只允许一个 active pointer，但所有历史版本永久保留。

---

# 7. 可编辑面与实施分层

## 7.1 v0.1：配置级 Harness Evolution（黑客松主线）

只允许编辑：

```text
routing_policy.yaml
review_priority.yaml
field_playbooks/*.yaml
```

首个候选类型必须是：

> **Cohort-based routing relaxation：把一组低收益软风险从 mandatory review 改为 policy_accept。**

候选规则只允许引用通用特征：

- field / tier；
- support strength；
- gate verdict vector；
- warning reason codes；
- DWS confidence bucket；
- document family / layout family（必须有最小样本）；
- provider mode status。

禁止引用：

- doc ID；
- benchmark row number；
- ground-truth value；
- 特定测试文件名；
- 单个供应商名称的硬编码，除非明确是产品级 vendor policy 且人工批准。

## 7.2 v0.2：运行时升级策略

开放：

```text
escalation_policy.yaml
```

允许：

```text
understand
→ 初步 gates
→ 只对边界风险字段/文档调用 agentic
→ re-gate
→ 仍冲突才人工
```

这类候选必须做 paired live DWS evaluation，因为冻结旧响应无法评估新的调用顺序。

## 7.3 v0.3：Extraction Schema Candidate

开放：

```text
extraction_schema.json
```

必须：

- 一个 candidate 只改一个或少量字段描述；
- paired live extraction；
- 保留所有原始响应；
- 报告 credits 和 provider drift；
- 不修改 eval normalizer。

## 7.4 暂不开放：任意 Python 自修改

黑客松期间不允许 agent 任意编辑：

```text
freeze.py
snapshot.py
adjudicate.py
review.py
deliver.py
bundle verifier
eval scorer
```

将来若开放代码级 candidate，也只能写入独立的：

```text
invoiceloop/harness_plugins/
```

并通过 import allowlist、静态检查和 sandbox。

---

# 8. 权限与沙箱

## 8.1 三进程隔离

### Proposer

可读：

- Finding pack；
- 脱敏/必要的 traces；
- 公开架构文档；
- allowlisted harness files；
- targeted development cases。

可写：

- candidate worktree 中的 allowlisted files；
- `proposal.yaml`；
- `prediction.md`。

不可读：

- promotion/final labels；
- private scorer internals；
- active credentials。

不可写：

- production workspace；
- trust kernel；
- git main branch；
- active harness pointer。

### Evaluator

可读：

- baseline/candidate Harness；
- frozen source inputs；
- private ground truth；
- scorer。

可写：

- immutable `eval_result.json`。

不可写：

- candidate diff；
- active harness；
- production evidence。

### Promoter

必须是显式人类命令，读取 EvalResult，写 PromotionRecord 和 active pointer。

## 8.2 Candidate Diff Linter

自动拒绝：

- 修改不在 allowlist 的路径；
- 修改 eval/ground truth；
- 新增网络调用；
- 新增依赖；
- 提高预算上限；
- 出现 DocILE doc ID；
- 出现 hard-coded expected value；
- diff 超过预设大小；
- 同时修改多个组件；
- 删除日志、测试或失败案例。

## 8.3 数据隐私

生产发票或人工理由发送给外部 proposer 模型前必须：

- 获得明确授权；
- 最小化上下文；
- 优先提供结构化 feature / crop，而非整份发票；
- 对银行账号、税号、地址等敏感字段做脱敏；
- 将模型、provider 和发送工件记录进 candidate trace。

---

# 9. 反馈质量：防止“从人工数据学错”

## 9.1 双层反馈

每次人工操作分成：

1. **业务裁决**：最终值或状态；
2. **诊断标签**：为什么系统需要被改进。

业务裁决必须完成；诊断标签尽量使用单击 reason code，降低额外人工负担。

Agent 可以建议 reason code，但必须由人确认，不能自行写成真值。

## 9.2 Reviewer confidence

```text
high     页面证据明确
medium   有推断但较确定
low      依赖业务判断或页面模糊
```

自动策略放宽只使用 high/medium 且无冲突的反馈。

## 9.3 双人复核

至少对以下样本进行第二人复核：

- 所有 candidate-only critical errors；
- `not_applicable`；
- `confirm_absent`；
- 一定比例的 policy-accepted QA 样本；
- reviewer confidence=low。

## 9.4 随机 QA 与选择偏差

每个自动接受字段记录：

```text
review_probability
```

建议：

```text
正常 auto-accept：5% 分层随机 QA
新 layout / 新供应商 / provider 漂移：10%–20%
刚晋升政策命中的 cohort：首批 20% QA，稳定后下降
```

分层至少按：

- TIER1/TIER2；
- field；
- document family；
- support strength；
- policy cohort；
- 新旧 layout。

**未复核不等于正确。** Weakness Miner 不得把没有 feedback 的 auto-accepted slot 当负例。

---

# 10. Weakness Mining

## 10.1 不直接喂全部 raw trace

构建分层 Experience Pack：

```text
Level 0：总体指标和 drift
Level 1：cohort 统计
Level 2：代表性 review rows
Level 3：具体 source / crop / gate / claim trace
```

这对应：

- component observability：明确哪一组件可改；
- experience observability：把长轨迹压成可下钻证据；
- decision observability：每个改动都带可验证预测。

## 10.2 Cohort key

第一版可用：

```text
field
× tier
× support_strength
× gate verdict vector
× warning reason set
× DWS confidence bucket
× document family
× harness_id
```

## 10.3 统计项

```text
reviewed_count
accept_unchanged_count
critical_correction_count
noncritical_correction_count
reject_count
confirm_absent_count
not_applicable_count
abstain_count
random_qa_count
review_seconds
```

## 10.4 最小样本纪律

不建议把“n≥30”误当成安全证明。即使 30 次零错误，真实错误率上界仍很宽。

规则：

- n<30：只能提出“收集更多证据”，不能提出自动放行；
- n≥30：允许生成 exploratory candidate；
- 是否晋升由独立 promotion eval 决定；
- 不对外声称绝对错误率保证。

## 10.5 Finding 必须带保留集

每个 finding 除“要修什么”外，必须写：

- 哪些成功行为不能破坏；
- 哪些 hard blocker 永不放松；
- 预计影响哪些成本；
- 哪些 subgroup 可能回归。

---

# 11. Routing Policy 设计

当前 `matrix.py` 将“任何 warning”统一变成 `requires_adjudication=True`。建议改为显式、版本化 policy。

## 11.1 四种 route

```text
auto_accept  满足当前 Harness 的自动放行合同
review       需要人工解决
block        缺少基础证据或存在不可放行风险
escalate     先调用额外机器步骤，再重新评估
```

## 11.2 Hard blockers（Improve v0.1 禁止放松）

至少包括：

- 文档级 OCR / extraction 基础设施不可用；
- 冻结绑定失败；
- TIER1 citation fail；
- TIER1 arithmetic fail；
- 两个竞争 claim；
- label convention dispute；
- cross-document duplicate/conflict；
- required TIER1 missing 且未 confirm_absent/not_applicable；
- 银行或支付信息异常（未来加入时）；
- bundle / snapshot integrity fail。

## 11.3 Soft review triggers（候选可研究）

例如：

- visual corroboration unavailable；
- 某些 TIER2 单一来源；
- 不参与恒等式导致 arithmetic unavailable；
- 已知合法缺失；
- 不影响金额/支付的格式 warning；
- 经 QA 证实低收益的特定 gate combination。

## 11.4 Candidate 只改软触发

第一版 candidate 不能删除 hard blocker，只能把一个清晰 cohort 的：

```text
review → auto_accept
```

或者：

```text
review → escalate
```

每个变更必须带 reason code 和 policy digest。

---

# 12. 评测目标与指标

## 12.1 不优化单一综合分

采用词典序：

```text
1. Integrity
2. Critical safety
3. Human workload
4. Cost and latency
```

人工量永远不能覆盖安全失败。

## 12.2 Headline 指标

### Mandatory field review load

```text
必须人工处理的记分字段数 / 全部记分字段数
```

41.1%→30%必须明确是这个口径。

### Document touch rate

```text
至少有一个 mandatory field 的文档数 / 全部文档数
```

### Human actions per invoice

```text
人工提交的有效裁决动作数 / 文档数
```

### Reviewer minutes per invoice

真实计时，而不是由字段数量代替。

## 12.3 安全指标

### Critical selective risk

```text
自动接受但错误的 TIER1 字段数
/ 自动接受的 TIER1 字段数
```

### Critical generalized silent risk

```text
自动接受但错误的 TIER1 字段数
/ 全部有标签的 TIER1 字段数
```

后者不受 accepted 分母变化的误导，适合作为主安全指标。

### Critical routing recall

```text
进入人工/阻断的关键错误
/ 全部关键错误
```

### Critical document silent failure

```text
被 release 且仍含至少一个关键错误的文档
/ 全部 release 文档
```

## 12.4 全曲线指标

不能只看 41% 和 30% 两个工作点。至少画：

```text
x = review load
 y = generalized critical silent risk
```

并报告：

- critical error recall@10/20/30/40% review budget；
- risk–coverage curve；
- AUGRC 或等价平均未检测风险指标。

## 12.5 成本指标

```text
DWS credits per invoice
API calls per invoice
P50/P95 latency
storage bytes
reviewer minutes
```

---

# 13. 数据集与防过拟合协议

## 13.1 现有 100 份的身份

现有 100 份已经用于结果分析和方案设计，因此从 Improve 项目开始应改名为：

```text
EVOLUTION / DEVELOPMENT CORPUS
```

不能再作为最终 held-out。

## 13.2 四类数据

### EVO

完全可见，用于：

- mining；
- finding；
- targeted eval；
- candidate 开发。

### REGRESSION

由 evaluator 持有。包含：

- 已知关键失败；
- clean negative controls；
- integrity attacks；
- 不相关字段和其他 layout。

可以重复运行，但不能由 proposer 修改。

### PROMOTION-k

每轮新取、对 proposer 隐藏。只返回资格结果和聚合指标，不返回全部逐样本答案。

被使用后即“燃烧”，下轮不能继续充当 promotion set。

### FINAL SEALED

所有轮次结束后只运行一次，用于最终对外结果。

## 13.3 Query budget

每轮：

- 最多 3 个 candidate；
- 每个 candidate 最多一次 PROMOTION 查询；
- 失败不能在同一 promotion set 上无限修补；
- 所有查询写入 `evaluation_access_ledger.jsonl`。

## 13.4 配对评测

Baseline 和 Candidate 必须在完全相同文档上运行。

下游 routing candidate：使用同一份冻结 DWS responses，隔离 provider drift。

schema/escalation candidate：使用 paired live calls，并记录调用顺序、request schema、credits 和 raw response。

## 13.5 统计不确定性

- 以文档为 bootstrap 单位，不把同一发票多个字段当独立样本；
- 固定随机种子并记录；
- 报告 95% bootstrap interval；
- 小样本时报告精确分子/分母；
- 不把“未观察到新增错误”写成“已证明没有风险”。

---

# 14. 实验流程：41% → 30%

## R-1：语义与完整性准备

完成全部 P0，不计为 Improve 成果。

验收：

- `policy_accept` 与人工决定分离；
- accept 值来自 ledger；
- absent / N/A / abstain 分离；
- routing report 版本化；
- Harness 进入 execution fingerprint；
- bundle semantic verify；
- reviewer time / QA sampling 可记录。

## R0：冻结真实基线

冻结：

```text
code revision
HAR-0001 digest
TIER1 field set
hard blockers
metrics/scorers
data split fingerprints
candidate query budget
```

报告：

- field review load；
- document touch rate；
- actions/doc；
- minutes/doc；
- critical generalized/selected risk；
- routing recall；
- DWS credits。

只有重新测量结果约为 41%，才能对外讲“41→30”。

## R1：消除无价值软复核

目标：找出：

```text
被 review
但大量 accept unchanged / confirm_absent
且随机 QA 未发现关键漏错
```

候选：

```text
特定 soft-warning cohort
review → policy_accept
```

要求：

- 不触碰 hard blockers；
- 一个候选一个 cohort；
- target + negative control；
- promotion set 无新增关键静默错误。

## R2：风险桶与 Review Budget Policy

在 R1 的新反馈基础上，构建保守的 risk bucket：

```text
field × support × gates × warning set × document family
```

不是直接相信点估计，而是根据样本量和不确定性给出风险上界/分层。

目标：

```text
在 30% review budget 下最大化 critical error recall
```

候选可调整：

- 哪些软触发 mandatory review；
- priority；
- QA sampling rate。

## R3：机器升级替代人工

目标：将一部分边界字段从：

```text
review
```

改为：

```text
escalate to agentic / focused extraction
→ re-gate
→ unresolved 才 review
```

必须报告新增 DWS credits 与减少的人工分钟，证明不是“用无限 API 换人工”。

## Final：一次性 sealed evaluation

最终表：

| 版本 | Field review load | Document touch | Critical generalized silent risk | Critical routing recall | Minutes/doc | Credits/doc |
|---|---:|---:|---:|---:|---:|---:|
| R0 | 实测 | 实测 | 实测 | 实测 | 实测 | 实测 |
| R1 | 实测 | 实测 | 实测 | 实测 | 实测 | 实测 |
| R2 | 实测 | 实测 | 实测 | 实测 | 实测 | 实测 |
| R3 | 实测 | 实测 | 实测 | 实测 | 实测 | 实测 |
| Sealed final | 实测 | 实测 | 实测 | 实测 | 实测 | 实测 |

禁止预填后续数字。

---

# 15. Promotion Gates

## Gate 0：权限与完整性

必须全部通过：

- forbidden files 未变化；
- trust kernel tests 全绿；
- bundle semantic verify 全绿；
- candidate diff 在 allowlist；
- 无 doc ID / expected value 硬编码；
- execution fingerprint 正确变化。

## Gate 1：Must-Catch Regression

以下已知关键案例不能从 review/block 变成 auto_accept：

- citation fail；
- arithmetic fail；
- binding reject；
- label convention dispute；
- duplicate/conflict；
- missing required TIER1；
- document-level infrastructure blocked。

## Gate 2：Safety Non-Inferiority

同一 promotion docs 上：

```text
candidate critical generalized silent errors
≤ baseline critical generalized silent errors
```

同时：

- 无新增 severity=critical 的 candidate-only document failure；
- 报告 paired document bootstrap delta；
- subgroup 无明显红旗。

这是黑客松版保守门槛，不等于统计学上的永久安全保证。

## Gate 3：Workload Benefit

建议每轮工程门槛：

```text
field review load 至少下降 2.5 percentage points
OR reviewer minutes 至少下降 10%
```

该数字是预注册工程门槛，不是科学定律。

## Gate 4：Resource Budget

- DWS credits 不超过 candidate manifest 上限；
- P95 latency 不超过上限；
- 不新增未披露 provider；
- 不降低 QA sampling 以制造人工率下降。

## Gate 5：Human Promotion

人类看到：

- finding；
- exact diff；
- predicted vs actual delta；
- target/regression/promotion results；
- 新增风险；
- rollback target。

然后选择：

```text
promote / reject / defer
```

---

# 16. Shadow、Canary 与回滚

## 16.1 Shadow

Candidate 先对新发票产生反事实 route，不改变真实工作流：

```text
active policy 决定实际 review
candidate policy 只记录 shadow decision
```

这提供新分布证据。

## 16.2 Canary

晋升后先应用于小比例、低风险 cohort，并提高 QA sampling。

## 16.3 自动回滚触发

可以自动把 active pointer 回滚到上一版，但不能自动修复 Harness。触发包括：

- QA 出现 candidate-only critical error；
- provider response drift 超过阈值；
- document touch / latency 异常；
- integrity test 失败；
- 新 layout 比例突然上升。

所有回滚写入 append-only promotion ledger。

---

# 17. Provider Drift

当前仓库的 live test 已观察到同批 PDF 在不同时点 DWS 输出漂移，因此必须把“策略改进”和“provider 变化”分开。

## 17.1 Replay Eval

适合：

- routing policy；
- review priority；
- warning taxonomy；
- downstream mapping。

使用完全相同的 raw DWS response，结果确定性。

## 17.2 Live Paired Eval

适合：

- extraction schema；
- mode selection；
- escalation policy。

要求：

- 同文档 baseline/candidate 配对；
- 原始请求和响应全部冻结；
- 报告 provider error / missing / confidence distribution；
- 调用顺序随机或交错；
- 不把 provider drift 误写成 candidate 改进。

## 17.3 Safe Mode

当 drift 触发：

```text
暂停新的 policy relaxation
提高 QA sample
回退到最近 safe harness
允许人工率超过 30%
```

30% 是正常分布目标，不是硬预算上限。

---

# 18. 明确禁止事项

1. 禁止 agent 自动晋升或发布。
2. 禁止修改 Trust Kernel。
3. 禁止修改 ground truth、scorer、critical field set、promotion rules。
4. 禁止让 proposer 读取 promotion/final labels。
5. 禁止同一 sealed set 上反复调参。
6. 禁止覆盖失败 candidate；每次尝试必须新 ID。
7. 禁止删除失败结果、负面 findings 或回滚记录。
8. 禁止把未复核字段视为正确。
9. 禁止把所有 human `accept` 视为无噪声真值。
10. 禁止使用读图模型/DWS confidence 作为 ground truth。
11. 禁止通过 `not_applicable`、字段删除或 normalization 放宽降低 review rate。
12. 禁止使用 doc ID、benchmark index、expected value 硬编码规则。
13. 禁止一次 candidate 修改多个 Harness 组件。
14. 禁止未披露地增加 API 次数、预算、延迟或 provider。
15. 禁止改变 QA sampling 以美化人工率。
16. 禁止将 41.1% 称为 document review rate，除非重新实测确实如此。
17. 禁止把开发集改善称为 generalization。
18. 禁止把“零新增观察错误”写成“证明零风险”。
19. 禁止在没有完整 promoted cycle 前称“系统已自我改进”。
20. 禁止让系统为了 30% 硬预算放过已知 blocker。

---

# 19. 建议代码结构

```text
invoiceloop/
  harness.py                 # 加载 immutable HarnessManifest
  routing.py                 # 纯函数：ledger+gates+policy → RoutingReport
  execution.py               # execution_fingerprint
  feedback.py                # adjudication → FeedbackEvent
  qa_sampler.py              # 分层随机 QA / propensity

  improve/
    models.py                # Finding/Candidate/Eval/Promotion schemas
    compile.py               # 生成 Experience Pack
    mine.py                  # deterministic weakness mining
    propose.py               # agent task pack / candidate manifest
    lint.py                  # diff allowlist / anti-cheat
    sandbox.py               # worktree 与权限
    metrics.py               # 风险—覆盖、人工、成本
    evaluate.py              # targeted/regression/promotion
    promote.py               # human-only promotion
    report.py                # before/after + prediction audit

harnesses/
  HAR-0001/
  HAR-0002/

workspace/
  improve/
    feedback/events.jsonl
    findings/FIND-*/
    candidates/CAND-*/
    evaluations/EVAL-*/
    promotions/PROM-*.json
    improvement_ledger.jsonl
    active_harness.json
    evaluation_access_ledger.jsonl
```

保持项目现有的文件系统、不可变目录和 append-only 风格；黑客松阶段没有必要引入数据库。

---

# 20. CLI 合同

```bash
# 从权威 run 和裁决重建反馈事件
python -m invoiceloop feedback compile --workspace ws

# 确定性统计与 finding 草稿
python -m invoiceloop improve mine --workspace ws

# 人确认 finding 为 actionable
python -m invoiceloop improve confirm-finding \
  --finding FIND-0012 --reviewer Stahl

# agent 只在 allowlisted Harness component 内提出候选
python -m invoiceloop improve propose \
  --finding FIND-0012 --component routing_policy

# lint + targeted + regression
python -m invoiceloop improve evaluate \
  --candidate CAND-0012-A --stage regression

# 一次 promotion-set 查询
python -m invoiceloop improve qualify \
  --candidate CAND-0012-A

# 只有人能执行
python -m invoiceloop improve promote \
  --candidate CAND-0012-A \
  --approved-by Stahl \
  --rationale "..."

# 展示 41%→X% 的完整轨迹
python -m invoiceloop improve report --workspace ws
```

---

# 21. 必须新增的测试

## Trust / identity

- Harness digest 变化 → execution fingerprint 必须变化；
- 相同输入 + 不同 Harness 不得 replay 旧 run；
- accept_claim 必须取 ledger value；
- matrix tamper 不得改变 deliverable；
- semantic verify 能抓最终值错绑；
- `confirm_absent/not_applicable/abstain` 投影不同。

## Improve permissions

- candidate 修改 forbidden path → reject；
- candidate 包含 doc ID / expected value → reject；
- candidate 修改 scorer → reject；
- candidate 增加网络调用/依赖/预算 → reject；
- candidate 多组件 diff → reject。

## Eval integrity

- proposer 无法读取 private labels；
- promotion query 计入 access ledger；
- consumed promotion set 不可复用；
- baseline/candidate 文档集必须完全一致；
- metric bootstrap seed 记录；
- field-level metric 不错误当 document-level metric。

## Improvement semantics

- 排序 candidate 不得宣称降低 review load；
- policy relaxation 不能覆盖 hard blockers；
- review rate 下降但新增 critical silent error → qualification fail；
- QA sampling 下降 → qualification fail；
- agent prediction 与实际结果差异被记录，不得覆盖。

---

# 22. 黑客松演示脚本

## 画面 1：保守起点

```text
HAR-0001
Mandatory field review load: 41.1%
```

展示一张无实际错误但因为 soft warning 被送人工的字段。

## 画面 2：每次复核留下结构化反馈

人点击：

```text
accept_claim
reason = ROUTING_FALSE_POSITIVE
confidence = high
```

显示它进入 Feedback Event，而不是只改当前 JSON。

## 画面 3：Finding

```text
This cohort caused 43 reviews,
0 critical corrections,
8 randomized QA checks,
no hard blocker.
```

## 画面 4：Agent Candidate

Agent 只能修改 `routing_policy.yaml` 的一条规则，并写出预测：

```text
Expected review-load reduction: 4pp
Expected new critical silent errors: 0
```

## 画面 5：评测门控

同屏显示：

```text
Targeted: PASS
Regression: PASS
Promotion: PASS
Integrity: PASS
Review load: 41.1% → 36.8%
Critical silent errors: unchanged
```

实际数字出来前不能预填。

## 画面 6：Human Promote

人点击 Promote，生成 HAR-0002 和 PromotionRecord。

## 画面 7：下一张发票

新 run manifest 明确绑定 HAR-0002；同类软 warning 自动 policy_accept，完整审计链说明为什么不再需要人看。

## Demo 结尾

> **Every review becomes an eval. Every policy change must re-earn trust.**

---

# 23. 可公开声称与禁止声称

## 完成 v0.1 且有一次 promotion cycle 后可声称

- InvoiceLoop captures human review as structured feedback events.
- Repeated actionable feedback becomes bounded Harness candidates.
- Candidates cannot modify evidence, evaluators or production policy.
- Every candidate is tested against targeted and regression evals before human promotion.
- A promoted policy reduced measured review load from R0 to R1 on an unseen qualification set.
- Every future run binds the exact Harness version that produced its routing decisions.

## 完成 final sealed evaluation 后可声称

- On a fresh sealed DocILE-derived set, the promoted Harness reduced mandatory field review load from X% to Y% without increasing observed critical generalized silent failures.

必须带：

- 精确分母；
- 数据集范围；
- confidence interval；
- 人工时间与 DWS 成本；
- 非生产适用声明。

## 禁止声称

- InvoiceLoop autonomously learns from every invoice.
- Human review is no longer required.
- The system guarantees less than 1% error.
- The underlying DWS model improved.
- 30% is universally optimal.
- The system is production-safe based only on DocILE.

---

# 24. 研究与工程依据

本设计吸收以下思想，但不照搬其自治强度：

1. **OpenAI, “Building self-improving tax agents with Codex”**  
   专家修正 → 产品 trace → actionable findings → targeted eval → scoped engineering task → regression → human shipping。

2. **Lilian Weng, “Harness Engineering for Self-Improvement” (2026)**  
   Harness 包括 workflow、evaluation、permission control 和 persistent state；evaluator 与权限控制应位于演化循环之外，人类应上移到关键抽象层。

3. **Agentic Harness Engineering (AHE), arXiv:2604.25850**  
   component / experience / decision observability；每个改动必须是可证伪预测。

4. **Self-Harness, arXiv:2606.09498**  
   Weakness Mining → Harness Proposal → Proposal Validation；候选必须经 regression 才接受。

5. **Harness Updating Is Not Harness Benefit, arXiv:2605.30621**  
   能写 Harness 更新不等于下游真的受益；InvoiceLoop 必须评估未来 run 的实际 review/risk，而不是 proposal 文案质量。

6. **Adaptive Auto-Harness, arXiv:2606.01770**  
   开放任务流中单一持续密集更新的 Harness 可能变脆；应监控 drift、保留回滚，并避免把局部 finding 无条件全局化。

7. **HarnessCompass, arXiv:2608.01918（非常新的预印本）**  
   constrained evolution、component-wise optimization 和避免组件间干扰；第一版一个 candidate 只改一个组件。

8. **Selective Classification, arXiv:1705.08500**  
   自动接受与拒绝/人工之间本质是 risk–coverage trade-off，不能只看单点 accuracy。

9. **Conformal Risk Control, arXiv:2208.02814 / ICLR 2024**  
   未来在样本量与选择偏差条件满足后，可研究用校准程序控制单调风险；不应在当前小样本黑客松阶段夸大保证。

10. **Dwork et al., adaptive data analysis / reusable holdout**  
    反复查看同一测试集并据此改策略会过拟合；需要限制测试集暴露、燃烧 promotion set，并保留一次性 final sealed set。

11. **NIST AI RMF 1.0**  
    明确角色、反馈整合、持续监控、TEVV、变更管理、第三方模型 drift 和人类监督。

以上 2026 Harness 论文多数为新近预印本，适合作为架构启发，不应当作已经形成行业标准的证据。

---

# 25. 最终实施裁决

## PASS

- 把 Improve Layer 作为 InvoiceLoop 的核心新增叙事；
- 以 41%→30% 作为清晰的产品目标；
- 采用反馈→finding→candidate→eval→human promotion→future run 的完整循环；
- 使用 AHE 式三类 observability；
- 使用 Self-Harness 的 mine/propose/validate 骨架；
- 使用 Tax AI 的 trace-to-eval 工程路径。

## HOLD，直到 P0 完成

- 最终值权威绑定；
- 人工决策语义拆分；
- policy_accept；
- routing report；
- Harness execution identity；
- evaluator 与 product normalization 分离。

## 第一版明确不做

- 任意 repo 自修改；
- 自动 promotion；
- 多组件联合优化；
- 模型权重更新；
- 把现有 100 份继续冒充 final held-out；
- 用一个综合分掩盖安全回归。

**一句话结论：**

> InvoiceLoop Improve Layer 不应当是一个“会改规则的 agent”，而应当是一个把真实人工复核变成可归因评测任务、只允许受限 Harness 候选、并要求每次改进在未见数据上重新赢得信任的控制面。
