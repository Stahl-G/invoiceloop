# InvoiceLoop Hackathon Scoring Rubric v0.1

> **冻结说明(本节由冻结提交追加,正文未改动)**
>
> - **状态**:FROZEN。本文件在按 repo 事实打分**之前**提交,冻结评分标准与权重。
> - **来源**:用户提供,非 Nutrient 官方计分表;由官方要求(Overall Round 看
>   Progress/Concept/Feasibility;Sponsor Round 要求 DWS 承担核心文档操作、
>   强调确定性输出/置信判断/人工介入/审计轨迹)反推的内部评审标准。
> - **正文逐字保留**,不因 repo 现状调整任何维度权重。后续若要改权重,
>   另开 v0.2 并说明改动理由与时间,不得就地覆盖 v0.1。
> - **冻结纯度限定(必须显式登记)**:本文件由 Claude 写入,而
>   `CLAUDE.md` 在会话开始时自动进入上下文,其中已包含关于本 repo 的成果声明
>   (M0–M4 落地、116 条测试、lift 4.10×/3.04× 等)。因此这是
>   **"未读实现代码前冻结"**,不是**"对 repo 一无所知时冻结"**。
>   按宪章六,这条限定必须随任何引用本 rubric 的评分结果一并出现。

可以。下面这份 **InvoiceLoop Hackathon Scoring Rubric v0.1** 先完全独立于你的 repo，用来冻结评分标准，避免 agent 看完现有实现后再“量身定做”评价尺度。

这不是官方公布的数字权重，因为 Nutrient 没有给出 sponsor round 的详细计分表；它是根据官方要求反推的内部评审标准。官方 Overall Round 明确看三件事：**Progress、Concept、Feasibility**；Nutrient Sponsor Round 则强调：DWS 必须承担至少一个有意义的核心文档操作，并特别重视确定性输出、置信判断、人工介入和完整审计轨迹。

对 InvoiceLoop，最核心的评分问题应当是：

> **InvoiceLoop 是否在不把所有发票都扔给人工的前提下，相比原始 DWS 输出显著降低了静默错误，并且让每一次自动放行、人工复核和最终修改都可以解释、追溯和回放？**

---

## 一、先过资格门，不直接计分

官方要求提交 public repo 或 shared link、setup instructions、2–4 分钟端到端演示，以及一句话说明 DWS 在哪里承担核心工作。

| Gate | 检查内容 | 处理方式 |
|---|---|---|
| G1：DWS 核心使用 | Nutrient DWS API、SDK 或 Viewer 是否承担真实的核心文档操作，而不是一次装饰性 API 调用 | **FAIL 时不具备 Nutrient Sponsor Challenge 资格** |
| G2：证据诚信 | 是否存在伪造指标、硬编码演示结果、使用测试集标签参与运行时决策、隐瞒失败样本 | 出现确定证据时标记 **INVALID，最终分 0** |
| G3：可运行闭环 | 是否至少有一次真实的“上传→DWS→判断→复核/放行→最终结果”运行 | 没有则最终分最高 **59** |
| G4：提交完整性 | repo/shared link、安装说明、2–4 分钟视频、DWS heavy-lifting 说明是否齐全 | 缺少则最终分最高 **89** |
| G5：比赛时间合规 | 是否说明比赛前已有代码、比赛期间新增代码和复用组件 | 不由 agent 自行判违规；标记 `REQUIRES_HUMAN_CONFIRMATION` |

官方 instructions 写的是 teams should build apps from scratch。鉴于正式线上赛程为 2026 年 8 月 17 日至 9 月 3 日，建议保留清晰的 commit timeline，并披露哪些是既有通用组件、哪些是在比赛窗口内完成。

---

# 二、100 分正式评分表

## 分数结构

- **Overall Round proxy：30 分**
  A + B + C，对应官方的 Concept、Progress、Feasibility。
- **Nutrient Sponsor Round proxy：63 分**
  D + E + F + G + H。
- **Submission quality：7 分**
  I。

