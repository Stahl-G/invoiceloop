# 广播 harness 设计草案(2026-08-10)

> **状态:草案,未实施,未测量。** 本文档是设计,不是结果。里面每一条"预期收益"
> 都必须先过开发集盲测、再过密封集,才许写成数字。
>
> **决定(用户,2026-08-10):** InvoiceLoop 的场景收窄为 **DocILE 中最多的美国广播
> 广告发票**;SEALED-4 仍跑,但主臂必须是按这个场景优化过的 harness,不是
> HAR-0017/0018。本文档回答:那个 harness 长什么样,怎么走到它,以及它怎么进
> SEALED-4。

---

## 0. 为什么现在的 harness 对这个场景不合理(一句话)

路由策略的可调面已经在非 invoice 类上榨得差不多了,而广播场景的痛点——
**合法缺席、派生 due_date、单总额、美国税号、当事方方向**——全在 schema 与
字段语义层,路由策略够不着。优化杠杆用错了层。

证据:广播域 dev 重放(194 份,`BROADCAST_DEV_REPORT_2026-08-09.json`)里,
人工队列 1,081 槽的 **56% 集中在四个"天然缺失"字段**:

| 字段 | review 槽 | 主要触发 | 标注覆盖率(全语料实测) |
|---|---|---|---|
| due_date | **178** / 194 | extraction_present 140(缺值) | 13.1% |
| seller_vat_id | 149 / 194 | 缺值 + 无 invoice 类缺席规则 | 11.9% |
| total_vat | 141 / 194 | 缺值(仅 12 槽被 AV 规则接住) | 10.7% |
| total_net | 137 / 194 | 缺值 | 13.9% |

其余大户:buyer_name 94(cross_mode 分歧 75 次)、total_gross 113、amount_due 108。

**当前队列的大部分是让人一遍遍地确认"这页上确实没印这个字段"** —— 这正是
页面证据缺席机制设计来接的事,只是它目前只接了 total_vat 一个字段。

## 1. 已测量的事实(设计的地面,全部可重算)

1. **DocILE 标注字段分布**(5,680 份全量实测,2026-08-10):头部六字段覆盖
   >80%;`total_net` 13.9%、`date_due` 13.1%、`vendor_tax_id` 11.9%、
   `amount_total_tax` 10.7%;`iban`/`bic` 近乎为零。
   **71.1% 的文档只有 amount_due + total_gross 两个金额**(单总额形态),
   74.7% due==gross。
2. **due_date 不印在页面上**:payment_terms 标注覆盖 35.9%,date_due 仅
   13.1%,且其中 26% 是 due==issue 的 "Cash in Advance" 标注惯例(噪音)。
   广播发票的到期日是 **issue_date + 付款条款算出来的**,不是抽出来的。
3. **缺席词表的单调安全性质**(`absence_evidence.py` 模块 docstring):
   加词只会少放行、永不造静默错;删词才是拟合方向。词表 v1(盲测)/v2
   (事后)两版都已照登(`ABSENCE_EVIDENCE_DEV_2026-08-09.md`)。
4. **类别条件缺席进不了 invoice 类**(实测封死):`AE-invoice-seller_vat_id`
   省 184 槽吞 7 个真税号,`AE-invoice-due_date` 省 130 吞 10
   (`DOCTYPE_ABSENCE_DEV_2026-08-09.md` §2)。invoice 类内只许走页面证据。
5. **schema 文字版候选已被 pilot 枪毙过一次**(`BROADCAST_PILOT_RESULT_2026-08-10.json`):
   30 份配对,silent_wrong 23→17,但 review 191→201、放行决策负载
   79.67%→81.00%,**不晋升**。只改描述文字能减错值,减不了人工量。
6. **派生 due_date 模块存在但触发率极低**:worktree `93d4ea3` 的
   `due_date.py`(v1 规则)在 pilot 30 份上 computed 2 / not_computable 28。
   保守是对的(没有明确标签的基准日就拒算),但 v1 的条款模式覆盖面太窄,
   按现状它救不了几个槽。
7. **improve lint 的硬边界**(`improve.py::lint_schema` / `lint_policy`):
   schema 候选**只许改已有受评字段的 description**——不许增删字段、不许改
   type、不许加 required;policy 候选只许加 cohort 条目。这个边界决定了
   本设计哪些能走正常晋升流程、哪些需要先改机制。
