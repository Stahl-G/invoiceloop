# 预注册:agent 裁决 vs 人工裁决(2026-08-08,执行前冻结)

**本文件的首次提交即冻结点。看到任何一臂的结果之后再改本文,该臂作废。**

## 0. 问题

改进循环的挖掘臂(`improve.mine`)吃的是**人工裁决事件**。到今天为止,
它一共只吃过 346 条(`runs/hitl-sealed`,12 份文档)。

问:**在同一批复核槽上,ADK agent 的裁决能不能代替人的裁决作为挖掘输入?
代价是多少?**

这不是要把自动裁决放进产品 —— 模型自己提案、自己签字是把监督闭合在
自己身上(理由见 `invoiceloop/doctype.py` 模块文档对 `invoice_type` 的
同一条论证)。这是**把它作为对照臂测出代价**,数字照登。

## 1. 为什么用 SEALED-2 挖、用 SEALED-1 的 88 份评

- SEALED-2 的留出资格已于 2026-08-07 撤销(`docs/SEALED2_RESULTS.md`),
  现在是**开发集** —— 在它上面挖 cohort 是它的合法角色;
- 它的 100 份文档 **一条人工裁决都没有**
  (`runs/sealed2/adjudication_ledger.jsonl` = 0 行),是块干净的空地;
- 评估集用 SEALED-1 的 88 份从未人工接触的文档 —— 与挖掘集**不相交**,
  且与 2026-08-06 的泛化实验同一个集合,数字可直接对照
  (`docs/LOOP_GENERALIZATION_2026-08-06.md`);
- **SEALED-3 全程不参与。** 本实验零 DWS 调用。

> ⚠ **口径提醒**:`runs/sealed2` 跑的是 **HAR-0004**,里面已经含了 12 份
> HITL 挖出的两个缺席 cohort。所以本实验测的是「在 HAR-0004 之上再挖一轮」
> 的**边际**收益,**不能**与 2026-08-06 那个 63.7% → 55.1%(HAR-0001 起步)
> 直接比大小。主对照是 **TA vs H2**,不是 TA vs 历史。

## 2. 抽样(先于任何裁决)

- 池:`runs/sealed2/support_matrix.json` 中 `route == "review"` 的 **468** 槽;
- 槽键:`f"{doc_id}|{field}"`;
- 抽样:`random.Random("invoiceloop-arm-v1|" + seed).sample(sorted(keys), 200)`;
- 随机源:drand 主网 beacon,**轮次 6356437**,种子 =
  `08b6c717dc07a6628986c48d4ad0c9b784fd53270bc7bb3ce36d233333c6e082`
  (该轮 `randomness` 原文,取种 UTC 2026-08-08);
- 名单落盘 `docs/arm_slot_sample.json`,**单独 commit,先于任何裁决**。

### 池的构成(抽样前记录,防止事后说样本挑过)

| 维度 | 分布 |
|---|---|
| 空值 / 有值 | 157 / 311 |
| support_strength | unsupported 233 · corroborated 226 · single_source 9 |
| 字段 | due_date 89 · total_net 65 · total_vat 51 · amount_due 50 · total_gross 50 · buyer_name 46 · seller_name 34 · invoice_number 34 · issue_date 27 · seller_vat_id 22 |
| 含 QA 探针 | 24(`QA_SAMPLE:*`)—— `mine` 按设计排除,预期抽中约 10 |

均匀随机,**不分层**。分层会让人怀疑分层依据是照着想要的结果选的。

## 3. 两臂(同一批 200 槽,互盲)

| 臂 | 裁决者 | 工作区 |
|---|---|---|
| **TA** | ADK / Gemini agent | `runs/arm-ta` |
| **H2** | 用户本人(workbench) | `runs/arm-h2` |

**同一批槽**是关键:配对设计才能直接量「同一个槽上两者判得一样吗」,
两批不同的槽只能比总体分布。

### 两臂看到的东西必须完全相同

每个槽给一份 slot pack,内容:

