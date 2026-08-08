# SEALED-3 多 harness 封箱结果（2026-08-08，一次开箱，数字照登）

协议：`docs/SEALED3_PROTOCOL.md`；结果前附录与机器计划：
`docs/SEALED3_MULTIHARNESS_ADDENDUM_2026-08-08.md`、
`docs/sealed3_multiharness_plan.json`。开箱 revision：
`447acf0699d7815fcd69ba8d9922feaf569f65aa`。

## 结论先行

1. **排序能力复现**：主臂 HAR-0004 的 H1 lift 为 **3.75×**，H1–H4、
   H6、H7 通过；H5 citation 失败率 **15.35%**，略高于 `<15%` 线，照登 FAIL。
2. **人工队列下降**：HAR-0004 相对保守 HAR-0001 从 **624/1000
   (62.4%) 降至 527/1000 (52.7%)**，少 97 槽（−9.7pp），文档触达
   100/100 → 99/100。
3. **但 SEALED-3 资格失败**：P1 要求两类静默错均不升。HAR-0004 的
   `silent_absent` 为 **1**，HAR-0001 为 **0**；`silent_wrong` 同为 59。
   P1 因 1 个静默缺席失败，P2 通过。**不写 sealed3_qualified 标记，
   不得宣称 HAR-0004 已在未见集上“减负且静默错不升”。**
4. **ADK due_date 候选不得晋升**：HAR-0007 再省 33 槽（−3.3pp），却比
   HAR-0004 多 **5 个**静默缺席；自动 promotion 会把真实到期日静默丢掉。
5. **人类裁决准确率仍是 NOT MEASURED**：本次只完成零人工、零新 DWS、
   零新 ADK 的确定性工作量与真值安全评测；未完成的人类臂以后单独完成。

## 1. 执行与封缄

- 100 份 × understand/agentic 均使用已经存盘的 SEALED-3 证据；本次
  **DWS 调用 0、ADK 调用 0**。
- 七臂在一个批事务中完成；`batch_complete.json` 产生前未读中间结果。
- 三个批不变量全部通过：同一 input fingerprint、同一上游 artifact/ledger/
  spans、HAR-0004 精确重复臂全部 run 工件逐字节一致。
- input fingerprint：
  `63357ff37366c4e8375e9d0a9120ac169e21c761bf2e0bdfe3f3a79041699e9c`。
- batch complete sha256：
  `e54552f5f34a183ccc392bc31878ae15cd6c6588b5848e73e79e58fd6e486eef`。
- metrics sha256：
  `687caa608c00e71850d5f29716d2aa79886af4e7695dd052e281759eaa6ed1f6`。
- 主臂 field ledger：1277 claims，账本内 digest
  `158e8ad3ad83b3c036609b5f4e64924748141c74607a9468e42db9aa5a9be215`。
- 主臂 audit bundle：416 members，sha256
  `6b2d4d1ff679598f9861c80b77fa933d54b474c66790c65eff55cdc38497a3c9`；
  members/snapshot/semantics 全过，空裁决所以 binding=None，未做 DWS
  signature sealing（不影响预注册 H7 的四层 verify）。

## 2. 主终点 H1–H7（P = HAR-0004）

| # | 量 | SEALED-1 | SEALED-2（资格后撤销） | **SEALED-3** | 区间 | 判定 |
|---|---|---|---|---|---|---|
| H1 | 分诊 lift | 4.03× | 3.19× | **3.75×** | > 1.5 | **PASS** |
| H2 | coverage@46% | 77.3% | 75.2% | **77.33%** | > 55% | **PASS** |
| H3 | 历史 requires 口径复核召回 | 77.7% | 72.0% | **76.11%** | > 55% | **PASS** |
| H4 | extraction_present 缺失率 | 29.3% | 12.8% | **16.10%** | 10–45% | **PASS** |
| H5 | citation 可判子集失败率 | 15.3% | 13.6% | **15.35%** (62/404) | < 15% | **FAIL（照登）** |
| H6 | understand 冻结拒绝率 | 36.6% | 34.6% | **34.41%** (331/962) | 5–35% | **PASS** |
| H7 | 运行闭环 | PASS | PASS | **bundle verify PASS** | run + verify | **PASS** |