8. **DocILE 的 `vendor_tax_id` 真值 85% 是美国 EIN**(2026-08-10 全量实测:
   760 条非空标注中 648 条为 `NN-NNNNNNN` 格式,仅 3 条 VAT 式 `DE…`,
   其余多为无连字符的 9 位美国税号)。**这意味着真值侧一直把 EIN 当作这个
   字段的值**——EN 16931 口径的 schema 描述与真值直接冲突:按真值抽出 EIN
   的作答,被按描述训练的人工口径判为 `WRONG_FIELD_MAPPING`
   (`FIELD_COVERAGE.md` 已知关联限定记的那份 reject)。系统在惩罚正确答案。
   该限定条款以此实测为准修正:错映射的不是抽取器,是字段描述。

## 2. 设计(按层)

### P0 范围定义:什么算"广播发票"

沿用 pilot 冻结的范围规则(`BROADCAST_PILOT_SCOPE_2026-08-09.json`,
`broadcast-pilot-v1`):**FCC 风格呼号 + ≥2 个广播术语 = strong(224/400),
单侧证据 = weak(110),皆无 = none(66)**。规则确定性、零 API、对全语料可算。

- **开发集**:pilot 已用的 194 份(来自 sealed1/2/3 + heldout 的已曝光文档)。
  调参、词表设计、harness 候选评测都在这里,照旧零 API 重放。
- **评测集**:必须从**未曝光池**(现 4,931 份)里先按范围规则过滤、再抽取。
  见 §4(SEALED-4 修订)。
- weak/none 文档的处置:harness 不拒绝它们(范围是优化目标,不是门禁),
  但指标只在 strong 子集上报告,weak 单列。这是口径声明,写进评测协议。

### P1 Schema 层(lint 允许的范围内)

**原则:schema 文字只负责"别诱发幻觉",减人工靠 P2。**

1. **due_date 语义收窄 + 派生层落地。**
   - raw `due_date` 的 description 改为明确只抽"页面直接印出的绝对日期"
     (worktree 候选 schema 的做法;pilot 证明它减 silent_wrong)。
   - **合并 worktree `93d4ea3`**:`due_date.py` 派生层(`calculated_due_date`)
     进 main,接 pipeline/deliver/bundle。raw 字段永不被派生值覆盖。
   - **派生规则 v2**:v1 只认 "Net N" 和两类显式句式,30 份里只算出 2 份。
     v2 的条款模式清单(如 "2% 10 Net 30"、月末条款、"on receipt" 各形态)
     **先于任何命中率测量写成预注册清单**,再测。看过结果再加模式 = 拟合,
     与词表同纪律。
2. **seller_vat_id 的描述改为美国口径。** lint 不许改字段名,只许改
   description:"Seller US federal tax ID (EIN / Federal ID), or VAT
   identifier where present." 依据:§1.8——真值侧 85% 就是 EIN,EN 16931
   口径描述与真值冲突,且已实测诱发口径混乱(`FIELD_COVERAGE.md`
   已知关联限定,心码 WRONG_FIELD_MAPPING)。**记分映射
   (`DOCILE_TO_FIELD`)不动**,DocILE `vendor_tax_id` 与 `seller_vat_id`
   的对应关系不变——变的是描述向真值靠拢,不是真值向描述靠拢。
   (对照:pilot 的 ADK 草稿把 EIN **排除**在外——那会让抽取器刻意不抽
   真值标注的值,制造人工缺席;pilot 里它降 silent_wrong 的部分原因是
   不抽就不会错。方向错误,不采用。)
3. **金额四字段的描述按美国单总额形态写**,例如 total_net:
   "Subtotal before tax, only if separately printed." 目的只是减少"编一个
   net 出来"的诱因。单总额文档的算术门禁静默沿用既有 ruling
   (commit `6dce2e9`),不改门禁。
4. **明确不改:不增删字段。** order_id(广播 cluster 覆盖 48%,AP 对账天然键)
   想要的话是**机制变更**(lint_schema 放开增字段 + 记分字段集预注册扩充 +
   新真值来源),按 GOAL.md"少造机制"单独立项,不混进本次。

### P2 缺席层(本设计的主杠杆)

把页面证据缺席从 1 条规则扩到广播场景的三个字段。**全部走
`absent_evidenced_cohorts`(页面证据),不碰 `absent_expected_cohorts`
(类别赌注在 invoice 类已被实测封死,§1.4)。**

