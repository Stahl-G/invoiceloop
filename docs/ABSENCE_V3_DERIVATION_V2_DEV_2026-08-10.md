# 引擎 v3 + 派生 v2:开发集测量(2026-08-10)

接着 [`ABSENCE_EVIDENCE_DEV_2026-08-09.md`](ABSENCE_EVIDENCE_DEV_2026-08-09.md)。
两个机制变更都**先于本次测量 commit**(时间戳即预注册):

- `6341052` —— 派生规则 v2(`due_date.py`,条款清单见代码注释);
- `e06488f` —— 缺席引擎 v3(`absence_evidence.py`,长 token 允许一个编辑的
  OCR 容错;方向与加词相同,只多匹配不少匹配)。

全程零 API:只读存盘 DWS 响应、独立 OCR、DocILE 标注。开发集 =
sealed1 / sealed2 / heldout 工作区去重后 300 份(SEALED-3 不用,它已被
一次性开箱用掉)。

## 一、缺席引擎 v3:seller_vat_id 过线了

`python3 scripts/absence_by_evidence.py` 原样重跑,引擎
`absence-evidence-v3`(词表 `0a9f3773577e068c…`,词表内容**与 v2 逐字相同**,
只有匹配规则变了):

| field | 缺值 | held | saves(v2) | saves(v3) | silent(v2) | **silent(v3)** |
|---|---:|---:|---:|---:|---:|---:|
| `seller_vat_id` | 266 | 27 → 32 | 238 | 234 | 1 | **0** |
| `total_vat` | 143 | 19 | 124 | 124 | 0 | **0** |
| `total_net` | 80 | 28 | 51 | 51 | 1 | **1** |
| `due_date` | 207 | 115 | 84 | 84 | 8 | **8** |

- v2 仅剩的那个静默(OCR 把 "Federal" 读成 "federai",
  `5da5a0e2bded40ad8948d5eb`)被模糊匹配接住 → `held`,回到人工。
  同时模糊匹配在别处多接住 4 个标签,saves 238 → 234 ——
  **少省 4 槽,正是安全方向该有的代价**。
- **`AV-seller_vat_id` 过线:234 saves / 0 silent / 0 unscored,其中 193 槽
  是 16 条类别规则够不到的(invoice 类 174 槽)。** 按与 HAR-0017 同一条线
  (silent=0、unscored=0、saves≥3)可提。
- 照登:这次测量是**事后的**——机制变更的动机案例就在 v2 台账里。
  与 v2 补词同一定性:单调安全掩护得了机制,掩护不了"盲"字。
  资格只能靠 SEALED-4。

### 晋升(同日;门内数,与即席台账口径不同,以门内数为准)

在干净工作区 `runs/absence-v3-2026-08-10`(只含 v3 探针 run——旧 v2
探针若混在同一 workspace,`_compute_evaluation` 的 `docs_without_probes`
会把规则静默禁用还误报 probe 状态)走完 propose → evaluate → promote:

- **`AV-seller_vat_id` 进 HAR-0019**(`PROM-0018`,署名 stahl,
  2026-08-10T05:23:20Z)。强制门逐字节重算的数字:review load
  55.67% → 50.47%(delta −5.2pp = 156/3000 槽出队),
  `absent_rule_matches` 212 → 405(+193),
  `silent_absent` 0→0,`absent_rule_truth_conflicts` 0,probe available。
- 口径自陈:台账的 234 saves 是"规则点火"计法(缺值 + 真值空 + 页面
  无证即计);门内 +193 是反事实重路由下的规则匹配数,156 是队列真实
  减少。三个计数器各计各的,对外引用一律用门内数。
- 工件:`docs/evidence/absence_v3_2026-08-10/`(policy / eval / PROM
  三份拷贝)。

## 二、total_net 仅剩的 1 个静默:单总额口径分歧,不是词表漏词

