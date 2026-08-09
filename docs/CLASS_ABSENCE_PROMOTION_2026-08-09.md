# 16 条类别缺席规则:propose → evaluate → promote 全过(2026-08-09)

依据表:[`DOCTYPE_ABSENCE_DEV_2026-08-09.md`](DOCTYPE_ABSENCE_DEV_2026-08-09.md)。
全程零 API。结果 harness **HAR-0017**,policy digest
`9b6df44236d1e22d19b760e1b1d786906f88c8d5a7d6ba58e5895982a699c7c7`,
文件已钉进 `docs/evidence/class_absence_2026-08-09/`。

## 结论

开发集 300 份 / 3,000 槽,HAR-0001 → HAR-0017:

| | HAR-0001 | HAR-0017 |
|---|---:|---:|
| 人工队列 | 1,806(60.2%) | **1,736(57.9%)** |
| `auto_absent` | 0 | 70 |
| **silent_absent(对 DocILE 真值)** | 0/0 | **0/70** |
| silent_wrong | 179/1,015 | **179/1,015** |

**−70 槽 = −2.33pp,两类静默错都没升。** 16 条候选全部通过
propose → evaluate → promote,没有一条被门拒。

## 数字是怎么合上的

规则匹配到 **107** 个槽(与 `absence_by_class.py` 预测的 107 完全一致),
其中:

- **70** 变成 `auto_absent` —— 这就是省下的人工;
- **29** 被 20% QA 探针送回人工 —— 设计如此,缺席是否成立要持续观测;
- **8** 仍留在队列 —— 这些槽另有门禁硬失败,缺席规则不越过 `slot_blocking`。

所以 107 条匹配换来 70 槽净省。**探针不是损耗,是这条路能走的前提**:被误判
成缺席的槽再也不会有人看到,没有事后发现的机会,只能靠抽检维持观测。

## 晋升谱系(每步对 HAR-0001 的累计 Δ)

| # | 规则 | Δpp | # | 规则 | Δpp |
|---|---|---:|---|---|---:|
| HAR-0002 | `AE-purchase_order-seller_vat_id` | −0.40 | HAR-0010 | `AE-contract-due_date` | −1.63 |
| HAR-0003 | `AE-purchase_order-due_date` | −0.63 | HAR-0011 | `AE-receipt-seller_vat_id` | −1.80 |
| HAR-0004 | `AE-confirmation-seller_vat_id` | −0.83 | HAR-0012 | `AE-credit_note-total_vat` | −1.90 |
| HAR-0005 | `AE-confirmation-total_vat` | −0.93 | HAR-0013 | `AE-estimate-due_date` | −2.00 |
| HAR-0006 | `AE-confirmation-due_date` | −1.03 | HAR-0014 | `AE-estimate-seller_vat_id` | −2.07 |
| HAR-0007 | `AE-credit_note-seller_vat_id` | −1.20 | HAR-0015 | `AE-purchase_order-total_net` | −2.17 |
| HAR-0008 | `AE-purchase_order-total_vat` | −1.37 | HAR-0016 | `AE-estimate-total_net` | −2.27 |
| HAR-0009 | `AE-contract-seller_vat_id` | −1.47 | HAR-0017 | `AE-estimate-total_vat` | −2.33 |

每一步的 `absent_rule_truth_conflicts_candidate` 都是 0 —— 这是 QA 抽检**之前**
的真值检查,一条会吞掉真有值槽的规则在这里就被拒,不靠探针碰运气。逐条记录见
`docs/evidence/class_absence_2026-08-09/promotion_log.json`。

## 复算

`runs/absence-dev-2026-08-09/runs/`(不在 git 里,在 invoiceloop-data 下):

- `run-0001` —— HAR-0001 基线
- `run-0002` —— HAR-0017,同一份证据、同一份 schema 重跑完整确定性流水线

两个 run 的 `silent_absent` / `silent_wrong` 由 DocILE 标注独立复算,不经
`improve` 的 scorer。语料是 `runs/absence-dev-corpus`:sealed1 / sealed2 /
heldout 三个工作区的 raw 汇成一处 + `data` 指向校准语料,**不含任何促销记录**,
所以基线一定是包内 HAR-0001。

## 两条限定

- **这是开发集。** sealed1 / sealed2 / heldout 全部在开发期被读过、被调过。
  −2.33pp 与 0 silent_absent 都**不是未见集上的结论**。
- **SEALED-3 不能用来验它。** 那批已被一次性开箱用掉
  (`SEALED3_RESULTS.md` §7),而且这 16 条规则正是由它的失败启发的。
  要资格,得另抽 SEALED-4 —— 见 `SEALED4_PROTOCOL.md`。

## 途中踩到的两个坑(记下来,别再踩)

1. **第一次建开发 run 时三个语料各跑一次,其中 sealed2-workspace 里有促销
   记录**,于是那 100 份是在 HAR-0004 下跑的,而另外 200 份在 HAR-0001 下。
   `pipeline.run` 的 active harness 来自**语料根**(`load_active(derisk_root())`),
   不是输出目录。混合基线让 16 条候选全部被拒,且拒绝理由一模一样 ——
   十六条不同的规则给出同一个数字,那就不是规则在起作用。改成一个不含促销
   记录的合并语料根之后才有意义。
2. `improve.gate_verdict` 返回的键是 `ok`,不是 `promotable`。读错键会把
   「全部通过」读成「全部拒绝」。
