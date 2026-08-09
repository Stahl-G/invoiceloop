# 页面证据缺席:开发集测量与一条晋升(2026-08-09)

前一份是 [`DOCTYPE_ABSENCE_DEV_2026-08-09.md`](DOCTYPE_ABSENCE_DEV_2026-08-09.md)
(类别条件缺席,16 条晋升为 HAR-0017)。这一份接着它往下走:类别规则**进不去
invoice 类**,而剩余缺值槽的 568/722 正是 invoice。

全程零 API。结果 harness **HAR-0018**,policy digest
`30797d4e9edda174524a3f45cf4e1744b057d64908c0f2ba60a6dae941241d65`;
词表版本 `c90cf8df16d82c2d…`(引擎 `absence-evidence-v2`)。
工件钉在 `docs/evidence/absence_evidence_2026-08-09/`。

## 结论

开发集 300 份 / 3,000 槽,三臂各跑一次完整确定性流水线:

| | HAR-0001 | HAR-0017 | **HAR-0018** |
|---|---:|---:|---:|
| 人工队列 | 1,806(60.20%) | 1,736(57.87%) | **1,670(55.67%)** |
| `auto_absent` | 0 | 70 | **136** |
| **silent_absent** | 0/0 | 0/70 | **0/136** |
| silent_wrong | 179/1,015 | 179/1,015 | **179/1,015** |

**在 16 条类别规则之上再省 66 槽(−2.20pp),对基线 −4.53pp,两类静默错都没升。**

HAR-0001 与 HAR-0017 这两个数字是在**新代码下重跑**出来的,与 2026-08-09 上午
的旧记录逐位一致(1,806 / 1,736)—— 加了缺席探针没有改动任何既有 harness 的
路由。这不是顺带一提:探针是新加进门禁事务的一项检查,它若动了旧臂,三臂对照
就不是同一把尺。

## 机制:押注换成证据

类别条件规则问的是「这一类单据通常有没有这个字段」——一个对同类文档的统计押注。
本机制问的是另一个问题,**关于这一份**:页面上到底印没印过这个字段的标签?

一个槽只有在 DWS 没返回值时才落到缺席规则手里。此时:

- 页面印着 `VAT` / `Tax` / `MwSt` 之类 → 这不是缺席,是**漏抽**,留给人;
- 页面上一个税额标签都没有 → 缺席由**这一页纸**背书,不是由同类文档背书。

所以它能进 invoice 类,而类别规则不能:`AE-invoice-total_vat` 省 96 吞 3,
`AE-invoice-seller_vat_id` 省 184 吞 7。

### 单调安全性:这套东西敢在开发集上定词表的理由

往词表里**加**一个 token,只能把某份文档从「缺席成立」变成「缺席不成立」,
反向不可能。所以更宽的词表严格更安全:**加词永远不会造出静默错,只会少省几槽。**
拟合压力只有在**删词**时才走向不安全的一侧。纪律因此是:

> 看过结果之后加词随意,删词等于拟合。

`tests/test_absence_evidence.py::TestMonotoneSafety` 把这个方向钉住了。

## 词表两版,两版都照登

**v1 是盲测**(commit `da5337e`,写在任何 saves/silent 数字之前)。
**v2 是事后的**:看过 v1 台账才补的词。两版都登,因为只有 v1 那一列是盲的。

| field | 缺值 | held | v1 saves | v1 silent | v2 saves | v2 silent |
|---|---:|---:|---:|---:|---:|---:|
| `total_vat` | 143 | 19 | **124** | **0** | **124** | **0** |
| `seller_vat_id` | 266 | 4 → 27 | 256 | **6** | 238 | **1** |
| `due_date` | 207 | 115 | 84 | **8** | 84 | **8** |
| `total_net` | 80 | 28 | 51 | **1** | 51 | **1** |

