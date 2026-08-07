# 单据类型声明的页面字面证据(2026-08-07,阶段 A)

协议/计划:`docs/DOCTYPE_PLAN_2026-08-07.md`。实现:`invoiceloop/doctype.py`。
复算(零 API):

```bash
INVOICELOOP_CORPUS=runs/sealed1-workspace python3 scripts/doctype_evidence.py
INVOICELOOP_CORPUS=runs/sealed2-workspace python3 scripts/doctype_evidence.py --sealed2
```

## 词表冻结(阶段 A)

| 决定 | 取值 | 理由 |
|---|---|---|
| `proforma` | **单独成类** | 形式发票与 invoice 会计语义不同;已在 `CLASSES` |
| `check` | **归入 `receipt`** | 不拆新类;证据短语含 `check` |
| 匹配顺序 | `credit_note` → `proforma` → `confirmation` → `purchase_order` → … → `invoice` | `credit` 先于 `invoice`;`confirmation` 先于 `purchase_order`(否则 "Order Confirmation" 被 `\border\b` 抢走) |

后续**只许扩类/扩短语,不许改判据方向**(计划 §4)。

## 覆盖率(模型声明 → 受控类 → OCR 字面证据)

| 集 | n | 有声明且映入词表 | 有字面证据 | 证据率 | 无证据阻断 |
|---|---|---|---|---|---|
| SEALED-1 未人工 88 | 88 | 86 | **81** | **94.2%** | 5 (5.8%) |
| SEALED-2 | 100 | 99 | **90** | **90.9%** | 9 (9.1%) |

`unmapped=0`(两集)。`no_claim` 为模型未返回 `invoice_type`。

> **⚠ 这张表是样本内的,不是留出测量。** 冻结词表时我扫过 SEALED-2 的
> 自由文本拼法,`discrepancy` / `printout` / `traffic` / `receipt` / `billing`
> 五个 token **只因为 S2 里出现过才被写进去**。所以「`unmapped=0`」是
> **构造出来的**,不是测出来的 —— 换一个没看过的集合,该数字不成立。
> 去掉这五个 token 重算,SEALED-2 变成 **≈91% 有证据 + 2 份 unmapped**
> (unmapped 会显式转人工,不会被猜成 invoice,属于优雅降级)。
> 词表尚未去污 —— 见文末「未了项」。

**口径**:抽取器类型声明在这两个集上约 **8–9% 找不到页面字面支撑**
(SEALED-2 9/99),**且这个百分比带样本内污染**。
「找不到字面支撑」是一条可复算的支持关系判定,**不等于**「模型分类错了」——
语义对错仍由人看(宪章六)。也不是「类型检查能修好付款静默错」,
那是另一回事(见计划 §0)。

## SEALED-2 阻断名单(9)

| doc_id | 模型声明 → 类 | 备注 |
|---|---|---|
| `39fd2941088a4cd9864d8dbf` | Order Confirmation → confirmation | 分类对,页上无 confirm\* 字面 |
| `40532c4e2c6a42bca301ea58` | invoice → invoice | 抽查:实为 traffic order form |
| `45f1811ec4c74141b459f4ea` | pro forma invoice → proforma | 页上无 proforma 字面 |
| `6a6b6a39b9914e72b943c579` | invoice → invoice | 抽查:整页无 invoice 字样 |
| `9a52926255a64fd1aa57c5f8` | invoice → invoice | 抽查:实为 makegood form |
| `b45c2725a2204c03aa5b858a` | invoice → invoice | 抽查:整页无 invoice 字样 |
| `b5b4d5fb37b64428958cd7f5` | invoice → invoice | 无字面 |
| `e12004780d164ee9ba386f5f` | invoice → invoice | 无字面 |
| `fc7554630cc24a2c8f9db32b` | invoice → invoice | 无字面 |

## SEALED-1 未人工 88 阻断名单(5)

`0f1ca104…` / `50bbaa7c…` / `6decf48f…` / `9fadde21…`(均声明 invoice,无字面);
`afe032e8…`(声明 check → receipt,无 receipt/check/received 字面)。

## 与「付款静默错 22%」脱钩(照登纠正)

零触达集上 13 个静默错值**零个与贷项符号有关**;主体认错(`seller_name`)占 6/13。
类型证据门禁标出的是**类型声明在页面上找不到字面支撑的文档**,
它不直接消掉那 13 个金额错。
阶段 D 已处理主体方向并 **KILL**(51.6% < 80%,见
`docs/DOCTYPE_STAGE_D_2026-08-07.md`);贷项符号检查**不做**。

## 阶段 A 边界

- 本阶段**不接入**门禁 / 路由 / 指纹。
- 测试:`tests/test_doctype.py`(词序、边界、bbox 合并、`NO_CLAIM`≠`UNMAPPED`)。
- 下一步:阶段 B 回答 Q1(文档级裁决落点)与 Q2(阻断粒度对负载的影响)。

## 未了项(阻断本文数字进任何对外材料)

1. **词表去污**:删掉 `discrepancy` / `printout` / `traffic` / `receipt` /
   `billing` 五个 S2 派生 token,`engine` 升版本,重跑本文全部数字。
   会改 `doctype.digest()` → 改执行指纹 → 旧 run 与新 run 不同代。
2. 阻断名单里只有 **4/9** 逐份看过(表中标「抽查」的四份)。
   其余 5 份**未逐份裁决**,不得当作已确认的误分类。