| ID | 评分维度 | 分值 |
|---|---|---:|
| A | 真实问题与项目概念 | 10 |
| B | 项目进展与端到端执行 | 12 |
| C | 落地与创业可行性 | 8 |
| D | Nutrient DWS 集成深度 | 15 |
| E | 可靠性改进与实验证据 | 20 |
| F | 风险路由与 Human-in-the-Loop | 13 |
| G | 审计、来源与可回放性 | 10 |
| H | 创新性与差异化 | 5 |
| I | 提交材料与演示表达 | 7 |
|  | **合计** | **100** |

---

## A. 真实问题与项目概念｜10 分

| 子项 | 分值 | 满分标准 |
|---|---:|---|
| 明确用户与工作流 | 3 | 明确是 AP clerk、财务审核人、审计人员、ERP 操作员或其他具体角色，而非泛称“企业用户” |
| 明确错误代价 | 3 | 说明哪些错误会导致错付、重复付款、税务问题、供应商错误或审计风险 |
| 明确目标结果 | 2 | 目标不是“识别更准”，而是降低静默错误、减少无价值复核，同时保持自动化 |
| 与挑战主题匹配 | 2 | 清楚解释为什么这是“让人真正信任文档结果”的问题 |

### 评分锚点

- **0–2：** 只是“AI OCR for invoices”。
- **3–5：** 有发票识别场景，但没有明确用户、错误成本或工作流。
- **6–8：** 问题、用户和信任风险清楚。
- **9–10：** 能用一句话讲清楚“谁在什么环节，因为哪类静默错误遭受什么损失，InvoiceLoop 如何改变决策”。

一个理想的一句话概念可以是：

> InvoiceLoop is a risk-aware verification layer that turns raw invoice extraction into an auditable decision: safe fields flow through, risky fields go to a human with the exact source evidence, and every decision can be replayed.

---

## B. 项目进展与端到端执行｜12 分

| 子项 | 分值 | 满分标准 |
|---|---:|---|
| 完整核心流水线 | 4 | 上传发票 → DWS 抽取 → 标准化/校验 → 风险判断 → 自动放行或人工复核 → 最终结果 |
| 正常路径 | 2 | 至少有真实 clean invoice 成功完成自动处理 |
| 异常路径 | 3 | 至少有真实 risky invoice 被正确拦截、解释、修改和批准 |
| 可复现运行 | 3 | 有清楚 setup、固定配置、测试命令和可重复示例 |

### 不能拿高分的情况

- 前端页面能打开，但核心结果来自静态 JSON。
- 只有 notebook benchmark，没有可交互产品闭环。
- 只有 happy path，没有错误、失败或人工介入路径。
- README 声称完成，但 repo 内找不到对应实现。

---

## C. 落地与创业可行性｜8 分

| 子项 | 分值 | 满分标准 |
|---|---:|---|
| 部署与集成路径 | 2 | 能说明如何进入 ERP、AP、采购或文档工作流 |
| 成本与延迟 | 2 | 报告每页或每张发票的 DWS credits、延迟和模式选择策略 |
| 隐私与安全 | 2 | API key 不进前端、不提交 secrets，说明文档和日志保存策略 |
| 商业采用逻辑 | 2 | 说明谁付费、替代什么人工步骤、为什么不是一个只能展示的 demo |

如果项目使用 `understand` 和 `agentic` 等不同模式，满分证据应包括：

- 哪些文档先走低成本模式；
- 什么信号触发昂贵模式；
- 这种动态路由是否真正改善了成本—可靠性关系。

DWS 当前将 extraction 分为 text、structure、understand 和 agentic 等模式，强调按速度、成本和处理深度选择。

---

## D. Nutrient DWS 集成深度｜15 分

| 子项 | 分值 | 满分标准 |
|---|---:|---|
| DWS 承担核心操作 | 5 | 发票解析、结构化抽取、Viewer 审核或其他关键文档操作真实依赖 DWS |
| 使用结构化证据 | 4 | 不只读取最终字符串，还利用 confidence、page、bounding box、citation、match label 或结构信息 |
| DWS 输出驱动决策 | 3 | DWS 输出真实影响自动放行、升级模式、字段复核或 UI 高亮 |
| 利用 DWS 差异化能力 | 3 | 展示来源定位、文档内复核、确定性处理、Viewer、Processor、签名等至少一种真实优势 |

