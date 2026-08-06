# Rubric v0.1 复评(2026-08-06,evaluated_commit `562af0a` = main HEAD)

判据不变:`docs/HACKATHON_RUBRIC_v0.1.md`(冻结于 `5567241`)。
上一轮:`docs/RUBRIC_V01_SCORE_2026-08-05.md`(`ad3d655`,86/96)。
demo reel 分项仍按用户决定删除,满分基数 **96**。

**结果:93 / 96(96.9%),较上轮 +7。** 分档:Submission-ready。

区间内变化:main 上 10 个 commit(2026-08-05 两个、08-06 八个),
上轮列的 6 条 ROI 动作落地 5 条。

---

## 一、分项变化

| ID | 维度 | 上轮 | **本轮** | 满分 | 变化原因 |
|---|---|---:|---:|---:|---|
| A | 真实问题与项目概念 | 8 | **10** | 10 | README 指名 AP 记账员 + 审计人员,四条错误代价逐条绑定字段 |
| B | 项目进展与端到端执行 | 11 | 11 | 12 | 未变(见下) |
| C | 落地与创业可行性 | 4 | **8** | 8 | ERP 集成路径 + 实测延迟 + 替代的人工步骤,三个子项全部补齐 |
| D | Nutrient DWS 集成深度 | 15 | 15 | 15 | 已满 |
| E | 可靠性改进与实验证据 | 19 | 19 | 20 | 扣分理由**更换**(见 §三) |
| F | 风险路由与 HITL | 13 | 13 | 13 | 已满;证据强度显著上升(真人工时数据) |
| G | 审计、来源与可回放性 | 10 | 10 | 10 | 已满 |
| H | 创新性与差异化 | 4 | 4 | 5 | 跨文档类型的推广仍未主张也未演示 |
| I | 提交材料(去 demo reel) | 2 | **3** | 3 | 英文 pitch + 英文段 + 双语 UI |
| | **合计** | 86 | **93** | 96 | |

Round proxy:Overall(A+B+C)**29/30**;Sponsor(D+E+F+G+H)**61/63**;Submission **3/3**。

---

## 二、本轮亲手验过的(不是读 README)

| 主张 | 验证方式 | 结果 |
|---|---|---|
| 测试全绿 | `python3 -m pytest tests/` @ `562af0a` | **372 passed**(README 写 370,低报) |
| 全链路仍通 | demo → adjudicate(HD-0001)→ bundle(48 成员)→ verify | 四层全过;矩阵摘要与上轮**逐字段相同**(HAR-0001 默认不变,「字节等价」成立) |
| 工作台 | 起在 8791 端口实拉两页 | 队列页 191KB 带搜索框 `name="q"`;裁决页 200,3 个 page-tab、bbox overlay 定位块、任务行、`why this is in your queue: gate failed: cross_mode_agreement` |
| Host 白名单 | `curl -H 'Host: evil.example'` | **403** |
| HITL run-0002 全部数字 | 直接重算 `runs/hitl-sealed/runs/run-0002/adjudication_ledger.jsonl` | **逐个吻合**:123 条裁决 / 120 槽 / 3 supersession;accept 67 · correct 24 · confirm_absent 26 · N/A 4 · reject 2;中位耗时全部 28s、accept 20s、correct 66s、confirm_absent 44s、reject 95s、N/A 90s;快路 74/123 = **60.2%**;最大间隔 25,088s(即他们说的隔夜污染,故只报中位 —— 处置正确) |
| 延迟 | 769 份存盘响应的 `processingTimeMs` 独立重算 | understand 中位 9.1s / p95 30.5s,agentic 中位 12.0s / p95 32.3s,串行 ≈21.1s/份 —— 与 README 的 9.1/11.9/21s 一致 |
| 封箱集基线 21.91% | `python3 scripts/baseline_comparison.py runs/sealed1 runs/sealed1-workspace` | **完全复现**:TIER1 281 槽,置信度阈值 21.91% vs InvoiceLoop 9.62%,覆盖 89.3% vs 55.5%,路由召回 35.3% vs 83.3% |
| 改进层没有偷跑 | grep HAR-0003 / 找 promotion 记录 | HAR-0003 只是**候选**,无晋升记录、无对外数字。SEALED-1「本批降级为回归集、正式结论等下一批」的纪律**守住了** |
| absent_expected 没放松硬阻断 | 读 `tests/test_routing.py` 新增用例 | 钉死:doc 阻断仍 block、QA 抽检强制 review、cohort 不激活时 verdict 仍 `fail` |

---

## 三、E 项扣分理由更换(重要)

上轮 E 扣 1 分的理由是「四个 rubric 建议字段缺席且无说明」。
`docs/FIELD_COVERAGE.md`(2026-08-06)正是为此而写,**时点正确**
(SEALED-2 之前,不是事后补)。但**该文件的实测数字复现不出来。**