| 候选规则 | 词表现状 | 已知残余风险(照登) |
|---|---|---|
| `AV-total_vat` | 已有,HAR-0018 在用 | dev 上 0/136 静默 |
| `AV-seller_vat_id` | 词表 v2 已含美国拼法(federal/employer/id no…) | dev 剩 1 个静默(OCR 把 "Federal" 读成 "federai");**拒绝逐份拟合补词**,接受残余 |
| `AV-total_net` | 词表已有(subtotal/net/before tax…) | 待 dev 盲测;"net" 在广播发票上同时是佣金口径词(0.85 签名),词表设计时须预注册处理 |
| `AV-due_date` | **词表刻意不放行**(裸 `due` 被 "Amount Due" 命中,模块 docstring 明写) | 需要词表 v3 重设计,见下 |

**due_date 词表 v3 是本设计里唯一需要"设计"的东西,也是最容易踩拟合红线的地方。**
纪律(与 doctype 去污、词表 v1/v2 同):

1. v3 词表**先于任何 saves/silent 测量**写成清单并 commit(时间戳即预注册);
2. 设计来源是一般应付账款词汇("terms"、"net 30"、"payment due"、"days"
   等),**不读开发集台账里的具体拼法**;
3. "Amount Due"/"Balance Due" 与到期日的区分是 v3 的核心问题——候选解法是把
   金额语境词(amount/balance/due 共现)写成排除规则,而不是靠删词;
4. 写完在 194 份开发集上**盲测一次**,saves 与 silent 同时照登;silent > 0 即
   不晋升该字段,词表留在原地(负结果也进文档)。
5. 既有 8 个 due_date 口径分歧静默(`ABSENCE_EVIDENCE_DEV_2026-08-09.md`)
   与本词表无关,照登不动。

### P3 放行层(保守,基本不动)

- `release_tier1_explicit: true` **保持**。单据级人署名批准是 08-09 刚封死的
  安全边界(commit `a28587d`),场景优化不动它。
- `auto_accept_cohorts` 暂不加条目。广播场景里看起来最干净的形态(单总额、
  due==gross、citation 通过)恰恰是 silent_wrong 的历史藏身地(六轮:未被
  flag 的 TIER1 仍有 7.8% 真错)。**省人工的主杠杆是 P2 的缺席,不是放行。**
- buyer_name 的 cross_mode 分歧(94 槽)本次不处理:没有安全的自动规则,
  当事方方向的几何规则预注册失败已被杀(`DOCTYPE_STAGE_D_2026-08-07.md`),
  留在人工队列是诚实的答案。

### P4 量什么

开发集盲测(194 份,零 API 重放)报告,按字段给:
review 槽数、auto_absent 数、silent_absent(对真值)、silent_wrong(对真值)、
放行决策负载。晋升门沿用 SEALED 系纪律:**silent_absent 必须逐项列出,
>0 即不晋升该规则**;队列下降是收益,不是门槛。

## 3. 实施计划(顺序有依赖)

| 步 | 动作 | 验证 |
|---|---|---|
| 1 | ~~合并 worktree 到 main~~ **已完成 2026-08-10**:cherry-pick `93d4ea3`(due_date 派生层 + scope + 广播 tooling),`3c0568f`;`808b904` 未合——其 doctype-HITL 功能 main 已有自有实现(`ec715ba`,workbench 75 处 doctype 曝光),合并只会引入语义重复 | `pytest tests/` **687 过 3 跳**(合并前 673) |
| 2 | ~~schema description 修订(P1.1/1.2/1.3),走 `improve propose_schema` 正常 lint + 晋升路径~~ **已完成 2026-08-10,不晋升**:终版 10 条描述预注册(`BROADCAST_SCHEMA_FINAL_2026-08-10.json`);HAR-0022 复抽 30 份(510 credits)review_load -0.33pp、value_hits +1,但 silent_wrong 8→11——+3 全是**未改动 name 字段**的复抽方差(地址拼进名字),目标字段无可计分收益;裁决不晋升(stahl),HAR-0021 保持 active | eval + 候选 schema 钉本进 `docs/evidence/absence_v3_2026-08-10/`;方法论发现记入 `ABSENCE_V3_DERIVATION_V2_DEV_2026-08-10.md` §6 |
| 3 | ~~派生规则 v2 条款清单预注册 commit → 开发集测触发率~~ **已完成**:`6341052`;触发率 8/300(2.7%),对照真值 2/2 一致,瓶颈是 53 份"裸 Date" | 触发率与 not_computable 原因分布照登(`ABSENCE_V3_DERIVATION_V2_DEV_2026-08-10.md` §4) |
| 4 | ~~due_date 词表 v3 预注册 commit → 开发集盲测~~ **改为引擎 v3 模糊匹配**(单调安全机制,`e06488f`):seller_vat_id 234/0 **过线**;total_net×1 与 due_date×8 的静默全是口径分歧(单总额 ruling + 派生值 ruling),非词表问题 | silent=0 才进下一步(`ABSENCE_V3_DERIVATION_V2_DEV_2026-08-10.md` §1–3) |
| 5 | ~~`AV-seller_vat_id` / `AV-total_net`(/ `AV-due_date`)候选 → dev 评测 → 逐条晋升,得广播 harness(HAR-00xx)~~ **已完成 2026-08-10**:HAR-0019(seller_vat_id,`9939adb`)、HAR-0020(total_net)、HAR-0021(due_date) 逐条过强制门,署名 stahl;广播 harness = **HAR-0021**,dev 队列 60.20% → 47.73% | 每条:晋升日志 + policy 钉本进 `docs/evidence/absence_v3_2026-08-10/` |
| 6 | ~~SEALED-4 协议修订(§4)→ 人确认 → commit~~ **已完成 2026-08-10**:`04fc8cd` 增补件冻结(广播子池 union 4,196 实测、T1/T2 真值口径规则逐条列明);T1/T2 打分函数随 `0381016` 落地 | 修订先于一切抽取 |
| 7 | 预算授权 → `sealed extract` → 一次性开箱 | `SEALED4_RESULTS.md` |

