# SEALED-4 增补件:广播范围 + 真值口径规则(2026-08-10,抽取前冻结)

对 [`SEALED4_PROTOCOL.md`](SEALED4_PROTOCOL.md) 的修订。原协议 §1.2 已把
代码钉与主臂标为"抽取前重钉";本增补件把**名单范围**也改掉,并新增真值
口径规则。合法性依据与原协议相同:**SEALED-4 至今未抽取、未开箱,不存在
任何结果**;§5 管的是"结果出来之后再改",与本增补件无关。抽取一旦发生,
本文件再动任何一字 = 本批作废。

本文件首次提交即冻结。 drand 轮次留白,执行时填(原协议 §1 同纪律)。

## A1. 名单:范围换成广播,新种子重抽

原名单(`docs/sealed4_doc_list.json`,drand round 6360483)从**全类型池**
抽的(~25% 非 invoice,广播/通用混杂),与广播 harness 的优化目标不匹配。
处理方式:**留盘不删,标注作废原因**(与 SEALED-2 资格撤销同纪律:事实照登,
不毁痕迹)。

新名单:

1. 子池 = `heldout.sealed_pool()`(4,931 份,未曝光)按 `broadcast-pilot-v1`
   范围规则确定性过滤(`scripts/broadcast_scope.py::classify_evidence`,
   FCC 呼号 + 广播术语,**零 API**,只读语料 OCR);
2. 子池大小已实测(2026-08-10,先于任何抽取):
   **strong 2,725 / weak 1,471 / none 735(不进名单)**,union(strong+weak)
   = **4,196 份**,名单复算锚:
   - strong digest `d1e79686fe67f389cc08f9deba200aaa21f8c661445d5de738af65bb1f926489`
   - weak digest `72066c8be5e082abd31093a1ca8c60cffdbbf39e449cd575498f440917bbcb16`
   - union digest `78066c41a4bea9fa5f5102ccd5977ae2993297ba5fbb055b04cee810e0ae438c`
   (digest = 排序后 doc_id 逐行连接的 sha256;过滤规则与暴露清单任一变化
   都会改变它们);
3. 从 union 4,196 份用**新 drand round**(留白,执行时填)抽 100 份,
   PRNG 语境换 `sealed4-v2`(`SEALED_CONTEXTS` 相应增加,代码改动随本
   增补件之后的实施 commit 落地,先于开奖);
4. 名单落盘 `docs/sealed4_doc_list.json`(覆盖前把旧名单改名
   `sealed4_doc_list_voided_fullpool.json`),**单独 commit,先于任何
   DWS 调用**。

代价照登:union 抽取预期 ~65 strong + ~35 weak,主指标只在 strong 子集上
算(A4),统计功效低于 100 份全 strong —— 换来的是 weak 单列可见,
不藏在"广播"一个标签后面。

## A2. 主臂与代码钉

- **主臂 = 抽取前 HEAD 上 `improve/active_harness` 指向的广播 harness。**
  当前为 **HAR-0019**(= HAR-0017 + `AV-total_vat` + `AV-seller_vat_id`,
  policy digest `ebaf66ef8ec9542d1dc9d5bd3d829ccab8cebae4cec2083a60b7d7b3bef90fa7`);
  步 6b / 步 2 若再晋升,以抽取前最后一次晋升为准,policy digest 在抽取前
  的钉板 commit 里写死;
- **代码钉 = 抽取前 HEAD。先 commit 再抽取,顺序不许倒**(原协议 §1.2
  同纪律);
- **基线不变**:包内 HAR-0001。两臂同证据配对,H1–H7 区间与 P1–P3
  通过线沿用原协议 §3;
- 缺席引擎钉:`absence-evidence-v3`,词表 digest
  `0a9f3773577e068c4b6a21ed68ead6a8ae37dacc755ce928e9d4051f4af6f92e`;
- 派生规则钉:`due-date-relative-term-v2`;
- A3 的 T1/T2 打分函数是产品代码,随代码钉一起冻结。

## A3. 真值口径规则(2026-08-10 经 stahl 采纳,先于开箱冻结)

既有两条口径 ruling 管的是**项目侧**的行为;DocILE 真值侧存在同族分歧,
打分器没有第三个桶(`6dce2e9` 已预注册过这个问题)。本规则把两条 ruling
一致化到真值侧:**下列情形属 applicability 维度的口径分歧(宪章五),
不计入 `silent_absent`,单列照登为「口径争议」。** P1 判定只用真静默列;
口径争议列不许归零、不许隐藏。

### T1 —— 单总额单据,真值把总额标进非 amount_due 字段

机械定义:slot `(doc, F)`,`F ∈ {total_net, total_vat, total_gross}`,
被判 `silent_absent` 时,若**同一份**的 `truth[F]` 与 `truth[amount_due]`
规范化后金额相等(同一金额,真值只是选了另一个槽放),重分类为口径争议。
依据:ruling `6dce2e9`(单总额单据 `Total` 归 `amount_due`,其余三个金额
字段 `confirm_absent`)—— 项目侧早已这样判,真值侧现在对齐。

开发集实例(1 份,逐条列明):

| doc_id | truth[F] | truth[amount_due] | 页面 |
|---|---|---|---|
| `f7b199fd711149feaf0044c8` | `total_net` = `1100.00` | `$1100.00` | 只印一个 `$1100.00`,无任何 net 类标签 |

### T2 —— 真值把别名目日期标成 date_due