记分槽 574，偏差 247；队首一半偏差率 67.94%，队尾一半 18.12%。H5
再次落在长期约 15% 的边界上，不得说 citation 已经修好；H6 回到区间内也
不得解释成抽取准确率提升。

## 3. 多 harness 工作量与安全结果

`human_queue` 是对外人工队列口径：route 不是 auto_accept/auto_absent。
`silent_absent` 与 `silent_wrong` 使用同一 DocILE truth scorer；分母分别是
auto_absent hits 与有真值可判的 auto_accept value hits。

| arm | human_queue | requires（含 auto_absent） | 文档触达 | auto_absent | silent_absent | silent_wrong |
|---|---:|---:|---:|---:|---:|---:|
| B0 HAR-0001 | 624 (62.4%) | 624 | 100/100 | 0 | 0/0 | 59/320 |
| B1 HAR-0002 | 632 (63.2%) | 632 | 100/100 | 0 | 0/0 | 57/314 |
| B2 HAR-0003 | 572 (57.2%) | 643 | 100/100 | 71 | **1/71** | 58/306 |
| **P HAR-0004** | **527 (52.7%)** | 633 | **99/100** | 106 | **1/106** | 59/312 |
| A1 HAR-0006 (ADK) | 531 (53.1%) | 632 | 100/100 | 101 | 1/101 | 58/313 |
| A2 HAR-0007 (ADK) | **494 (49.4%)** | 637 | 100/100 | 143 | **6/143** | 59/310 |

精确重复臂 P-repeat 与 P 的上述数字及全部 run tree bytes 均相同。

### 配对差（candidate − baseline）

| 比较 | Δ human_queue | Δ silent_absent | Δ silent_wrong | 结论 |
|---|---:|---:|---:|---|
| HAR-0002 − HAR-0001 | +8 (+0.8pp) | 0 | −2 | QA 抽样成本使队列反而略升 |
| HAR-0003 − HAR-0002 | −60 (−6.0pp) | **+1** | +1 | seller VAT cohort 减负但并非零风险 |
| HAR-0004 − HAR-0003 | −45 (−4.5pp) | 0 | +1 | total VAT cohort 继续减负 |
| **HAR-0004 − HAR-0001** | **−97 (−9.7pp)** | **+1** | 0 | **P2 PASS，P1 FAIL** |
| HAR-0006 − HAR-0004 | +4 (+0.4pp) | 0 | −1 | 重复 cohort 没有减负价值 |
| **HAR-0007 − HAR-0004** | **−33 (−3.3pp)** | **+5** | 0 | **ADK due_date 候选拒绝** |

这些是**整份 harness 的配对效果**，不能全叫“只改一个 cohort”的纯因果消融。
原因是 QA sampler 的 hash key 含 `harness_id`；HAR-0003、0004、0006、0007
换 ID 时会同时重新抽 5% / 20% QA 槽。HAR-0006 的重复 total_vat cohort
语义上没有新增字段，却仍出现 +4 槽差，正好实证了这项混杂。结果前附录只对
HAR-0006 明写了 near-placebo，没有把同一警告推广到 lineage 三臂；这是实验
设计遗漏，结果后不补臂、不换 seed，照登为限定。

## 4. P1 失败的那一个槽

唯一主臂静默缺席是：

| doc | doctype 字面证据 | 字段 | DocILE truth | DWS understand | HAR-0004 后果 |
|---|---|---|---|---|---|
| `5a34aacbc5fc49f3a09c2b06` | `rebate form` → `credit_note`，evidence pass | seller_vat_id | `27042768` | null | `auto_absent` |

这不是 `$0.00` 口径边界，而是确有 VAT/tax identifier 的非 invoice 单据。
它直接推翻“美国发票通常没有 VAT，所以所有文档的 seller_vat_id 都可预期
缺席”这一无条件规则。更重要的是：**doctype 已经正确识别它是 credit note，
但 routing policy 完全没消费 doctype**。这为下一版本提供了明确问题，不为
当前版本补答案：类别可作为 applicability 上下文/人类提问条件，但任何自动
缺席规则仍需新数据验证，不能用 SEALED-3 修完再在 SEALED-3 上复考。

