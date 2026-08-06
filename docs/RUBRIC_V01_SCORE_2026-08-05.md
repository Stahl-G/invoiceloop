# Rubric v0.1 评分(2026-08-05,evaluated_commit 5567241)

判据:`docs/HACKATHON_RUBRIC_v0.1.md`(冻结于 5567241,先于本次打分)。
**用户决定:demo reel 相关分项不计**(距黑客松开始 12 天,录屏尚不存在)——
I 的「2–4 分钟端到端 demo」(3)与「同时展示 clean 与 risky case」(1)共 4 分
从分子分母同时删除;G4 只核 repo/setup/DWS heavy-lifting 说明,不核视频,
因此不触发「提交材料不完整」的 89 分上限。**满分基数 96。**

**结果:86 / 96(89.6%)。** 分档:Strong contender 顶格,贴到 90 线。

评分者自陈的限定见 rubric 文件头「冻结纯度限定」:本次打分者与冻结者是
同一会话,`CLAUDE.md` 的成果声明在冻结前已进上下文。

---

## 一、资格门

| Gate | 判定 | 证据 |
|---|---|---|
| G1 DWS 核心使用 | **PASS** | `invoiceloop/dws_client.py:20` 直调 `api.nutrient.io/extraction/extract`,schema 驱动 + understand/agentic 双模式;`invoiceloop/samples/raw/*.understand.json` 是真实响应记录(`requestId` / `apiVersion 2026-05-25` / `processingTimeMs`);字段草稿**只**来自 DWS(`field_ledger.json` 的 `drafted_by` ∈ {dws_understand, dws_agentic});DWS 的 `metadata.bbox` 是裁剪、区域 OCR 与冻结绑定的输入(`evidence_span_registry.json` 的 `source: "dws_source_bbox"`) |
| G2 证据诚信 | **PASS** | 真值只在 `scripts/{baseline_comparison,heldout_metrics,build_exposure_manifest}.py` 里读;`invoiceloop/` 运行时零真值(`heldout.py:53` 用 annotations 仅做选样,`ocr.py:76` 仅做语料布局探测)。反向证据充分:H5/H6 未过线照登不调判据(`docs/SEALED1_RESULTS.md:27-28`);基线口径重写后自己的优势变小仍照登(`docs/BASELINE_COMPARISON.md:82`);41.8% 被自己否掉并改报 61.2%/100%/82.3%(`docs/R0_BASELINE_2026-08-05.md:23-28`) |
| G3 真实端到端运行 | **PASS** | 本次亲自跑通:`demo` → 3 份文档 30 槽 → 复核队列 → `adjudicate`(生成 HD-0001,绑定 review_snapshot `9f722f46…`)→ `bundle`(48 成员)→ `verify` 四层全过;翻转包内一个字节后 `members: false` 且精确点名 `pages/002e3cf9…-1.png`,其余三层仍 true |
| G4 提交完整性(去视频) | **PASS(部分)** | public repo + `README.md:41-98` setup + DWS 角色说明齐全。缺英文一句话 pitch;README 全中文 |
| G5 时间线合规 | **REQUIRES_HUMAN_CONFIRMATION** | 74 个 commit 全部落在 2026-08-02 至 08-05,赛程为 08-17 至 09-03 —— **现有全部工作在窗口之前**。agent 不判违规,但这是当前最大的结构性风险,需要一份「既有组件 vs 窗口内新增」披露 |

---

## 二、分项

| ID | 维度 | 得分 | 满分 |
|---|---|---:|---:|
| A | 真实问题与项目概念 | 8 | 10 |
| B | 项目进展与端到端执行 | 11 | 12 |
| C | 落地与创业可行性 | 4 | 8 |
| D | Nutrient DWS 集成深度 | 15 | 15 |
| E | 可靠性改进与实验证据 | 19 | 20 |
| F | 风险路由与 Human-in-the-Loop | 13 | 13 |
| G | 审计、来源与可回放性 | 10 | 10 |
| H | 创新性与差异化 | 4 | 5 |
| I | 提交材料(去 demo reel) | 2 | 3 |
| | **合计** | **86** | **96** |

Round proxy:Overall(A+B+C)23/30;Sponsor(D+E+F+G+H)61/63;Submission 2/3。