Nutrient 的 Data Extraction API 会返回带页码、坐标、来源和置信信息的结构化结果，目的就是让下游系统进行验证、路由和人工复核，而不是只向 LLM 提供一段文本。

### 分数限制

- DWS 只负责把 PDF 转成文本，后续完全不使用结构或来源：通常不超过 **8/15**。
- DWS 结果没有参与任何实际决策：通常不超过 **6/15**。
- 删除 DWS 后，只需换一个 OCR endpoint，产品行为完全不变：通常不超过 **7/15**。
- 不要求为了得分强行调用多个 Nutrient 产品；**一个 API 用得深，比三个 API 装饰性调用更好。**

---

## E. 可靠性改进与实验证据｜20 分

这是 InvoiceLoop 最重要的一项。

| 子项 | 分值 | 满分标准 |
|---|---:|---|
| Held-out 评测设计 | 4 | 调参集与最终测试集分离；测试标签不参与阈值选择或运行时判断 |
| 原始基线比较 | 4 | 至少比较 raw DWS、简单 confidence threshold 和完整 InvoiceLoop |
| 抽取与关键字段指标 | 4 | 报告 DocILE 相关指标，并单列业务关键字段表现 |
| 风险—覆盖—人工负载 | 4 | 同时报告静默错误、自动化覆盖和人工复核负载，最好提供阈值曲线 |
| 错误分析与 ablation | 2 | 说明系统具体修复了什么、仍在哪些文档失败；拆除模块后效果如何变化 |
| 可复现与统计诚实 | 2 | 固定样本、版本和配置；小样本不做过强结论；报告分母与不确定性 |

DocILE 的官方任务是 KILE 和 LIR：KILE 评估字段类型与位置，LIR 还要求正确分组 line items；官方 evaluator 提供 AP、F1、precision 和 recall，并以 micro averaging 汇总。 其中位置标注本身就是为了支持人工复核和审计，这与 InvoiceLoop 的信任闭环高度一致。

但 **DocILE AP/F1 不能单独证明 InvoiceLoop 可信**。它们衡量的是抽取、定位和 line-item grouping，不直接回答：

- 错误结果是否被自动放行；
- 错误结果是否会伤害业务；
- 人工审核量是否真的下降；
- 系统是否会给错误结果虚假安全感。

### 推荐的核心指标合同

在测试前预先声明一组 `critical_fields`。示例包括：

- `invoice_number`
- `issue_date`
- `due_date`
- `currency`
- `net_amount`
- `tax_amount`
- `total_amount`
- `supplier_name`
- `supplier_tax_id`
- `buyer_tax_id`
- `purchase_order_number`
- `payment_or_bank_details`

并说明为什么某些字段属于或不属于关键字段。不能在测试结果出来后，只挑表现好的字段作为“关键字段”。

建议强制报告以下指标：

```text
critical_field_accuracy
= 正确的关键字段预测数 / 所有有标注的关键字段数
```

```text
critical_document_pass_rate
= 不包含任何关键字段错误的文档数 / 所有评测文档数
```

```text
field_silent_error_rate
= 被自动接受但实际错误的关键字段数 / 所有被自动接受的关键字段数
```

```text
document_silent_failure_rate
= 自动放行后仍含至少一个关键字段错误的文档数
  / 所有自动放行文档数
```

```text
automation_coverage
= 自动放行文档数 / 所有评测文档数
```

```text
document_review_rate
= 进入人工复核的文档数 / 所有评测文档数
```

```text
field_review_load
= 被要求人工查看的字段数 / 所有抽取字段数
```

```text
critical_error_routing_recall
= 被正确送往人工复核的关键错误文档数
  / 所有包含关键错误的文档数
```

此外建议报告：

