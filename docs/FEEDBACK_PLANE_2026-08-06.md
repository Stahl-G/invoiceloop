# 反馈平面修订(2026-08-06):让挖掘臂第一次有可能点火

冻结基线是 `IMPROVE_LAYER_V0.2_DESIGN.md`。本文件按项目纪律
(**先说、给依据、写进文档,不静默改判据**)登记四处改动,其中一处是
**放松既有质量门** —— 那条门是 83 评问题三加进来的,放松它必须留痕。

## 0. 触发这次修订的实测

`runs/hitl-sealed` 的 run-0002(123 条真人裁决)之后跑 `improve mine`:

```
events 75 · actionable 0 · qualified_for_mining 0
cohorts [] · low_yield_candidates [] · absence_candidates []
not_actionable: no_reason_code 69 · low_or_no_confidence 75
```

**挖掘臂产出为零,一次都没点火过。** 而同期落地的 `absent_expected`
cohort(PROM-0002)是**人**读完 run-0002 报告手写的 —— rationale 字段
就是一段引用报告的散文。也就是说:改进循环里被端到端验证的是
harness 版本化 + 晋升 + 回滚 + QA 探针 + 反事实评估;
「从人工裁决里自动学」这条臂从未运行。

根因有两条,一条是判据太严,一条是**信息压根没送进来**。

---

## 1. 把握度退出合格门(放松,需留痕)

**改前**:`actionable = 心码 ∧ reviewer_confidence ∈ {high, medium} ∧ 非弃权`
**改后**:`actionable = 心码 ∧ reviewer_confidence ≠ "low" ∧ 非弃权`

**依据(不对称性)**:

- 人**主动**标「没把握」是真信息,该听 → 保留出局;
- **未填不等于有把握**。run-0002 填写率 3/123,把未填当不合格,
  等于让一个可选字段一票否决整条臂;
- 自评把握度**从未被验证与正确率相关**。run-0002 有反例:被试在未标低
  把握的情况下填进 `105528107477215711`(形状可疑,像 OCR 涂抹段被照抄);
- 同一个风险已有**测量式**守卫:cohort 放松 20% QA 探针、
  policy_accepted TIER1 5% 抽检。用一个未验证的自评信号再守一遍,
  代价是全部事件归零,收益不明。

**未放松的部分**:心码仍是硬要求(没有心码就没有监督标签,且系统不代填);
`superseded` 与 `random_qa` 排除不变;mined cohort 仍须过
`evaluate` 反事实 + 人工 `promote` + QA 探针。**质量门从来不是唯一守卫,
这也是可以松它的原因。**

口径变更:`mine_report.buckets.not_actionable_reasons` 的
`low_or_no_confidence` 改名 `low_confidence`,只数主动标低的。
**不回溯重算任何已发布数字。**

## 2. 别把同一件事问两遍(UX,非判据)

`adjudicate.py` 的 combo 表本来就规定心码与裁决不独立:
`CONFIRMED_ABSENT ⟺ confirm_absent`、`NOT_APPLICABLE ⟺ not_applicable`。
对这两类裁决再问心码,是让人把刚点的东西重打一遍
(run-0002:此类占 30/123 = 24%)。

- **快路按钮自带心码**,只在语义一对一时带:确认缺失→`CONFIRMED_ABSENT`、
  采用被拒草稿→`BAD_SOURCE_BINDING`;
- **accept 拆两键**:「确认正确」不带码(词表里没有「路由判对了」,
  它也不构成放松证据);「而且这条不该进队列」→`ROUTING_FALSE_POSITIVE`,
  这是挖掘低收益 cohort 唯一需要的信号。是两个按钮,不是一个新表单字段;
- **问题 chip 同规则**:值不对→`WRONG_VALUE`、位置不对→`BAD_SOURCE_BINDING`、
  看不清→`AMBIGUOUS_DOCUMENT`、页面上没有→`CONFIRMED_ABSENT`、其他→`OTHER`;
  **「与页面一致」「口径冲突」留空** —— applicability 争议在心码集里没有
  对应项,硬塞一个就是编。连点多个 chip 时只有第一个写码,不覆盖人手选的;
- 「采用 DWS 值(无声明)」这一支**留空**:既可能是绑定失败、也可能是
  OCR 阻断导致门禁 unavailable,机器分不出来就不替人选。