### A. 真实问题与项目概念 8/10 — `IMPLEMENTED_AND_VERIFIED`

- 明确目标结果 **2/2**:`GOAL.md:13` 「不是让抽取变准 —— 六轮实验已经证明做不到……是让『不准』可见、可定位、可分级」。这正是 rubric 要的目标形态。
- 与挑战主题匹配 **2/2**:`README.md:3` 「支持关系,不是正确性」;`README.md:20` 论证为什么发票的支持关系是几何的、可机械验证。
- 明确用户与工作流 **2/3**:有「复核者 / adjudicator」角色(裁决记名入账),但没有指名 AP clerk / 财务审核人 / 审计人员,也没有描述发票进入付款流程的上下游。**扣 1。**
- 明确错误代价 **2/3**:`fields.py:42` 「T1 错了是要命的」是分层依据,但全仓找不到一句「错在哪会导致什么」——错付、重复付款、税号错导致的申报问题都没写。**扣 1。**

### B. 项目进展与端到端执行 11/12 — `IMPLEMENTED_AND_VERIFIED`

- 完整核心流水线 **4/4**:本次亲跑,见 G3。
- 异常路径 **3/3**:三类真实拦截,全部可复现 ——(a) `046e0c49` 无文字层且无 tesseract → 按宪章四阻断而非静默跳过(本次复现);(b) `docs/LIVE_TEST_2026-08-05.md:76-79` agentic 把 seller_vat_id 抽成 `58-0391482`(末位错一位),冻结绑定当场拒绝;(c) `docs/LIVE_TEST_2026-08-05.md:30-34` C8 跨文档查重首战抓到同号不同日的两份。
- 可复现运行 **3/3**:本机 `python3 -m pytest tests/` = **357 passed**(43s,零 skip);`scripts/fresh_venv_check.sh` 干净 venv 评委门;`doctor` 缺件即退 1。
- 正常路径 **1/2**:**扣 1。**「clean invoice 成功完成自动处理」在产品形态上不存在 —— 文档触达率两臂均 100%(`docs/SEALED1_RESULTS.md:54`、限定清单第 2 条),本次 demo 三份文档零裁决时全 `pending`。这是设计决定且已披露,不是缺陷,但 rubric 这一子项确实没有可计分的实例。

### C. 落地与创业可行性 4/8 — 最弱项

- 隐私与安全 **2/2**:`dws_client.py:7,39-41` key 只从环境变量读、绝不落盘;`docs/H1_WORKBENCH_2026-08-03.md:69` 把「写端点无 Host/Origin 校验可烧 credits、伪造裁决」列为 critical 并已修(Host 白名单 + POST Origin 403);全部处理在本机 loopback。
- 部署与集成路径 **1/2**:`deliver.py` 产出 `deliverable.json`(逐字段 status + caveats),形状适合下游消费,但没有任何一句说它如何进 ERP/AP。**扣 1。**
- 成本与延迟 **1/2**:credits 报得很准(`docs/HELDOUT.md:20` understand 均值 19.7/次、agentic 31.5/次;SEALED-1 实耗 4,953/200 次)。**延迟从未报过**,只在 v0.2 设计里作为计划出现。**扣 1** —— 但数据其实已经在盘上,见下方 ROI-2。
- 商业采用逻辑 **0/2**:`NOT_FOUND`。谁付费、替代哪个人工步骤、为什么不是只能展示的 demo —— 全仓无对应内容。按「不得根据架构图推断功能存在」计 0。

### D. Nutrient DWS 集成深度 15/15 — `IMPLEMENTED_AND_VERIFIED`

- 承担核心操作 **5/5**;结构化证据 **4/4**:span 记录同时带 `page` / `bbox_rel` / `ocr_text`(该区域的独立 OCR)/ `printed_label` / `source: dws_source_bbox` / `crop_sha256` —— DWS 的坐标被用来**裁图并交叉验证**,不是只读字符串。
- 输出驱动决策 **3/3**:understand/agentic 双模式分歧是六门禁之一;citation 门按 DWS bbox 判;绑定拒绝有实例(`FC-0012` 的 rejections 里 agentic 草稿 `83519` coverage 0.0 被拒)。
- 差异化能力 **3/3**:source grounding 被用到底。只用 Extraction API、未用 Viewer/Processor/签名 —— 按 rubric「一个 API 用得深优于三个装饰性调用」**不扣**。
- 三条限分条件逐条不触发:不是只做 PDF→文本;结果参与决策;换掉 DWS 则双模式门与 bbox 绑定同时失效,产品行为会变。

