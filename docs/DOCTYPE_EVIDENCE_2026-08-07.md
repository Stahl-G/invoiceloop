# 单据类型声明的页面字面证据(2026-08-07,阶段 A)

协议/计划:`docs/DOCTYPE_PLAN_2026-08-07.md`。实现:`invoiceloop/doctype.py`。
复算(零 API):

```bash
INVOICELOOP_CORPUS=runs/sealed1-workspace python3 scripts/doctype_evidence.py
INVOICELOOP_CORPUS=runs/sealed2-workspace python3 scripts/doctype_evidence.py --sealed2
python3 scripts/doctype_vocab_ablation.py            # 逐 token 消融
python3 scripts/doctype_vocab_ablation.py --v1-diff  # 去污前后对比
```

> **2026-08-07 更新(词表去污,`doctype-v1` → `doctype-v2`)。** 本文覆盖率
> 数字**一个没变**;变的是词表和对污染的描述。原「未了项 1」写的删除清单
> 有一处是错的,已在下面「去污」一节照登。

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

> **⚠ 这张表是样本内的,不是留出测量。** 词表是照着这两个集的自由文本
> 拼法写出来的,所以「`unmapped=0`」**构造出来的成分无法排除** ——
> 换一个没看过的集合,该数字不成立。去污(下节)删掉了七个明显的语料
> 派生 token,但**没有、也不可能**因此把这句话取消:剩下的载荷 token 里
> 仍有 `\bcheck\b`(S1 的 'check')和 `donation`(S1 的 'donation received')
> 是照着语料写的,删掉就有 3 份改判。**删不掉的那部分只能照登。**
>
> 唯一能把 `unmapped=0` 变成测量的办法,是在一个**词表冻结后才见到**的
> 集合上跑一次。那是下一步(见文末「未了项」1),不是本文能给的。

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

## 词表去污(`doctype-v1` → `doctype-v2`,2026-08-07)

删掉七个**只在校准语料自由文本里出现过**的 token:

| 类 | 删掉 | 它当初吃的串 | 那个串其实靠谁命中 |
|---|---|---|---|
| `credit_note` | `discrepancy` | S2 'billing discrepancy/credit request' | `credit` |
| `purchase_order` | `worksheet` | S1/S2 'order worksheet' | `\border\b` |
| `purchase_order` | `printout` | S2 'order printout' | `\border\b` |
| `purchase_order` | `traffic` | S2 'new traffic order form' | `\border\b` |
| `contract` | `broadcast` | S1 'broadcast contract' | `contract` |
| `invoice` | `affidavit` | S1 'invoice / affidavit' | `invoice` |
| `invoice` | `billing` | S2 'official billing invoice' ×2 | `invoice` |

**七个全是死票。** 逐 token 消融 + 组合验证实测:一起删,SEALED-1 未人工 88
与 SEALED-2 100 **各 0 份改判**,本文覆盖率表一个数字没变。

```bash
python3 scripts/doctype_vocab_ablation.py --v1-diff
#   TOTAL RECLASSIFIED BY THE DE-CONTAMINATION: 0
```

它们决定不了任何事,却让词表看起来是照着测试集调过的 —— 删掉是为了让
`unmapped=0` 不再有这层假象,不是为了改数字。

### 照登纠正:原「未了项 1」的删除清单是错的

原文写的是删 `discrepancy` / `printout` / `traffic` / **`receipt`** / `billing`
五个,并预测「SEALED-2 变成 ≈91% 有证据 + 2 份 unmapped」。实测后两处错:

1. **五个里有四个是死票,删了零改判**;预测的 2 份 unmapped **全部来自
   `receipt` 一个 token**,与另外四个无关。
2. **`receipt` 不该删。** 它是 `receipt` 类的本名,不是语料派生 —— 任何
   人凭常识写应付账款词表都会先写它。删掉的后果是 S2 里字面标题就是
   "Receipt" 和 "Transaction Receipt" 的两份变成 `unmapped`。
   **一个不认识 "receipt" 的 receipt 类不是去污,是自残。**

同时原清单**漏了** `worksheet` / `broadcast` / `affidavit` 三个同性质的
token(都是死票,现已一并删),也没提到真正删不掉的那两个:
`\bcheck\b` 与 `donation` 是 S1 派生**且载荷**(共 3 份改判)。

结论是这条方法论:**污染不能靠删 token 消掉。** 能删的都是死票(删了不
改数字,只改观感),改数字的那些恰恰删不得。真正的解药只有一个 ——
在词表冻结之后才见到的集合上量一次。

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

1. **`unmapped` 未曾在留出集上量过。** 去污只删掉了死票,污染仍在
   (`\bcheck\b` / `donation` 载荷且语料派生)。要把 `unmapped=0` 从
   构造变成测量,只有一条路:取一批**词表冻结后才见到**的文档,
   跑 understand 拿 `invoice_type`,一次性记下 `unmapped` 率,不许回头改词表。
   ~~词表去污~~ 已做(`doctype-v2`,见上节);`digest()` 已变 →
   去污前后的 run 不同代,不许混算。
2. 阻断名单里只有 **4/9** 逐份看过(表中标「抽查」的四份)。
   其余 5 份**未逐份裁决**,不得当作已确认的误分类。