复算(`~/Developer/dws-derisk/data/docile/annotations/`,5,680 份,
与该文件声称的语料同一份;`trainval.json` 亦为 5,680):

| FIELD_COVERAGE.md 的说法 | 本次复算 | 判定 |
|---|---|---|
| currency:1,054 份有标注键,**非空值为零** | 键出现在 **4,000** 份;按项目自己的 CODE 规范化后仍非空的有 **126** 例 | **数字对不上** |
| account_num / bank_num:键存在 **52 / 39** 份,**非空值为零** | 键出现在 **112 / 93** 份;非空实例 **135 / 105**,样例是 `10491969`、`052001633` —— 真实账号/行号 | **「非空值为零」为假** |

在 train/val 任一子集下都复现不出 1,054 / 52 / 39,也复现不出「零」。

**最可能的成因**:currency 的标注 `text` 普遍是裸符号 `$`(样例逐条确认),
按 CODE 规范化会塌成 `None` —— 「无可判真值」对 currency **结论成立**,
但成立的理由是「标注的是货币符号位置,不是币种代码」,不是「非空值为零」。
而 account_num / bank_num 有实打实的可判真值,只是**稀有**(112/5,680 ≈ 2%),
稀有到进不了 100 份封箱集 —— 这本身就是充分且诚实的排除理由。

**处置建议**:结论(四个字段不进记分集)不用改,把理由改成能复算的那个
—— currency「标注是符号位置,规范化后无可判值」、bank/account
「真值存在但 2% 覆盖率进不了封箱集」、buyer_tax_id / PO「DocILE 无此
fieldtype」(这条我复核为真)。

**评分处置**:E 仍 19/20,不额外扣分 —— 记分的是 TIER1 指标表本身(未变、
且质量高),这份文件是佐证材料。但登记为 `benchmark_integrity_findings`:
**这是全仓唯一一个我复算不出来的数字,而且它恰好在为满足 rubric 而写的
文件里。** 按 GOAL.md 优先级 2(可复算 > 完备),这条比丢 1 分严重。
不改就带着进提交,任何动手核的评委会看到我看到的东西。

E 的另一半扣分(与上轮口径衔接):记分层不含任何 KILE/LIR 形态的指标
(AP/F1),line item 完全不在 schema 内 —— 「DocILE 相关指标」的相关性
限于表头字段正确性。措辞仍然正确(从未自称 official benchmark score)。

---

## 四、未变项的说明

- **B 正常路径 1/2**:文档触达率仍 100%,HITL run-0002 实测 120/120 槽全部
  经人裁决。`absent_expected` 会造出第一条真正的零触碰路径,但它是 HAR-0003
  **候选**,默认策略仍 HAR-0001。上轮建议不变:**不要为这 1 分造假路径。**
- **H 可推广 1/2**:`FIELD_COVERAGE.md` §产品层与记分层 说明了**字段**可扩
  (「冻结、门禁、绑定、路由、审计机制与字段无关」),但跨**文档类型**
  (receipts / PO / claims)既未主张也未演示。这是最后一个便宜分。
- **G5 时间线**:**已由用户决定退役,不再作为风险登记**(2026-08-06)。
  本仓库从未上传过 GitHub;开赛后走全新 repo(或在新 repo 里做一个新
  文档域的功能),本仓库作为赛前既有研究资产存在。G5 本就是
  `REQUIRES_HUMAN_CONFIRMATION`、从不影响分数,**93/96 不变**。
  唯一保留的建议:新 repo 里把 dws-derisk 六轮实验与本仓库如实标注为
  「赛前既有研究」,引用而不冒充窗口内产物 —— 这与宪章六同一条纪律。

---

## 五、剩余 ROI(合计 +3 → 96/96)

| # | 动作 | 分 | 说明 |
|---|---|---:|---|
| 1 | 修 `FIELD_COVERAGE.md` 的三个数字 | 0 | **不加分,但优先级最高** —— 见 §三 |
| 2 | 把封箱集基线表写进 docs/ | 0 | README:126 引用的 9.62% vs 21.91% 目前**只存在于脚本输出**,docs/BASELINE_COMPARISON.md 仍是旧留出集的表。数字我复现了,但评委得自己跑脚本才找得到 |
| 3 | E:补一个 KILE 形态指标,或明写「line item 不在范围内及其理由」 | +1 | 后者成本几乎为零 |
| 4 | H:一段设计主张 —— 这套机制适用于任何「支持关系是几何的」文档域,并说明 receipts/PO 为什么落在里面 | +1 | README:20 已有半句论证,补全即可 |
| 5 | B:等 HAR-0003 走完资格流程再谈零触碰 | +1 | 不建议为分提前 |