### E. 可靠性改进与实验证据 19/20 — 全项最强

- Held-out 设计 **4/4**:SEALED-1 用 drand 轮次 6350076 播种,承诺 commit `979fd37` 先于开奖、名单 commit `f3594ce` 先于任何 DWS 调用,与 260 份暴露清单及旧留出 100 零交集,`heldout.sealed_list(seed)` 独立复算逐份一致(`docs/SEALED1_RESULTS.md:4-8`)。这比 rubric 的要求高一档。
- 原始基线比较 **4/4**:四方对照(raw 全信 / 有值才放行 / confidence≥0.95 / 双模式)+ InvoiceLoop,且 2026-08-05 重写了比较合同,把「让对手借用 InvoiceLoop 闸门」的旧口径修掉 —— 修完之后自己的相对优势变小仍照登。
- 风险—覆盖—人工负载 **4/4**:三者同表(`docs/BASELINE_COMPARISON.md` TIER1 285 槽:静默错误 8.98% / 覆盖 58.6% / 复核负载 41.4% / 路由召回 82.4%),另有 10/20/30/40% 预算曲线与按文档 bootstrap CI。
- 错误分析与 ablation **2/2**:C3 修复与 C8 首检出逐槽定位;HAR-0001 vs HAR-0002 是同一份冻结证据上只换策略的真 ablation(放行决策负载 82.9%→64.2%,安全指标未劣化)。
- 统计诚实 **2/2**:H5(15.3% vs 线 15%)、H6(36.6% vs 上界 35%)未过线照登、不退役不调判据;「不主张」四条明写。
- 关键字段指标 **3/4**:**扣 1。** 记分字段只有 10 个,rubric 建议的 `currency` / `buyer_tax_id` / `purchase_order_number` / `payment_or_bank_details` 全不在内,且仓库没有一句说明为什么它们不属于关键字段。字段集是六轮预注册冻结的、不是看完结果挑的(这是 rubric 最在意的作弊面,已守住),但覆盖缺口本身仍是缺口。DocILE 口径措辞正确 —— 未使用官方 evaluator,也从未自称 official benchmark score。

**Pareto 判定**:满足 rubric 的第 1 条 —— 同人工预算下静默错误/召回更优,SEALED-1 预注册 paired CI 在 20–40% 预算段下界 > 0(+23.8 / +22.2 / +28.4pp)。不满足支配关系(覆盖 58.6% vs confidence 91.6%),项目自己也未主张。**不触发 11/20 的封顶。**

### F. 风险路由与 HITL 13/13 — `IMPLEMENTED_AND_VERIFIED`

- 字段重要性 **4/4**:`fields.py:43-46` TIER1/TIER2;`routing.py:103-109` `release_tier1_explicit`;`deliver.py:130` TIER1 未显式裁决 → `pending_tier1`。
- 不只依赖 confidence **3/3**:六个确定性门禁(算术恒等、日期时序、wellformed、citation 绑定、双模式、读图),且项目明写 confidence「是粗粒度 grounding score(0.95/0.4 两档),**不是校准正确率**」(`docs/BASELINE_COMPARISON.md:31-33`)—— 正是 rubric H 项想看到的洞察。
- 文档内复核体验 **3/3**:`workbench.py:19-20,875-913` 整页渲染 + bbox overlay(冻结绑定绿实线 / DWS 引用紫虚线),队列行带证据裁剪图 + 区域 OCR + 印刷标签。
- 修改批准与回退 **2/2**:append-only 裁决账本,`decision_id` / `review_snapshot_id` / `adjudicator` / `rationale` / `supersedes`;abstain = 未决且**不许带着放行**(`docs/LIVE_TEST_2026-08-05.md:57-59` 实测 26 条裁决后仍全 pending,直到 12 条显式 supersession 才 released)。
- 防止 review-all **1/1**:HAR-0002 在同一份冻结证据上把放行决策负载砍 18.7pp 且安全指标未劣化。**但登记限定:文档触达率仍 100%,系统降低的是「每份要看多少」,不是「要看多少份」。**

