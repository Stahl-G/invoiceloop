# InvoiceLoop

**发票抽取的支持关系,不是发票抽取的正确性。**

> **One-line pitch (EN):** InvoiceLoop turns Nutrient DWS invoice extraction
> into a verifiable support matrix — every field is bound to page evidence,
> checked by deterministic gates, and routed to a human only when the
> machine cannot vouch for it — with a tamper-evident audit trail and a
> guarded improvement loop that safely reduces review load over time.
> *(English quickstart: see [安装 / Install](#安装).)*

每个抽出的字段带一条可机械验证的支持关系:它绑定到页面上哪块区域、
那块区域的独立 OCR 说了什么、旁边印的标签是什么、六个确定性门禁各自的裁决、
以及在哪里说不准。

## 谁在用,错一个字段代价是什么

第一用户是 **AP(应付账款)记账员**:他们今天的动作是逐张发票、逐个
关键字段肉眼核对后再入 ERP。InvoiceLoop 替代的不是"看发票",而是
**"确认那些机器已经能担保的字段"** —— 人只看机器担保不了的部分。

关键字段错了不是小事,是钱和合规:

- `total_gross` / `amount_due` 错 → **错付**(多付或少付,事后追回成本
  远高于事前拦截);
- `invoice_number` 错或重复 → **重复付款**(同一张票付两次,AP 最常见的
  资金损失之一,跨文档查重 C8 抓的就是它);
- `seller_vat_id` 错 → **税务申报问题**(抵扣凭证上的税号错,审计时
  整批要回退);
- `seller_name` / `buyer_name` 错(买卖双方抽反,实测案例)→ **付款
  对象错误**,比金额错更难追。

第二用户是**审计人员**:交付物里的每个值都能回答"凭什么信它",
而且这个回答可以被离线重算(四层 verify + 带外 sha256 锚)。

## 落地路径:deliverable.json 怎么进 ERP/AP

每个 run 产出 `deliverable.json` —— 逐字段 `{value, status, source}`,
整单 `{released / released_with_caveats / pending / blocked}`:

- **released / released_with_caveats** → 下游 AP/ERP 直接入账
  (status 为 accepted/corrected/policy_accepted 的字段带值;
  confirmed_absent/policy_confirmed_absent 显式为空);
- **pending / blocked** → 留在复核队列,不落下游;
- 集成形态是**单文件契约 + 本地服务**:零 SDK 依赖,ERP 侧定时拉取
  workspace 的 deliverable.json,或一个 webhook 适配器转发
  (workbench 是 stdlib http.server,嵌进任何内网);
- `source` 字段让每个进 ERP 的值可追溯到冻结声明 / 人工裁决 /
  策略版本 —— 审计问询时不用再翻发票。

人工负载实测(SEALED-1,100 份封箱集):放行决策负载从 82.9% 降到
64.2%(HAR-0002,取消无冲突 TIER1 强制确认),安全性同证据配对无劣化;
改进循环(absent_expected cohort 等)继续把重复确认转成策略。

## 成本与延迟(实测,非估算)

- **DWS credits**:understand 均值 ≈20/次、agentic ≈31/次;
  100 份封箱集 200 次调用实耗 4,953 credits(≈49.5/份,双模式);
- **延迟**(750 份存盘响应的 `processingTimeMs` 实测):
  understand 中位 **9.1s**(p95 31.6s),agentic 中位 **11.9s**
  (p95 35.5s),两模式串行 ≈ **21s/份**;本地门禁/冻结/矩阵为毫秒级,
  不构成瓶颈;
- **为什么两模式恒调、不做动态降档**:双模式分歧本身是六道门禁之一
  (cross_mode_agreement),省掉 agentic 就等于拆掉这道门 —— 
  成本是信号的一部分,不是浪费。

## 它不做什么

不承诺抽得准。在 DocILE 语料上的六轮预注册实验与 100 份留出集复核
(`~/Developer/dws-derisk/`)发现:没有任何单一信号 —— 厂商置信度、算术一致性、
双模式分歧、独立 OCR 引用、前沿模型读图 —— 能识别所有后果严重的抽取错误。

InvoiceLoop 因此把 DWS 抽取与证据绑定、确定性检查、聚焦人工复核组合起来:
交付物是**支持矩阵**,不是判决。

## 为什么是发票

商业简报的支持关系是语义的,验不了。发票的支持关系是**几何的** ——
bbox 与页面区域的关系,可以用独立 OCR 逐词验证。

## 血统

BriefLoop 架构参考 v0.6.1 §3.6 支持充分性栈。该栈在 BriefLoop 中被标为实验性,
语义门禁 §8.4 明写"尚未交付"。InvoiceLoop 在一个支持关系可机械验证的域里实现它。

## 状态

M0–M4 全部落地,两轮外部验证完成:

- **SEALED-1 封箱评测(2026-08-05,`docs/SEALED1_RESULTS.md`)**:
  drand 信标播种的 100 份真未见集,分诊 lift 4.03×(线 1.5),H1–H4/H7 过,
  H5/H6 未过线照登不调判据;证据包 sha256 带外公布;
- **验证轮(2026-08-02,`docs/VERIFICATION_2026-08-02.md`)**:
  旧留出集 H1–H6 全过(lift 3.04×),人类验收五任务通过;
- **改进层在环**:routing 策略版本化(Harness),人工晋升带 PROM 哈希链,
  无冲突 TIER1 策略放行实测放行决策负载 −18.7pp(SEALED-1 第二臂);
- **测试套件 370 全绿**:第六轮错位事故 454 行回归、对拍 dws-derisk
  搬运保真、攻击链回归(promote 绕评/伪造指针/协调篡改全部钉死)。

## English

**What it is.** InvoiceLoop is a verification and review layer on top of
Nutrient DWS invoice extraction. It does not claim extraction is correct —
it makes every extracted field answerable: which page region it binds to,
what an independent OCR says about that region, what six deterministic
gates found, and where the machine admits it does not know. Fields the
machine cannot vouch for go to a focused human queue; everything is
recorded in an append-only, hash-chained audit trail that verifies offline
(four layers, single-byte tamper-evident).

**Why it matters.** Wrong `total_gross`/`amount_due` = mispayment; wrong or
duplicated `invoice_number` = paying twice; wrong `seller_vat_id` = tax
filing exposure. InvoiceLoop routes those risks to humans and lets the
rest flow — measured on a drand-seeded sealed set of 100 unseen invoices
(docs/SEALED1_RESULTS.md).

**Quickstart (zero API, self-contained):**

```bash
pip install -e ".[dev]" && python3 -m invoiceloop doctor
python3 -m invoiceloop demo --out demo-ws
python3 -m invoiceloop workbench --workspace demo-ws   # http://127.0.0.1:8765
```

Numbers you can recompute: triage lift 4.03× on the sealed set
(pre-registered thresholds), TIER1 silent-error 9.62% vs 21.91% for a
confidence-threshold baseline at a fixed operating point
(table: docs/BASELINE_COMPARISON_SEALED1.md), decision load
for release 82.9% → 64.2% under the promoted HAR-0002 policy — all from
stored evidence, no API calls needed to verify.

## 安装

```bash
python3 -m venv .venv && source .venv/bin/activate   # macOS 系统 Python 拒全局 pip(PEP 668),先建 venv
pip install -e ".[dev]"          # 或 pip install . 只装运行时(仅 requests 一个 PyPI 依赖)
python3 -m invoiceloop doctor    # 环境自检:缺什么说什么,产品路径不齐 → 退出码 1
```

系统依赖:poppler(`pdftotext`/`pdftoppm`,macOS `brew install poppler`);
tesseract 可选(扫描件退路,没有它扫描件按宪章四阻断而不是静默跳过)。

研究路径(`heldout`、校准复算、`run --out` 读存盘证据)另需 sibling 校准档案
`~/Developer/dws-derisk`(`INVOICELOOP_CORPUS` 指向它);产品路径(workspace 全流程、
demo、workbench)完全不需要它 —— 仓库自包含。
研究测试(对拍 / 分诊集中度 / e2e)缺校准档案时自动跳过,评审机上约 40 条
skip 属预期,不是失败。`heldout` 命令在运行时把 sibling 仓库插进 `sys.path`,
换机即断,属开发侧工具,不走产品路径。

```bash
# 两分钟 demo:内嵌示例语料跑通全流程 —— 零 API、零外部数据、零 sibling 仓库
python3 -m invoiceloop demo --out demo-ws
python3 -m invoiceloop workbench --workspace demo-ws   # http://127.0.0.1:8765 网页复核

# 自己的发票:PDF 丢进 workspace/input/pdfs/(输入契约 §12)
python3 -m invoiceloop ingest --workspace ws/    # 本地独立 OCR + DWS 抽取(需 DWS_API_KEY)
python3 -m invoiceloop run --workspace ws/ --crops   # 产出在 ws/runs/run-NNNN(不可变,panel 标注「不在校准集内」)
# 同一份输入再跑 = 重放既有 run;输入变了自动开新代;--new-run 强制新代。旧 run 永远原样保留。

# 人工裁决(append-only,绑定完整复核快照)与交付(全量自包含 bundle)
python3 -m invoiceloop adjudicate --run demo-ws/runs/run-0001 --doc <doc_id> --field total_gross \
  --claim-id FC-0042 --decision accept --rationale "证据齐" \
  --adjudicator <名字> --decided-at 2026-08-02T10:00:00
#   二次决定同一字段须显式 --supersedes HD-0001;裁决后 panel 自动重渲(失败不丢裁决)
python3 -m invoiceloop render --run demo-ws/runs/run-0001   # 随时从盘上工件重建 panel(纯投影)
python3 -m invoiceloop bundle --run demo-ws/runs/run-0001   # 全量自包含:上游 PDF/OCR/raw + 全部派生物
python3 -m invoiceloop verify demo-ws/runs/run-0001/audit_bundle.zip   # 离线三层校验:单点篡改(任一成员/哈希/快照/绑定)必被对应层抓住;包的真实性锚在带外公布的本包 sha256

# H1 复核工作台:网页上直接复核 —— 每行四个决策按钮 + 修正值 + 问题/理由输入域
python3 -m invoiceloop workbench --workspace ws/   # http://127.0.0.1:8765,仅本机 loopback
# 上传 PDF → ingest → 复核队列(任务行+证据裁剪图+OCR+标签,默认摊开)→ 裁决(自动带 supersession)
# → 交付报告(复核完成度+修正清单+残余风险声明)→ 打 bundle / 离线 verify

# 读图(可选):整页渲染 → 读图模型作答 → 复核队列出现「读图建议」预填块
python3 -m invoiceloop vision --workspace ws/    # 需 ANTHROPIC_API_KEY;作答是草稿,进输入指纹
# 建议只预填表单:一致 → 「采用建议」一键填入(人仍要点提交);分歧 → 摊开各读者的值
# OCR 受阻的文档上,读图是唯一幸存的机器信号(实测:它标中了 DWS 抽反的买卖双方)
# run 会捕获 answers6.*.tsv 到本地工件;工作台与 bundle 不依赖之后可变的 vision 目录

# 测试
python3 -m pytest tests/

# ── 研究路径(开发侧)────────────────────────────────
# 以下命令读校准档案(~/Developer/dws-derisk,由 INVOICELOOP_CORPUS 指向;
# 历史别名 INVOICELOOP_DWS_DERISK 仍有效)。评委与产品路径都不需要它们:
python3 -m invoiceloop run --out runs/demo --crops        # 160 份校准存盘证据的全流程
python3 -m invoiceloop heldout plan --workspace runs/heldout-workspace
python3 -m invoiceloop heldout extract --workspace runs/heldout-workspace --budget 6000
```

打开 `demo-ws/runs/run-0001/support_panel.html` —— 静态、离线、无需服务。
复核队列按支持强度升序、分「需要裁决」与「印证行(抽检)」两节:
队首就是系统明确表示自己不知道的地方;每行有任务行(核什么、DWS 读到什么),
门禁 chip 悬停有一句话解释(查什么、这状态意味着什么)。

文档:`ARCHITECTURE.md`(设计契约)/ `GOAL.md`(冲突时优化什么)/
`docs/VERIFICATION_2026-08-02.md`(验证轮总录)/ `docs/HELDOUT.md`(留出集协议与结果)/
`docs/H0_INTEGRITY_2026-08-03.md` + `docs/H1_WORKBENCH_2026-08-03.md`(完整性地基与工作台两轮)/
`docs/TESTING.md` + `docs/TESTING_FACILITATOR.md`(人类验收协议与主持包)。

校准语料与六轮实验证据:`~/Developer/dws-derisk/`(`REPORT.md` / `THRESHOLDS.md`)。
本仓库引用的每个数字都可从该仓库零 API 重算。