- 每张发票平均处理延迟；
- 每页或每张发票 credits/cost；
- reviewer 平均需要确认或修改多少字段；
- raw DWS → InvoiceLoop 的净改进；
- clean docs 和 risky docs 分组结果；
- 不同 layout cluster 或文档质量下的结果。

### 关键评分原则：看 Pareto 改进，不看拍脑袋门槛

不要把以下数字直接写成科学意义上的硬性成功标准：

- 静默错误率低于 1%；
- 人工负载低于 30%。

除非有真实 AP 业务流程、付款风险或客户 SLA 支持，否则它们只能是一个 **业务场景目标**，不是项目成功与失败的自然分界线。

Agent 应优先判断 InvoiceLoop 是否相对 raw DWS 实现了以下至少一种：

1. 在相同人工负载下，静默错误更低；
2. 在相同静默错误水平下，自动化覆盖更高；
3. 同时降低静默错误和人工负载；
4. 将人工从“检查所有字段”转变为“只检查真正高风险字段”。

如果只是移动一个 confidence threshold，在风险—覆盖曲线上没有优于简单基线，E 项通常不应超过 **11/20**。

### 防止指标作弊

以下方案不能算高可靠性：

- 所有文档都送人工，因此静默错误为零；
- 所有字段都拒绝，因此没有错误放行；
- 所有文档都自动接受，因此自动化率为 100%；
- 只展示成功样本；
- 在同一批测试文档上反复调整阈值；
- 将 DocILE ground truth 用于运行时规则；
- 不使用官方 evaluator，却将自定义字符串匹配结果称为“DocILE benchmark score”。

如果没有按照 DocILE 官方预测格式、bbox matching 和 evaluator 运行，应使用：

> “DocILE-derived evaluation on selected fields”

而不是：

> “Official DocILE benchmark score”。

---

## F. 风险路由与 Human-in-the-Loop｜13 分

| 子项 | 分值 | 满分标准 |
|---|---:|---|
| 字段重要性与风险策略 | 4 | 金额、币种、税号等高风险字段采用不同于低风险字段的处理规则 |
| 不只依赖原始 confidence | 3 | 结合金额恒等式、日期逻辑、税额关系、字段缺失、模式分歧或来源质量 |
| 文档内复核体验 | 3 | reviewer 能看到原始页面和对应高亮，而不是只看一张 JSON 表 |
| 修改、批准与失败回退 | 2 | 人工修改有记录；无法确认时能够保持 unresolved，而不是强制猜测 |
| 防止 review-all | 1 | 有证据表明系统确实减少了无价值人工查看 |

Nutrient 官方对 governed document AI 的描述正是：每个字段携带 confidence 和 source grounding，高置信结果可以流转，低置信结果进入人工队列；人工应在真实文档上下文中查看和修正。

### 满分行为示例

对于一张发票：

- `supplier_address` 置信不足，但不影响付款，可以允许低优先级复核；
- `total_amount` 与 line-item sum 不一致，即使 DWS confidence 较高，也必须进入人工；
- `currency` 缺失但金额存在，系统不得默认为 USD 后静默放行；
- reviewer 点击风险字段后，原发票对应位置被高亮；
- 修改后必须明确点击 approve，而不是编辑即自动批准。

---

## G. 审计、来源与可回放性｜10 分

| 子项 | 分值 | 满分标准 |
|---|---:|---|
| 原始输入和 DWS 输出 | 2 | 保存 document ID/hash、DWS request mode、原始 response 或可信引用 |
| 策略与版本 | 2 | 保存 threshold、policy version、schema version、代码或模型版本 |
| 字段来源证据 | 2 | 最终值能追溯到 page、bbox、citation 或明确人工来源 |
| 决策和人工修改 | 2 | 记录为什么自动放行/升级/复核，以及谁修改了什么 |
| 回放与最终导出 | 2 | 能从冻结输入和配置重建判断，最终导出与审计记录绑定 |

理想的单字段记录至少类似：