步 3–5 全部零 API。步 2 复抽已花 510 credits(2026-08-10);剩下的花费只有步 7(~200 次调用,熔断 6,000 credits)。

## 4. 与 SEALED-4 的关系(必须改协议,且只能在抽取前改)

SEALED-4 现协议(`SEALED4_PROTOCOL.md`)的两个钉子都已不适合本设计:
名单从**全类型池**抽的(~25% 非 invoice,且广播/通用混杂),主臂钉的是
HAR-0017/0018(通用 harness)。抽取未发生,修订合法;抽取一旦发生,
以下全部作废重来。修订草案(写进 `SEALED4_PROTOCOL.md` 增补件):

1. **名单重抽**:先从 4,931 未曝光池按 `broadcast-pilot-v1` 范围规则确定性
   过滤(零 API),得广播子池;**新 drand round 重新抽 100 份**。旧名单
   (`sealed4_doc_list.json`)留盘不删,标注作废原因——与 SEALED-2 资格
   撤销同纪律:事实照登,不毁痕迹。
2. **主臂重钉**:步 5 产出的广播 harness;代码钉 = 抽取前 HEAD。**先 commit
   再抽取,顺序不许倒**(原协议 §1.2 同纪律)。
3. **基线不变**:包内 HAR-0001。两臂同证据配对,沿用 H1–H7 与 P1–P3。
4. **指标口径**:主指标在 strong 子集上报告,weak 单列;`due_date` 的
   due==issue 标注惯例(§1.2,26%)在真值侧如何处理,**先于开箱写进增补件**
   (建议:due==issue 且 payment_terms 为 Cash-in-Advance 类的标注行不计入
   due_date 缺席判定,理由与依据随增补件冻结)。
5. 原协议 §5 的冻结清单相应替换:冻结对象从 HAR-0017 policy 换为广播
   harness policy + 词表 v3 digest + 派生规则 v2 digest。

**这是"改判据"动作,按 GOAL.md 纪律:先说(本节)、给依据(§0–§1 的实测)、
写进文档(增补件),不静默改。**

## 5. 明确不做

- 不给 invoice 类加类别条件缺席规则(实测吞真值,§1.4);
- 不动 `release_tier1_explicit`,不动单据级人署名批准;
- 不增删 schema 字段(order_id 单独立项);
- 不做当事方方向的几何/模型判定(预注册失败已杀);
- 看过结果之后不加词表词、不加派生模式、不窄化匹配(拟合红线);
- 不用 SEALED-1/2/3 的任何文档验证本设计的修复(它们已全部曝光,
  只作开发集)。

## 6. 未测量声明(防读反)

- 人类裁决准确率:**NOT_MEASURED**(ARM 实验第 32 槽终止);
- schema 文字修订对人工量的影响:pilot 实测为**增加**,本设计不声称 P1 能
  减人工,只声称它防错映射;
- 派生 due_date 的触发率:v1 实测 2/30;v2 的预期触发率**没有依据**,
  步 3 测出来才算数;
- 词表 v3 的安全性:设计性质(加词单调安全)只保证方向,不保证 v3 的
  具体写法 silent=0——那要步 4 的盲测;
- 广播范围规则本身的偏差:callsign+术语是页面字面证据的代理,weak/none
  110+66 份里混着什么,只在 pilot 粗看过,没有逐份标注。
