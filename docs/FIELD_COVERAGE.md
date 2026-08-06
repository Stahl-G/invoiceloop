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

## 四个建议字段缺席的事实(全语料 5,680 份实测,2026-08-06 复算修正)

(2026-08-06 外部复核抓出:本表第一版的计数取错了标注键(`value` →
应为 `text`),数字不可复算。已修正,复算脚本在文末。)

| rubric 建议字段 | DocILE 对应 | 实测(5,680 份) | 结论 |
|---|---|---|---|
| currency | `currency_code_amount_due` | 键在 4,000 份;但标注 text 普遍是裸符号 `$`,按预注册 CODE 规范化塌成 None,**非空仅 126 例**(EUR/USD 等) | 结论不变(无可判真值),理由是规范化塌缩,不是没有标注 |
| buyer_tax_id | `customer_tax_id` | 键 40 份,非空 40,但高度集中(同值重复) | 太稀有(0.7%),100 份封箱集期望 <1 例,进不了记分 |
| purchase_order_number | (无此 fieldtype;`order_id` 是订单/合同号,语义不同) | — | 无真值来源 |
| payment / bank details | `account_num` / `bank_num` | 键 135 / 105 份,**非空 135 / 105**(例 `10491969`、`052001633`) | **有真值但稀有(≈2%)** —— 100 份封箱集期望 ≈2 例,无法支撑任何指标;稀有本身就是排除理由 |

**结论:这四个字段不进记分集的理由是「无可判真值(currency、PO)」
或「真值稀有到进不了封箱集(buyer_tax_id、bank details)」—— 
不是「被判为不重要」。** 评分纪律「没有真值就不进错误率」不变:
把它们加进记分集只能产出伪指标。

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

## 复算脚本(本表全部数字的来源)

```python
import json, pathlib
from invoiceloop.eval_norm import eval_normalise as normalise
from invoiceloop.fields import Kind

ann = pathlib.Path("~/Developer/dws-derisk/data/docile/annotations").expanduser()
for ft in ("currency_code_amount_due", "account_num", "bank_num",
           "customer_tax_id"):
    keys = nonnull = 0
    for p in sorted(ann.glob("*.json")):
        for x in json.loads(p.read_text()).get("field_extractions") or []:
            if x.get("fieldtype") == ft:
                keys += 1
                t = x.get("text")          # 标注值在 text,不是 value
                if t and str(t).strip() and normalise(t, Kind.CODE) is not None:
                    nonnull += 1
    print(ft, "keys:", keys, "nonnull(CODE):", nonnull)
```