```json
{
  "document_hash": "...",
  "field": "total_amount",
  "dws_raw_value": "1,280.00",
  "normalized_value": 1280.0,
  "dws_confidence": 0.7,
  "source_page": 1,
  "source_bbox": [0.61, 0.78, 0.81, 0.83],
  "policy_version": "invoice-risk-v0.3",
  "decision": "human_review",
  "reason_codes": [
    "TOTAL_LINE_ITEM_MISMATCH",
    "CRITICAL_FIELD"
  ],
  "human_action": {
    "action": "corrected_and_approved",
    "previous_value": 1280.0,
    "final_value": 1230.0
  }
}
```

“记录当前最终 JSON”不等于审计；审计必须保留 **原始结果、决策规则、修改过程和最终结果之间的关系**。

---

## H. 创新性与差异化｜5 分

| 子项 | 分值 | 满分标准 |
|---|---:|---|
| 不只是 extraction wrapper | 2 | 价值来自可靠性控制层，而不是简单给 DWS 加一个 UI |
| 可推广的 trust architecture | 2 | 方案可以扩展到 receipts、purchase orders、claims 或其他文档 |
| 有明确技术/产品洞察 | 1 | 例如证明“confidence 不是最终决策，风险应由字段重要性与经验错误率共同决定” |

如果核心功能只是：

> 上传 PDF → 调 DWS → 显示 JSON

通常不超过 **1/5**。

如果核心功能是：

> DWS 提供结构和来源 → InvoiceLoop 校准风险 → 针对关键错误进行升级或人工确认 → 形成完整审计链

则有资格获得高分。

---

## I. 提交材料与演示表达｜7 分

| 子项 | 分值 | 满分标准 |
|---|---:|---|
| 官方材料齐全 | 2 | 项目名、一句话 pitch、public repo/shared link、setup instructions、DWS heavy-lifting 说明 |
| 2–4 分钟端到端 demo | 3 | 实际上传并运行，而非只放 slides 或截图 |
| 同时展示 clean 与 risky case | 1 | 一个自动放行，一个被拦截并人工修正 |
| 指标诚实且易懂 | 1 | 不堆 benchmark 数字，清楚展示“少错多少、少看多少、为什么可信” |

官方 Nutrient submission 明确要求 2–4 分钟的 working end-to-end demo。

### 建议的视频结构

**0:00–0:20：问题**

> Invoice extraction is often almost right. In accounts payable, one silent error can be more expensive than dozens of manual reviews.

**0:20–0:45：产品闭环**

展示 upload → DWS → InvoiceLoop risk decision。

**0:45–1:20：clean case**

清楚展示自动放行及来源定位。

**1:20–2:10：risky case**

展示一个高 confidence 但金额逻辑不一致，或低 confidence 的关键字段，被正确送到 reviewer。

**2:10–2:40：人工修改与审计**

显示原文高亮、修正、批准和 audit trail。

**2:40–3:10：证据**

只展示最重要的风险—覆盖结果：

- raw DWS；
- simple threshold；
- InvoiceLoop；
- silent failure；
- automation coverage；
- review load。

**3:10–3:30：DWS heavy lifting**

明确说 DWS 做了什么，以及 InvoiceLoop 为什么不是在替代 DWS，而是在让其输出能够安全进入真实流程。

---

# 三、评分证据规则

评分 agent 必须遵守以下规则。

## 1. 只给已验证的内容计分

技术主张的证据优先级：

1. 可重复实际运行；
2. 自动测试和冻结 benchmark artifact；
3. 真实实现代码；
4. 截图或录屏；
5. README 声明；
6. TODO、roadmap 和计划。

建议计分上限：

| 证据状态 | 单个技术子项最多获得 |
|---|---:|
| 可重复运行并有输出 | 100% |
| 代码、测试和结果齐全，但 agent 环境无法重跑 | 80% |
| 有实现代码但没有测试或运行证据 | 60% |
| 只有 README、截图或口头声明 | 40% |
| 只有计划或 TODO | 0% |

商业和产品维度可以使用访谈、流程图和明确的用户假设作为证据，不要求必须写在代码里。

## 2. 不重复计分

同一项证据不能同时充当：