HAR-0007 新增的 5 个 due_date 静默缺席均有非空真值：

- `3d8745f375c244bd9c9977e6` → `12/23/1999`
- `686fc97705a34f5987ee060b` → `11-23-2020`
- `a593b7950bf941608353fadf` → `11/27/00`
- `ca154b23196b4278ba87a3ec` → `14.03.99`
- `fedd01b20b8c48e096b7ba43` → `September 1, 2020`

所以“很多美国发票写 xx days after”不支持把 due_date 全局设为预期缺席；
恰恰相反，未见集显示有 5 个 DWS 漏抽、但真值存在的日期会被该规则静默吞掉。
若以后支持条款推导，它应是独立、可解释、带输入与适用性 gate 的业务规则层，
不能伪装成页面 span 抽取。

## 5. `decision_load_for_release` 指标实现失效（新发现，未修）

冻结 scorer 从 `deliverable.summary.decision_load_for_release` 读取该指标，七臂
全部返回 **82.8%**。但同一 `deliverable.json` 内的逐字段 status 自己证明这
不可能：HAR-0004 有 527 `pending`、367 `policy_accepted`、106
`policy_confirmed_absent`，需要人动作的应是 527，不是 828。

| harness | summary 报告值 | 按自身字段 status 复算（探索性审计） |
|---|---:|---:|
| HAR-0001 | 82.8% | 82.8%（624 pending + 204 pending_tier1） |
| HAR-0002 | 82.8% | 63.2%（632 pending） |
| HAR-0003 | 82.8% | 57.2%（572 pending） |
| HAR-0004 | 82.8% | 52.7%（527 pending） |
| HAR-0006 | 82.8% | 53.1%（531 pending） |
| HAR-0007 | 82.8% | 49.4%（494 pending） |

根因是当前 `deliver.py` 仍用 `requires_adjudication ∪ 全部 TIER1` 计数，
没有尊重 `release_tier1_explicit=false`，也把策略确认缺席的兼容
`requires_adjudication=true` 算回人工。**预注册的该列因此判为不可解释，
不能拿 82.8% 写多臂结论。**表中 status 复算只作发现缺陷的审计，不替换
预注册端点。代码与测试均不在本次结果后修改；修复进入下一版本，SEALED-3
不得用于验证修复。

## 6. doctype 描述性结果

当前门禁确实在 SEALED-3 跑了 doctype：100/100 有 `document_checks`，其中
83 pass、9 fail、4 no_claim、4 unmapped。分类为 invoice 75；其余 25 为
contract 5、credit_note 2、estimate 3、proforma 1、purchase_order 3、
receipt 3，另 8 无 class。

这复现了先前“约四分之一不是 invoice”的观察，也解释了为什么 HITL 不应让
用户每份重做类别辨认。但本版本 doctype 只提供字面证据，不改变字段按钮或
路由；本节是描述性结果，不把类别模型升级成裁定者。

## 7. 资格、候选与后续边界

- **HAR-0004：SEALED-3 qualification = FAIL**（P1 silent_absent 0→1）；
  不创建任何资格 marker。
- **HAR-0006：不晋升**；相对主臂人工队列 +4，没有减负收益，差异主要来自
  harness ID 重排 QA。
- **HAR-0007：不晋升**；−33 人工槽换来 +5 静默缺席，确定性 safety gate
  应阻断它。
- **人工裁决准确率：NOT MEASURED**；继续保留为独立的人类臂终点。
- SEALED-3 已完成它对 revision `447acf0` 的一次性测量。今后由本结果启发的
  doctype 条件规则、due-date 业务规则、QA sampler 或工作量指标修复，都只能
  使用开发/回归数据；下一次未见资格必须另抽 SEALED-4。

本次可以公开说的最强一句话是：**在开发期未见的 100 份 SEALED-3 上，
HAR-0004 的分诊 lift 为 3.75×，人工队列相对 HAR-0001 少 9.7pp；但出现 1 个
新增静默缺席，因此未通过预注册晋升门。**