- 整页渲染 PNG + bbox overlay(`span_ids` 冻结绑定 / `cited_span_ids` DWS 指向,
  与 workbench 左栏同一套颜色纪律);渲染走 `evidence.render_pages`,零 API;
- 槽位事实:`value`、`support_strength`、`source_tiers`、`applicability`、
  `limitations`、`gate_verdicts`、`reason_codes`、`blocking_findings`。

**两臂都看不到**:DocILE 真值、对方的裁决、本文件的预测节。

### 单一写者(宪章一)

agent 只输出**裁决草稿**:`decision` / `reason_code` / `rationale` /
`reviewer_confidence`,**不含任何 ID**。Python 调
`adjudicate.append_adjudication` 分配 `decision_id` / `seq` 并冻结账本 ——
与人走同一个写入口、同一套组合自洽校验。
`adjudicator` 字段记 `agent:<model>@<version>`,永不与人混淆。

agent 弃权按 `abstain` 如实记录,**不许丢**(宪章四)。

## 4. 裁判

DocILE 真值,口径与 `heldout_metrics.truth` 完全一致。

真值是**裁判**,不是任何一臂的输入 —— 两臂都是在看不到真值的情况下判的。

## 5. 预注册度量

| # | 量 |
|---|---|
| M1 | TA vs 真值:按决策类型的一致率 |
| M2 | H2 vs 真值:按决策类型的一致率(**这是本项目第一次量人自己的错误率**) |
| M3 | TA vs H2:配对一致率 + 6×6 混淆矩阵 |
| M4 | 两臂各自 `improve.mine` 产出的 cohort(数量、类型、字段) |
| M5 | 下游:两臂各自晋升后的策略回放到 88 份 → 复核负载 + 静默错,以 HAR-0004 为基线 |

M5 的晋升决策各按各的规矩:TA 臂由 **ADK critic** 决定,H2 臂由**人签字**。

## 6. 预注册预测(现在写死;错了照登)

- **P1** TA 能产出 `total_vat` 型 `confirm_absent` cohort,但 **`not_applicable`
  裁决占比 < H2 的一半** —— 真值和页面都只说明「这一份有没有」,
  「这一类单据没这个概念」是宪章五划给人的判断。
- **P2** TA 臂下游的缺席静默错率 **> 3.5%**(H 臂 2026-08-06 实测值)。
- **P3** TA vs H2 在 `accept` 上一致率 **≥ 80%**,在
  `not_applicable` / `abstain` 上 **< 40%**。
- **P4** TA 臂经 ADK critic 进入 promote 的候选数 **>** H2 臂经人签字的候选数。

## 7. 作废条件

- 看到任一臂结果之后修改 agent prompt / 判据 / 抽样 → **该臂作废**,
  换新 drand 轮次重抽;
- 用户在完成 H2 之前接触到 TA 的任何裁决内容 → **H2 作废**(锚定污染);
- 两臂槽位集合不一致 → **全实验作废**;
- 本实验的任何结论都**不得**用于修改产品默认策略,除非另走 promote 人签字。

## 8. 盲法执行纪律(约束的是我,不是代码)

用户指定 **TA 先跑**。因此在 H2 完成之前:

1. TA 的结果只公布 **ledger 的 sha256 与条数**,不公布任何一条裁决内容;
2. 我在对话里**不得**引用 TA 的任何具体裁决、决策类型分布、字段分布,
   也不得作「agent 觉得这类多半是缺失」这类概括 —— 那等于把答案递过去;
3. H2 的 workbench 页面不得可达 `runs/arm-ta` 的任何文件;
4. H2 完成、账本冻结后,一次性开封,写 `docs/ARM_AGENT_VS_HUMAN_RESULTS_*.md`。

第 2 条最容易在闲聊里破。破了就照登破了,不假装没破。

## 9. 成本

- DWS:**0**(SEALED-2 的 200 次响应 2026-08-06 已付,存盘可复用);
- Gemini:200 次 flash 调用(每次一张页图 + 一段槽位事实);
- 人:用户 200 槽。