- DWS 深度；
- 可靠性改进；
- Human-in-the-Loop；
- 审计能力；

四项的完整证明。

例如，保存 DWS confidence：

- 可以证明使用了 DWS 输出；
- 但不能自动证明路由正确；
- 更不能证明人工负载下降；
- 也不能证明整个流程可回放。

## 3. 明确区分状态

每项功能必须标记为：

- `IMPLEMENTED_AND_VERIFIED`
- `IMPLEMENTED_NOT_RUN`
- `CLAIMED_ONLY`
- `PLANNED`
- `NOT_FOUND`
- `CONTRADICTED`

不能把 “planned” 写成 “partially implemented”。

---

# 四、内部评分上限

这些不是官方取消资格规则，而是为了防止 agent 被漂亮 README 或 UI 误导。

| 缺失项 | 最终分上限 |
|---|---:|
| 无真实端到端运行 | 59 |
| 无 held-out 评测，或没有 raw DWS baseline | 69 |
| 无任何人工异常处理路径 | 74 |
| 无可验证的审计轨迹 | 84 |
| 官方提交材料不完整 | 89 |

多个上限同时触发时，取最低值：

```text
final_score = min(raw_score, all_applicable_score_ceiling)
```

G1 或 G2 失败不使用普通上限，而是分别标记为 `INELIGIBLE` 或 `INVALID`。

---

# 五、分数解释

| 最终分 | 内部含义 |
|---|---|
| 90–100 | Submission-ready；具备 sponsor winner 级别的完整证据 |
| 80–89 | Strong contender；产品和证据都强，但仍有一项明显缺口 |
| 70–79 | Credible submission；核心成立，但可靠性、审计或演示不完整 |
| 60–69 | Working prototype；有真实实现，但尚未证明“可信” |
| 40–59 | Fragmented demo；部分组件完成，缺少闭环 |
| 0–39 | 不满足挑战核心，或几乎无法验证 |

这只是项目成熟度分档，**不是获奖概率预测**，因为无法得知其他参赛项目的质量和 sponsor 最终偏好。

---

# 六、可直接交给评分 agent 的 Prompt

```text
SYSTEM — InvoiceLoop Evidence-Bound Hackathon Judge v0.1

你是 InvoiceLoop 项目的证据约束型黑客松评委。

InvoiceLoop 参加 Nutrient DWS Challenge。你的任务不是鼓励开发者，也不是根据 README
复述项目，而是针对一个固定 commit 和一组冻结提交材料，判断当前项目是否真正实现了：

1. 有意义的 Nutrient DWS 核心集成；
2. 相比原始 DWS 更低的业务关键静默错误；
3. 在可靠性和人工负载之间取得可证明的改进；
4. 只在必要时引入人工，并为人工提供原文来源；
5. 保存可解释、可追溯、可回放的处理记录；
6. 形成可运行、可展示、可落地的产品闭环。

你必须使用以下评分维度：

A. 真实问题与项目概念：10
B. 项目进展与端到端执行：12
C. 落地与创业可行性：8
D. Nutrient DWS 集成深度：15
E. 可靠性改进与实验证据：20
F. 风险路由与 Human-in-the-Loop：13
G. 审计、来源与可回放性：10
H. 创新性与差异化：5
I. 提交材料与演示表达：7

总分 100。

评审协议：

1. 只评估指定 commit，不使用更晚的分支或未提交修改。
2. 先检查资格门，再评分。
3. 技术主张必须引用 repo path:line、测试名称、benchmark artifact、
   运行日志或 demo timestamp。
4. README 与代码冲突时，以可运行代码和测试结果为准。
5. TODO、roadmap、未来计划不计实现分。
6. 不允许同一项证据在多个维度重复获得完整分数。
7. 没找到证据时写 NOT_FOUND，不得根据文件名或架构图推断功能存在。
8. 无法运行不等于运行失败，但必须标记 IMPLEMENTED_NOT_RUN，并限制证据分。
9. 检查 benchmark 是否存在数据泄漏：
   - 测试标签不得参与阈值选择；
   - 测试文档不得用于 prompt、schema 或规则调优；
   - 不得在测试集上反复寻找最佳阈值后报告同一测试结果。
10. 除非使用 DocILE 官方预测格式与 evaluator，否则不得称为
    official DocILE benchmark score。
11. 不得因为系统将全部文档送人工而给予高可靠性分。
12. 不得因为系统全部自动接受而给予高自动化分。
13. 重点判断 InvoiceLoop 相对 raw DWS 或 simple confidence threshold
    是否实现风险—覆盖上的 Pareto improvement。
14. 所有分数必须是整数，并逐项说明扣分原因。
15. 应用所有适用的 score ceiling，最终分为 raw score 与最低 ceiling 的较小值。

资格门：

G1 DWS 是否承担核心文档操作。
G2 是否存在伪造指标、硬编码结果或测试标签泄漏。
G3 是否有真实端到端运行。
G4 是否有 repo/shared link、setup、2–4 分钟 demo 和 DWS heavy-lifting 说明。
G5 是否清楚披露比赛前已有代码和比赛期间新增代码。

输出时不要使用模糊评价，例如“不错”“较强”“有潜力”。
必须给出可验证证据、精确分数、关键缺口和最高 ROI 的下一步。
```