**这条改动是前瞻性的。** 历史裁决的 `reason_code` 仍是空的
(115/123),run-0002 的数据解锁不了 —— 实测新门下 `qualified 0 → 7`、
`cohorts 0 → 5`,不是 0 → 117。第一次有真正产出的是下一轮。

## 3. 复核者的原话必须进得来(补漏)

`feedback.py` 此前**根本没有把 `rationale` 带进反馈事件** —— 那段必填的
自由文本停在裁决账本里,改进层看不见。现在:

- 事件带 `rationale`(原文,不解析);
- `mine` 按 cohort 归堆成 `notes`,`absence_candidates` 同样带。

**纪律:原文透传,机器不从中提取特征。** 自由文本 → 策略需要模型,
而 `gates.py` 首行是「全部确定性,不调模型」。这一栏是给**写提案的人**读的
—— 上一条 cohort 本来就是人读报告手写的,这里只是把「要读什么」
从 123 行账本收敛到「这个 cohort 里大家究竟说了什么」。

实测立刻有东西(runs/hitl-sealed):

- `total_gross`:「与页面一致,2371.95 和 $2371.95 不应该不同,下次记住」
  —— 规范化缺陷报告,此前对 harness 完全不可见;
- `seller_vat_id`:「美国发票的 Fed. I.D. 是 EIN 不是 VAT 号」,
  挂在一个 **`route: auto_accept` 却被 `reject`** 的槽上。

## 4. 撤销信号:auto_accept 被人推翻(收紧,新增)

`mine_report.overturned_auto_accepts`:路由是 `auto_*` 且人做了
`correct`/`reject` 的槽。

**方向与前两类相反** —— `low_yield` / `absence` 是放松线索,这一类是
**收紧证据**,所以不进 candidates,单列,且**一条就报,不设频次门槛**。
放松要证据、收紧要及时,不对称是故意的(宪章四:安全方向优先)。
QA 探针抓到的推翻**照样计入** —— 探针存在的理由就是抓这个,
不能因为它是随机抽的就不算数。

## 5. 顾问层 `suggest`(模型读笔记出草稿)

**位置**:刻意**不在** `improve` 之下。改进控制面四个子命令仍是
全确定性零模型;`suggest` 旁挂,与 `vision` 同款 —— 模型只写草稿文件
(`improve/suggestions.json`,无 ID、无策略、不进账本),
采纳与否由人在工作台读完原话与草稿后决定,之后仍走
`propose → evaluate → promote` 与 QA 探针。**差别全在谁签字。**

草稿写入前逐条校验(`suggest.validate`,纯函数、不碰网络、可单测):

| 判据 | 拒的理由 |
|---|---|
| `action ∈ {auto_accept, absent_expected, revoke}` | 别的动作不收 |
| cohort 键 ⊆ {field, tier, strength} | 出现 doc_id / 期望值 = 绕过 routing 的 cohort 白名单 |
| `cites` 非空且下标在笔记表内 | **没出处的建议就是模型的意见,不是从证据来的** |
| confidence ∉ {high,medium,low} → 降级 low | 不接受自造档位 |

工作台 `/improve` 页(**只读**):收紧信号排最前,复核者原话是主体,
模型草稿打 `advisory` 标、挂着它引用的原话、被丢弃的草稿也显示。
页面底部给的是**一条可复制的 propose 命令**,不是按钮 ——
唯一写 active 的入口必须是 `improve promote`(v0.2 §12),
网页上一个按钮能改策略,那道人工闸门就是摆设。

---

## 6. 下一轮的验收判据(先写后做)

1. **挖掘臂自己独立找出 `seller_vat_id` 的 absence 候选** —— 让它重新发现
   一条人已经手写过的规则。答案已知,这是检验它对不对最干净的测试;
2. 终点用**时间**不用槽数:run-0002 实测 seller_vat_id 中位 90s/槽、
   占全部人工时间 18.6%,而 `total_gross` 只要 14s —— 槽数把两者算成一样;
3. **挖掘集与评估集分开**:这 12 份已被 run-0002/0003 污染,只能当回归集;
4. **一次只动一个变量**:run-0003 同时改了策略并首次打开读图,
   路由层 −3 混着两个原因,这次不许再犯;
5. 模型草稿的**采纳率与被校验层丢弃率**要如实登记 —— 若丢弃率长期很高,
   说明顾问层在编,该退役而不是调 prompt 迁就它。
