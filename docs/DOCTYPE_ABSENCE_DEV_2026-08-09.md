# 类别条件缺席:开发集测量(2026-08-09)

两份零 API 脚本的结果,重算命令在文末。**全部数字来自开发语料**
(`sealed1-workspace`、`sealed2-workspace`、`heldout-workspace`,300 份去重后的
DWS 存盘响应)。SEALED-3 不在里面,也不许拿来验这里的任何结论 ——
它已被一次性开箱用掉(`SEALED3_RESULTS.md` §7)。

## 结论先行

1. **DocILE 自带单据类型真值**:`metadata.document_type`,5,680 份全有 ——
   tax_invoice 3850、order 1440、purchase_order 128、receipt 116、
   sales_order 75、proforma 29、credit_note 24、utility_bill 12、debit_note 6。
   所以类别判定的正确性是**可测的**,不必只靠断言。
2. **页面字面证据能给出可用类别的占 91.7%**(275/300)。其余 25 份不是判错,
   是页面上没写 —— 类别条件规则本来就不该在它们身上生效。
3. **可判子集上与 DocILE 一致 96.3%**(211/219)。8 处不一致里多数不是门禁
   的错:DocILE 标 receipt 而页面印着 INVOICE,DocILE 标 tax_invoice 而页面
   印着 Proforma / Confirmation / Estimate。**AP 复核者看到的是印在页面上的
   那个词。**
4. **类别条件化正是安全性的来源,这一点在数字上是分开的**:
   `seller_vat_id` 一个字段,按类别拆开之后一半的规则可以开、一半绝对不能开。
5. 按 silent=0 且 saves≥3 筛,**16 条候选可以提**,合计省 107 槽 /
   全语料 3,000 槽 = **人工负载 −3.6pp**,全部落在**非 invoice** 类别上。

## 1. 类别判定 vs DocILE

| 门禁裁决 | 份数 | 占比 |
|---|---:|---:|
| pass(有页面字面证据) | 275 | 91.7% |
| fail(DWS 报了类型,页面上找不到) | 18 | 6.0% |
| no_claim(DWS 没报类型) | 5 | 1.7% |
| unmapped(报的类型不在受控词表) | 2 | 0.7% |

**6.7% 的文档 DWS 自报了一个页面上无从印证的类型。** 这就是
`doctype.py` 存在的理由:那 20 份如果直接采信自报类型,被监督的模型就替
自己决定了要不要被监督。

可判子集(DocILE 类型在受控词表里有对应项、且门禁拿到可用类别)219 份,
一致 211 份 = **96.3%**。8 处不一致逐条在
`scripts/doctype_truth.py` 的输出里,例如:

- `254b7845…`:DocILE `receipt`,页面印 `invoice`,DWS 自报 `sale`
- `a187ba31…`:DocILE `tax_invoice`,页面印 `received`(Donation Received)
- `9ab6841f…`:DocILE `tax_invoice`,页面印 `estimate`

**DocILE 的 `order` 标签不进这一节**:65 份 DocILE-`order` 在页面上散成
purchase_order 9、confirmation 6、contract 5、credit_note 3、estimate 19、
invoice 9 —— 一个标签盖了几种单据,拿它算准确率只会算出一个没有意义的数。

## 2. 每条「类别 × 字段」缺席规则的两侧代价

一个槽只有在 DWS 没返回值时才落到缺席规则手里。此时真值也没有 → 净省一次
人工;真值**有** → 这个槽被自动判成缺席,**再也不会有人看到它**。

### 可以提的 16 条(silent=0,saves≥3)

| 规则 | 省 | 占该类文档 |
|---|---:|---:|
| `AE-purchase_order-seller_vat_id` | 16 | 100.0% |
| `AE-purchase_order-due_date` | 14 | 87.5% |
| `AE-confirmation-seller_vat_id` | 10 | 100.0% |
| `AE-confirmation-total_vat` | 8 | 80.0% |
| `AE-confirmation-due_date` | 7 | 70.0% |
| `AE-credit_note-seller_vat_id` | 7 | 100.0% |
| `AE-purchase_order-total_vat` | 7 | 43.8% |
| `AE-contract-seller_vat_id` | 6 | 100.0% |
| `AE-contract-due_date` | 5 | 83.3% |
| `AE-receipt-seller_vat_id` | 5 | 100.0% |
| `AE-credit_note-total_vat` | 4 | 57.1% |
| `AE-estimate-due_date` | 4 | 100.0% |
| `AE-estimate-seller_vat_id` | 4 | 100.0% |
| `AE-purchase_order-total_net` | 4 | 25.0% |
| `AE-estimate-total_net` | 3 | 75.0% |
| `AE-estimate-total_vat` | 3 | 75.0% |

合计 107 槽 / 全语料 3,000 槽 = **人工负载 −3.6pp**,全部在非 invoice 类别上。

### 绝对不能开的(silent > 0),按诱惑程度排

| 规则 | 省 | 静默吞掉 |
|---|---:|---:|
| `AE-invoice-seller_vat_id` | 184 | **7** |
| `AE-invoice-due_date` | 130 | **10** |
| `AE-invoice-total_vat` | 96 | **3** |
| `AE-invoice-total_net` | 55 | **3** |
| `AE-invoice-buyer_name` | 2 | **31** |

第一行就是这套东西的全部意义。`seller_vat_id` **不加类别条件**时是一条
「省 184 槽」的规则,看起来是全表最划算的一条 —— 而它会吞掉 7 个真有值的
税号。把同一个字段按类别拆开之后:purchase_order / confirmation /
credit_note / contract / receipt / estimate 六类各自 silent=0,加起来省 48 槽,
零代价;invoice 那一类留给人。

`AE-invoice-due_date` 同理,并且与 2026-08-06 记下的那次泛化伤害是同一件事
(一条 due_date 缺席 cohort 在 88 份没复核过的文档上静默丢掉 5 个真实到期日)。

## 3. 三条限定,不许省略

- **这是开发集上的数字。** 它决定值不值得提这条候选,**不是未见集上的保证**。
  要说「在没见过的数据上也成立」,得另抽 SEALED-4。
- **`credit_note × seller_vat_id` 在这里是 0/7,而 SEALED-3 主臂唯一那次
  静默缺席正好是一张 credit note 的 seller_vat_id**
  (`5a34aacb…`,真值 `27042768`,`SEALED3_RESULTS.md` §4)。开发集干净不等于
  未见集干净 —— 这条恰好把两者的差距摆在同一页上。
- **`unscored` 一栏是「算不出来」,不是零。** 没有 DocILE 标注记录的文档不能
  当作没有真值;`improve.gate_verdict` 在 QA 抽检**之前**就会因此拒掉候选。

## 重算

```bash
python3 scripts/doctype_truth.py       # 类别判定 vs DocILE 交叉表
python3 scripts/absence_by_class.py    # 每条规则的 saves / silent 台账
```

零 API:只读已存盘的 DWS 响应、已存盘的独立 OCR、DocILE 标注。
两份脚本都不接受 SEALED-3 的工作区作为默认输入。