机械定义:slot `(doc, due_date)` 被判 `silent_absent` 时,若 `truth[due_date]`
非空、其文本在页面 OCR 中出现,且满足 (i) 或 (ii),重分类为口径争议:

- (i) `truth[due_date]` 与 `truth[issue_date]` 规范化后为同一字符串
  (真值把同一日期同时标成 issue 与 due);
- (ii) 该日期在 OCR 中出现位置的 **±12 词窗口**内含冻结词集
  `{transaction, donation, authorization, adjustment}` 之一(小写匹配)
  —— 即它印在交易/收据时间戳的语境里,不是付款到期语境。

依据:ruling `95c6b66`(页面上没有该名目的标注列 → `confirm_absent`,
不许从邻列推断)—— 派生/交易时间戳不是 invoice 的 due date,项目侧早已
这样判,真值侧现在对齐。**词集只许加不许删;看过本批结果后加词 = 拟合,
本批作废。**

开发集实例(8 份,逐条列明;页面语境为 OCR 原文片段,规范化小写):

| doc_id | truth[due_date] | 页面语境(规范化) | 命中 |
|---|---|---|---|
| `0c56b86aedd445d8a845a287` | `03/27/00` | `credit adjustment by eft 03 27 00` | (ii) adjustment |
| `254b7845992547228487acc5` | `12/1/2021` | `transaction sale date time 12 1 2021 11 05 17 am cst` | (ii) transaction |
| `878ad70041f840eb923504a3` | `10/19/20` | `…belmont street bellaire… 10 19 20 1 53pm ref r293320050009 authorization code 101917` | (ii) authorization |
| `a14811674f9e4b2c99bce2be` | `August 26, 2020` | `donation received payment status completed august 26 2020 at 7 19 45 pm pdt` | (i)+(ii) |
| `a187ba31eae2481ca20cdc7a` | `September 5, 2020` | `donation received payment status completed september 5 2020 at 12 34 35 pm pdt` | (i)+(ii) |
| `c8d26800425448f1ae2115d1` | `26-Jul-2022` | `payment information date lime transaction id transaction type … 26 jul 2022 10 07 33 cdt` | (ii) transaction |
| `cdf65b6accc54facb0d8cf8e` | `9/29/2021` | `transaction sale date time 9 29 2021 8 46 55 am cst` | (ii) transaction |
| `db2e81c790384a11bbde5194` | `August 26, 2020` | `donation received payment status completed august 26 2020 at 7 14 08 pm pdt` | (i)+(ii) |

**代价自陈**:T2 会放过「真 due date 恰好印在这四个词旁边」的槽 ——
用一点静默检出灵敏度换口径一致性。写下即承认,不许事后说成零代价。

## A4. 指标口径

- 主终点(H1–H7 区间)与 P1–P3 在 **strong 子集**上报告;
- **weak 子集单列**同套数字,不参与晋升判定;
- `silent_absent` 拆两列报:真静默 / 口径争议(A3);P1 只看真静默列。

### A4.1 结果前就写死的预测(替换原协议 §3.1)

原协议预测针对 HAR-0017(队列降 1–4pp,`silent_absent ≤ 2`),主臂换了,
预测重写。开发集(全类型 300 份)上 HAR-0001 人工队列 60.20% → HAR-0019
50.47%(−9.73pp);广播子集上缺席规则命中更密,但 SEALED-4 的 strong 子集
只有 ~65 份,噪声更宽。

**预测:strong 子集人工队列相对基线下降 4–12pp;真静默 = 0;口径争议
0–3 例。** 偏差本身不是作废条件,照登即可;作废条件在原协议 §5 + 本件 A2/A3。

## A5. 原协议条款的处置

| 原协议 | 处置 |
|---|---|
| §0 冻结对象(代码 `175f1e6`、主臂 HAR-0017) | 由 A2 替换 |
| §1 种子(round 6360483)与名单 | 作废留盘(A1),新 round 留白 |
| §2 步骤 | 顺序不变:名单 commit 先于一切 DWS 调用;抽取需明确预算授权 |
| §3 P1–P3 | 沿用,作用于 strong 子集;`silent_absent` 按 A3 拆列 |
| §4 主张纪律 | 沿用,措辞中"16 条类别缺席规则"相应读作"广播 harness(主臂 policy 内容以钉板为准)" |
| §5 作废条件 | 沿用,冻结对象替换为 A2 列出的全部钉子 + A3 词集 |

## 实施清单(全部先于抽取,每步单独 commit)

1. ~~本增补件 commit~~ **已完成**:`04fc8cd`;
2. ~~代码:`SEALED_CONTEXTS` 加 `sealed4-v2`,`sealed_list` 支持子池过滤
   (strong+weak)—— 带测试~~ **已完成**:`48d1fcd`(迁移进
   `invoiceloop.scope` 的分类器重算 4,931 池,strong 2,725 / weak 1,471 /
   union 4,196 与三个 digest 逐字节吻合,回归测试钉死);
3. ~~代码:A3 的 T1/T2 重分类函数(供 SEALED-4 打分与步 6b 开发集重评
   共用)—— 带测试,词集即上表冻结词集~~ **已完成**:`0381016`
   (`invoiceloop/truth_caliber.py`,truth-caliber-v1);
4. drand round 开奖 → 填入 A1 → commit;
5. 新名单落盘 → 单独 commit(旧名单改名留盘);
6. 主臂 policy digest + 代码 HEAD 钉板 commit;
7. **明确预算授权后** `sealed extract`;封箱不读,开箱一次,
   `SEALED4_RESULTS.md` 数字照登。