### G. 审计、来源与可回放性 10/10 — `IMPLEMENTED_AND_VERIFIED`

五个子项全部亲验:`input_manifest.json`(pdf/ocr/raw/schema 各自 sha256 + fingerprint + execution_fingerprint)/ `routing_report.json` 内嵌策略全文与 `policy_digest`(`routing.py:126-138`:必须按**本次 run 的策略**重放,晋升后旧 run 的说法不许变)/ span registry 的 page+bbox+crop_sha256 / 我自己写入的 HD-0001 / `bundle`+`verify` 四层 + 单字节篡改被 members 层精确点名。rubric §G 给的理想字段记录形状,这里是超集。

### H. 创新性与差异化 4/5

- 不只是 wrapper **2/2**;技术洞察 **1/1**(confidence 无区分度这条是测出来的,不是说出来的:本批 DWS 非空值全 0.95 档)。
- 可推广的 trust architecture **1/2**:**扣 1。** `README.md:20` 明确论证发票之所以可做**正是因为**支持关系是几何的、语义域(商业简报)验不了 —— 这是诚实的边界声明,但同时意味着向 receipts/PO/claims 的推广既未主张也未演示。

### I. 提交材料 2/3(demo reel 分项已删除)

- 官方材料齐全 **1/2**:repo + setup + DWS 说明齐;缺英文一句话 pitch,README 全中文。**扣 1。**
- 指标诚实且易懂 **1/1**:诚实这半边满格。但登记:对外部评委而言可读性差 —— 24 份 docs、无一屏总结、无英文。

---

## 三、上限核查

| 上限条件 | 是否触发 |
|---|---|
| 无真实端到端运行(59) | 否 —— 本次亲跑全链路 |
| 无 held-out / 无 raw DWS baseline(69) | 否 —— SEALED-1 + 四方基线 |
| 无人工异常处理路径(74) | 否 |
| 无可验证审计轨迹(84) | 否 —— verify 四层 + 篡改对照 |
| 提交材料不完整(89) | 不适用 —— 视频分项按用户决定删除 |

`final_score = min(86, ∞) = 86 / 96`。

---

## 四、最高 ROI 的下一步

按「每分投入产出」排序。**前四项全部不碰证据层,只写文档。**

| # | 动作 | 预计得分 | 依据 |
|---|---|---:|---|
| 1 | README 加一节:谁付费、替代哪个人工步骤、`deliverable.json` 如何进 ERP/AP | **+3**(C 商业 0→2,部署 1→2) | 当前 `NOT_FOUND`,是全表唯一的 0 分子项 |
| 2 | 公布延迟 —— **数据已经在盘上**,每个存盘响应都有 `body.metrics.processingTimeMs` | **+1**(C 延迟 1→2) | 本次实算 721 份存盘响应:understand 中位 9.1s / p95 31.6s;agentic 中位 11.8s / p95 35.5s;两模式串行 ≈ **20.9s/份**。补一句「两模式恒调,不做动态降档,因为双模式分歧本身是门禁信号」即可说清模式策略 |
| 3 | 英文一句话 pitch + README 英文段 | **+1**(I 1→2) | 评委语言 |
| 4 | A 项补两句:指名角色(AP clerk / 审计)+ 错误代价(seller_vat_id 错 → 申报问题;total_gross 错 → 错付) | **+2**(A 8→10) | 项目实际就是为这个建的,只是没写 |
| 5 | 在 SEALED-2 之前声明为什么 currency / buyer_tax_id / PO / bank details 不在记分字段集内 | **+1**(E 19→20) | 必须**事前**声明 —— 事后补等于 rubric 点名的挑字段 |
| 6 | 用一份非发票文档(收据/PO)跑一次,或把推广边界写成设计主张 | **+1**(H 4→5) | 二选一即可,后者成本更低且更诚实 |

合计 **+9 → 95/96**,且不需要动可靠性证据层。

**明确不建议做的**:为了 B 的「正常路径」造一条零触碰自动放行。文档触达 100% 是
SEALED-1 照登的限定,砍掉它换 1 分,等于用宪章六换分。宁可丢这 1 分。

**优先于以上全部**:G5 时间线披露。74 个 commit 全在 08-02 至 08-05,
赛程 08-17 起。这不影响本表任何分数,但它是唯一可能让分数整体作废的东西。
