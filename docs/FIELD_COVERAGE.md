# 记分字段集覆盖声明(SEALED-2 之前冻结,2026-08-06)

rubric 建议的关键字段里有四个不在我们的记分集:currency、buyer_tax_id、
purchase_order_number、payment/bank details。本文件在**下一批封箱评测
之前**声明它们缺席的原因(事后补声明 = 挑字段,评审裁决的原文警告)。

## 记分字段怎么来的(不是看结果挑的)

十个记分字段(invoice_number / issue_date / due_date / seller_name /
seller_vat_id / buyer_name / total_net / total_vat / total_gross /
amount_due)在 dws-derisk 六轮实验**第一轮之前**预注册冻结
(`run_batch.sample` 的 wanted 集合,提交记录可查),选判据是
「AP 付款决策依赖 + DocILE 有标注可判」。InvoiceLoop 原样继承,
从未根据任何实验结果增删。

## 四个建议字段缺席的事实(全语料 5,680 份实测,2026-08-06)

| rubric 建议字段 | DocILE 对应 | 实测状态 | 结论 |
|---|---|---|---|
| currency | `currency_code_amount_due` | 1,054 份有该标注**键**,但全部 5,680 份中**非空值为零** | 无可判真值,记分不可定义 |
| buyer_tax_id | (无此 fieldtype) | DocILE 标注体系里不存在买方税号字段 | 无真值来源 |
| purchase_order_number | (无此 fieldtype;`order_id` 是订单/合同号,语义不同) | 同上 | 无真值来源 |
| payment / bank details | `account_num` / `bank_num` | 标注键存在(52/39 份),但全部 5,680 份中**非空值为零** | 无可判真值 |

**结论:这四个字段不是「被判为不重要」,而是「在本语料上无真值可判」。**
评分系统的硬纪律是「没有真值就不进错误率」—— 把它们加进记分集只能
产出伪指标(把「没有标注」算成「抽错」或「抽对」都是编造)。

## 产品层与记分层的区分

- **记分层**(H 系指标、基线表):只含上述 10 字段,理由是上表;
- **产品层**:抽取 schema 是数据驱动(`ingest.FIELD_DESCRIPTIONS`),
  租户要加 currency/PO/银行字段只需加 schema 行 + 提供真值集 —— 
  冻结、门禁、绑定、路由、审计机制与字段无关,全部照转;
- **已知关联限定**:`seller_vat_id` 的字段语义在美国语料上是预期缺失
  (2026-08-06 HITL 实测 + absent_expected cohort),且存在
  Fed. I.D. → seller_vat_id 的系统性错误映射风险(一份实测 reject,
  心码 WRONG_FIELD_MAPPING)—— 该字段的描述文字(EN 16931 口径)
  与美国语料现实有张力,任何修订走下一批的资格流程。

## 若换语料

在真值覆盖这些字段的语料上(如欧洲 VAT 发票、带银行字段的企业 AP
数据),字段集应该扩,扩法 = 预注册新字段 + 新封箱集,不回溯改本声明。