---

# 七、建议的机器可读输出格式

```json
{
  "rubric_version": "invoiceloop-hackathon-v0.1",
  "evaluated_commit": "",
  "artifacts_reviewed": [],
  "eligibility": {
    "G1_dws_core_use": {
      "status": "PASS",
      "evidence": []
    },
    "G2_evidence_integrity": {
      "status": "PASS",
      "evidence": []
    },
    "G3_end_to_end_run": {
      "status": "PASS",
      "evidence": []
    },
    "G4_submission_completeness": {
      "status": "PASS",
      "evidence": []
    },
    "G5_timeline_compliance": {
      "status": "REQUIRES_HUMAN_CONFIRMATION",
      "evidence": []
    }
  },
  "scores": {
    "A_problem_and_concept": {
      "score": 0,
      "max": 10,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "B_progress_and_execution": {
      "score": 0,
      "max": 12,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "C_feasibility": {
      "score": 0,
      "max": 8,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "D_dws_integration": {
      "score": 0,
      "max": 15,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "E_reliability_evidence": {
      "score": 0,
      "max": 20,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "F_risk_routing_and_hitl": {
      "score": 0,
      "max": 13,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "G_audit_and_replay": {
      "score": 0,
      "max": 10,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "H_innovation": {
      "score": 0,
      "max": 5,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    },
    "I_submission_and_demo": {
      "score": 0,
      "max": 7,
      "status": "NOT_FOUND",
      "evidence": [],
      "deductions": [],
      "missing_for_full_score": []
    }
  },
  "round_proxies": {
    "overall_round": {
      "score": 0,
      "max": 30
    },
    "nutrient_sponsor_round": {
      "score": 0,
      "max": 63
    },
    "submission_quality": {
      "score": 0,
      "max": 7
    }
  },
  "raw_total": 0,
  "applicable_score_ceilings": [],
  "final_total": 0,
  "verdict": "NOT_READY",
  "verified_strengths": [],
  "critical_gaps": [],
  "unverified_claims": [],
  "benchmark_integrity_findings": [],
  "highest_roi_actions": [
    {
      "priority": 1,
      "action": "",
      "expected_point_gain": 0,
      "reason": ""
    }
  ]
}
```

---

## 最终建议

这份 rubric 应当在 agent 看 repo **之前冻结**。后续可以根据 repo 事实打分，但不要因为项目当前恰好做了某项功能，就提高那一项权重；也不要因为某项尚未实现，就事后降低其重要性。

尤其要冻结以下三条：

1. **Raw extraction accuracy 不是最终目标。**
2. **0 个观察错误不等于已经证明低于 1% 的真实错误率。**
3. **真正的成功是相对基线改善风险—覆盖曲线，而不是恰好跨过一个预先拍出的 1%/30% 门槛。**