v2 补的是 `seller_vat_id` 上美国税号标签的**拼写形式**:v1 只收了缩写
(`ein` / `fein` / `tin`),而美国发票实际印的是 "Federal ID"。v1 漏掉的 6 个
税号,5 个紧跟在 `federal` 后面,第 6 个是 OCR 把 "USt-IdNr" 读成 "ush id nr"。
补词走的是单调安全那一侧,代价是 18 槽 saves。

**只有 `AV-total_vat` 两版都通过**,而且是在盲的那一版上通过的 —— 这是本文件里
唯一一条强主张。

### 没有跨过去的那条线

v2 之后 `seller_vat_id` 还剩 1 个静默,原因是 OCR 把 "Federal" 读成 "federai"
(`5da5a0e2bded40ad8948d5eb`)。**没有把 `federai` 加进词表。** 那是某一份文档上
的某一个 OCR 错字,不是应付账款词汇;加它只能压住这一份。单调安全掩护不了逐份拟合。

`due_date` 的 8 个静默同理。逐条看下来,它们是页面上标着别的名目的日期 ——
"transaction sale date time"、"credit adjustment by eft"、"donation received
payment status completed" —— DocILE 把它们标成了 `date_due`。这是口径分歧
(宪章五),真值那一栏settle 不了。**但这不救这条规则**:登记为静默错,规则拒掉。
不许拿「标注可能错了」去换一个更好看的数字。

## 124 个命中槽的去向,逐条对上

`AV-total_vat` 在 143 个 total_vat 缺值槽里,有 124 个页面证据成立。这 124 槽:

| 去向 | 槽 |
|---|---:|
| `auto_absent` —— 这就是省下的人工 | **66** |
| 20% QA 探针送回人工(设计如此) | 17 |
| 已被 16 条类别规则接走(类别规则先判) | 16 |
| 另有硬门禁失败(`UNSUPPORTED`,无证据绑定) | 25 |
| **合计** | **124** |

66 槽净省,与队列 1,736 → 1,670 完全一致。

## 复算

```bash
python3 scripts/absence_by_evidence.py     # 每条规则的 saves / silent 台账
```

三臂 run 在 `runs/absence-evidence-2026-08-09/`(不在 git 里):
`arms/har0001` 基线、`runs/run-0001` HAR-0017、`arms/har0018` 本次。
`silent_absent` / `silent_wrong` 由 DocILE 标注独立复算,不经 `improve` 的 scorer。

重跑非基线臂要临时把工作区 harness 状态挂进**语料根**,跑完就摘掉 ——
`pipeline.run` 的 active harness 取自 `load_active(derisk_root())`,不是输出目录:

```bash
ln -sfn ../absence-evidence-2026-08-09/improve   runs/absence-dev-corpus/improve
ln -sfn ../absence-evidence-2026-08-09/harnesses runs/absence-dev-corpus/harnesses
# … 跑 pipeline …
rm -f runs/absence-dev-corpus/improve runs/absence-dev-corpus/harnesses
```

## 三条限定

- **这是开发集。** sealed1 / sealed2 / heldout 全部在开发期被读过。
  −2.20pp 与 0 silent_absent **不是未见集上的结论**。
- **词表 v2 是事后的。** v1 那一列才是盲测,`AV-total_vat` 在两版上都成立
  是它唯一值得多信一点的理由。真要资格,只有 SEALED-4。
- **SEALED-3 不能用来验它。** 那批已被一次性开箱用掉
  (`SEALED3_RESULTS.md` §7)。

## 旧 run 判不了这类候选,而且它不会假装能判

缺席探针只存在于本次改动之后跑的 run。旧 `gate_report` 里没有 `absence_probes`,
页面证据规则一条也匹配不上,评测会给出一个漂亮的**零变化** —— 而零变化读起来像
「这条规则没用」,不像「这批证据判不了」。

`improve.gate_verdict` 因此单列 `absence_probe_status`:见到 `unavailable` 就拒,
并点名原因(重跑 run 再评)。宪章四:跑不了不是通过,也不是零。
回归钉在 `tests/test_improve.py::TestAbsentEvidencedLoop::
test_a_run_without_probes_is_refused_not_scored_as_no_effect`。