`f7b199fd711149feaf0044c8`(1998 年扫描件,圣安东尼奥西班牙裔商会会员发票):
页面只印一个 `$1100.00`("Anount Due" 都是 OCR 错字),**没有任何 net 类
标签**;DocILE 把这一个金额标成了 `total_net`(amount_due 也标了 $1100.00)。

这正是单总额 ruling(commit `6dce2e9`,2026-08-08 预注册)的形状:
单总额文档的 Total 映射到 amount_due,其余三个金额 confirm_absent。
**页面证据规则的 auto_absent 与项目自己的口径一致,与真值的字段选择不一致。**
按宪章五这是 `applicability` 维度的口径分歧,不是抽取错误——但按
08-09 的纪律,在真值口径规则写进协议之前,它**照登为静默错,规则不晋升**。

## 三、due_date 的 8 个静默:同上一家族的口径分歧

逐条构成不变(08-09 已查):真值把 "transaction sale date time"、
"credit adjustment by eft"、"donation received payment status completed"
这类**别名目日期**标成 `date_due`,而派生值 ruling(commit `95c6b66`)
已规定:页面上没有该名目的标注列 → confirm_absent,不许从邻列推断。

**total_net×1 + due_date×8 = 9 个静默,全部落在"项目口径 vs DocILE 标注
口径"的同一条缝上。** 处理路径是 SEALED-4 增补件里的真值口径规则
(预注册、逐条列明、进文档),不是词表改动——见
[`BROADCAST_HARNESS_DESIGN_2026-08-10.md`](BROADCAST_HARNESS_DESIGN_2026-08-10.md)
§4.4。在那条规则被采纳之前,`AV-total_net` 与 `AV-due_date` 保持拒开。

## 四、派生规则 v2:触发率 8/300(2.7%),诚实但稀疏

同一 300 份上跑 `derive_due_date`(版本 `due-date-relative-term-v2`):

| 结果 | 份数 |
|---|---:|
| computed(days 分布:30×7,0×1) | 8 |
| not_computable:页面无相对付款条款 | 201 |
| not_computable:有条款但**无标签**的基准日(印的是裸 "Date") | 53 |
| not_computable:receipt 类条款无 receipt 日期(诚实拒算) | 28 |
| not_computable:EOM/prox 月末条款(认得但不算) | 6 |
| not_computable:条款互相矛盾 | 4 |

真值对照:8 份 computed 里 2 份真值有 `date_due`,**两份都一致**
(我的即席比对脚本把 `2018-07-12` 与真值文本 `07/12/18` 判成不一致——
是两位数年份的格式假象,逐条核对为同一日期;脚本不是评分器,照登)。
另 6 份真值无 date_due,无从判对。

**结论:v2 把 v1 的 2/30(pilot)提到 8/300,但绝对触发率只有 2.7%。**
最大的拦路不是条款形态,是 53 份"有条款、裸 Date"——把裸 `Date` 当
issue date 是一条新的口径规则(它也可能是 due date),**没有预注册不做**。
派生层对队列的贡献有限,duedate 的主杠杆仍在缺席侧(第二节)与
schema 侧(步 2,待复抽预算)。

## 限定

- 全部是**开发集**数字(sealed1/2/heldout 全部曝光过),不是未见集结论;
  资格只能由 SEALED-4 给。
- 引擎 v3 测量是事后的(动机案例在 v2 台账里);`AV-total_vat` 仍是唯一
  在盲测版上通过过的规则。
- 真值口径规则(第二、三节)已被采纳(2026-08-10,stahl),写进 SEALED-4
  增补件;`AV-total_net` / `AV-due_date` 的重评在那之后走,在此之前
  两规则仍拒开,9 个静默照登。

## 复算

```bash
python3 scripts/absence_by_evidence.py          # 第一节台账(引擎 v3)
python3 -m pytest tests/test_absence_evidence.py tests/test_due_date.py
```

派生触发率为即席脚本(零 API,只读 `load_ocr` + `derive_due_date`),
未存盘;对比口径的格式假象已在第四节自陈。
