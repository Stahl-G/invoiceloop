# InvoiceLoop 架构设计 v0.1

> **血统**:BriefLoop 架构参考 v0.6.1(`main@47ae439d`)。InvoiceLoop 把它的
> **支持充分性栈**(§3.6)搬到发票抽取 —— 那一格在 BriefLoop 里被标为实验性,
> 语义门禁 §8.4 明写"尚未交付"。
>
> **证据基础**:`~/Developer/dws-derisk/` 六轮预注册实验,160 份 DocILE 发票,
> 320 次 DWS 调用,五个读图模型。本文件引用的每个数字都可从该仓库零 API 重算。

---

## 0. 论点

**抽取的正确性不可信,支持关系可验证。**

六轮实验证明:在 DWS 上,抽错的时候没有任何可用手段知道它抽错了 —— 包括厂商置信度、
确定性校验、双模式分歧、独立 OCR、以及五个前沿模型的读图。四个判据、六轮、
两种取景,全部失败。

InvoiceLoop 因此**不承诺抽得准**。它承诺的是:每个字段带一条**可机械验证的支持关系**,
以及一个诚实的"我们凭什么这么说、哪里说不准"。

**发票是这件事最好的试验场。** 商业简报的支持关系是语义的(验不了);
发票的支持关系是**几何的** —— bbox 与页面区域的关系可以用独立 OCR 逐词验证。

---

## 1. 宪章

继承自 BriefLoop §1.1,只保留本域适用的条款。

**一、同一个字段只许有一个写者。**
Python 写控制状态、证据注册、声明 ID、冻结、门禁、事件、哈希;
模型写字段草稿与读图提案;人类写裁决与交付决定。派生投影不得反向覆盖权威记录。

**二、有来源,不等于被支持;能追溯,不等于被证明。**
DWS 返回一个 bbox,只说明它"看了那里",不说明那里支持这个值。
第三轮实测:共享 bbox 的字段准确率 79.7%,独占 bbox 的 60.6% —— **方向与直觉相反**。
支持必须按强度、来源层级、适用范围分别记录,不能压成一个分数。

**三、机器能管的,不交给记忆。**
能由 schema、验证器、门禁、事务检查的规则,不得只写在提示词或交接说明里。

**四、冻结工件不能静默改写,缺口不能被隐藏。**
检查跑不了 = 高危阻断发现,不是跳过。DWS 没返回值的字段是**阻断**,不是"负载成本"。

**五、语义未解决的冲突保持显式,进入人工裁决,不进错误率。**
纸面印 `Gross Billings` 而标注要 `Net Amount Due` —— 这是口径冲突,不是抽取错误。

**六、不说工件证明不了的话。**
只有可追溯性时,不得宣称语义证明或质量提升。未测量的能力写成"尚未测量"。

---

## 2. 单一写者

| 写者 | 拥有 | 不得触碰 |
|---|---|---|
| **Python 控制面** | 运行状态、证据片段注册表、声明 ID、冻结账本、门禁裁决、事件、哈希 | 字段值本身(只验证,不发明) |
| **模型(读图/抽取)** | `field_drafts.json` —— **无 ID、无权威** | 账本、ID、门禁结果、事件 |
| **人类** | 裁决记录、交付批准 | 已冻结运行的输入 |

**`field_drafts.json` 与 `field_ledger.json` 是两个工件**,与 BriefLoop 的
`claim_drafts` / `claim_ledger` 同理:模型只能提交草稿,Python 分配稳定 ID 并冻结。

> **这一条不是形式主义。** 第六轮实测:一个读图模型把 359 行答案错位绑定到别的发票,
> 63.1% 的作答内容出现在其他文档上。若模型只能提交草稿、由 Python 校验绑定,
> 那次错位的 **66% 会被结构性拒绝**,而不是靠事后 OCR 取证发现。

---

## 3. 四条控制骨干

```
① 运行状态    run_manifest.json → run_state.json → artifact_registry.json → event_log.jsonl
② 证据与声明  dws_response → evidence_span_registry.json → field_claim_graph.json
                → field_drafts.json →【冻结事务】→ field_ledger.json
③ 门禁        六个确定性门禁 → gate_report.json(evaluations + findings)
④ 裁决与交付  adjudication_ledger.jsonl → support_matrix.json → support_panel.html
```

BriefLoop 有五条骨干,InvoiceLoop 只需四条:记忆与改进骨干(跨运行学习)
对单张发票的 demo 不适用。

---

## 4. 数据模型

### EvidenceSpan —— 证据片段
```python
span_id: str            # ES-#### ,Python 分配
doc_id: str
page: int
bbox_rel: tuple         # 归一化 (x0,y0,x1,y1),桥接 DWS 像素空间与渲染空间
crop_sha256: str        # 裁剪图内容哈希
ocr_text: str           # 该区域独立 OCR 文本(DocILE 词级 OCR)
printed_label: str      # 值旁边印着的标签原文,如 "Gross Amt:"
source: str             # dws_source_bbox | full_page
```

### FieldClaim —— 原子声明
```python
claim_id: str           # FC-#### ,Python 分配,草稿不得预写
doc_id: str
field: str              # invoice_number | total_gross | ...
value: str              # 规范化前的原文
normalised: str         # 按预注册规则规范化后
span_ids: list[str]     # 绑定的证据片段
drafted_by: str         # dws_understand | dws_agentic | vision:<model>
```

### 原子声明图的**边**
发票的声明图比简报实:边是可验证的算术恒等式,不是语义关联。
```python
("total_net", "total_vat") --sum--> "total_gross"      # C1
"total_gross" --equals--> "amount_due"                 # C2
"issue_date" --before--> "due_date"                    # C3
```

### SupportRow —— 支持矩阵的一行(四维,不是一个分数)
```python
claim_id: str
support_strength: "corroborated" | "single_source" | "unsupported"
source_tiers: list      # dws_extraction / independent_ocr / vision_reading / arithmetic
applicability: "matches" | "label_convention_disputed" | "out_of_scope"
limitations: list[str]
requires_adjudication: bool
gate_verdicts: dict     # gate_id -> pass | warning | fail | unavailable
```

**"适用范围"这一维是给口径冲突准备的。** 证据可以完全支持一个值,
而争议在于"纸面的 Gross"与"EN 16931 的 gross"不是同一个概念。
六轮把这类算进错误率,是把两件事混为一谈 —— 第五轮 20 例共错里 5 例是这个形状。

### GateFinding
```python
finding_id, gate_id, severity, blocking_level      # 照 BriefLoop 契约
repair_owner: "human" | "re_extract" | "vision_reread"
recommendation: str
evidence_ref: str                                   # 指向 span_id 或 claim_id
```
契约不变量:`blocking == (blocking_level == "blocking")`。

---

## 5. 三个控制事务

### 5.1 抽取事务 `extract`
调 DWS → **原始响应按内容哈希冻结为工件** → 从 `source_bboxes` 注册证据片段 →
渲染裁剪图与整页 → 建原子声明图。

产出:`artifact_registry.json` 一条记录 + `evidence_span_registry.json` + 事件。

### 5.2 冻结事务 `freeze` —— 系统的关键防线
| 步 | 写者 | 动作 |
|---|---|---|
| 1 | 模型 | 写 `field_drafts.json`,**不含 claim_id** |
| 2 | Python | 拒绝预写 ID;拒绝无法绑定到已注册片段的行 |
| 3 | Python | 分配稳定 `FC-####` |
| 4 | Python | 冻结 `field_ledger.json` + sha256,追加事件 |

**第 2 步的绑定规则(可执行,非声明):**

> 草稿行声明 `(doc_id, field, value)`。Python 检查该 `value` 是否出现在
> **该 `doc_id` 整份文档**的独立 OCR 文本中(规范化后 token 匹配 ≥80%)。
> 不匹配 → 该草稿说的不是这份发票,拒绝,记 `draft_binding_rejected` 事件,**不进账本**。
>
> **随后**记录该值落在哪个已注册证据片段内(或不在任何片段内)——
> 这决定 `support_strength`,**不决定是否接纳**。

⚠ **必须是文档级,不能是片段级。** 片段级(要求值落在 DWS 注册的 bbox 内)实测会
误伤 **26–28%** 的合法作答:

| 读图模型 | 作答 | 文档级拒绝 | 片段级拒绝 | 片段级误伤 |
|---|---|---|---|---|
| Kimi K3 | 140 | **14** | 50 | 36 (26%) |
| Opus 5 | 146 | **9** | 50 | 41 (28%) |
| GPT 5.6 SOL | 168 | **118 (70%)** | 138 | 20 (12%) |

被误伤的正是"DWS 没返回值或框错了位置,而读图在页面别处找到"的行 ——
**那是读图唯一有增量价值的地方**(第六轮:漏网真错的真值 8/8 都印在页面上)。
片段级规则会把系统最有价值的部分当成错误杀掉。

**GPT 5.6 SOL 的错位事故会被文档级规则拒掉 118 行(70%)。**

### 5.3 门禁事务 `gate`
绑定到**确切的工件修订与哈希**后运行;输入签名对不上则拒绝执行 ——
这是可复算性的来源:同样的输入哈希 → 同样的裁决。

产出:`gate_report.json`(evaluations + findings)+ 事件。

---

## 6. 门禁(六个,确定性,不调模型)

照 BriefLoop §3.3:确定性审计由 Python 执行。六个门禁**全部已在 dws-derisk 实现并测过**。

| gate_id | 检查 | 六轮实测 |
|---|---|---|
| `arithmetic_consistency` | net+vat=gross、gross=due、日期序 | 复现生产口径 530/1000 |
| `field_wellformed` | 金额可解析、日期合法、编号非空 | — |
| `extraction_present` | DWS 是否返回值 | 359 flagged 中 267 例缺值 |
| `citation_holds` | 值是否在 DWS 自称的引用区(**独立 OCR**) | T1 静默 4.4%→3.1% |
| `cross_mode_agreement` | understand vs agentic | lift 2.40×,**已知不独立** |
| `visual_corroboration` | 整页读图是否支持 | 三模型,lift 1.29–1.33 |

**负面发现规则(§宪章四)**:门禁跑不了 = `blocking_level: "blocking"`,severity `high`。
`extraction_present` 失败的 267 例是 267 条带修复路由的阻断发现。

**`visual_corroboration` 对全部字段运行,不只对被 flag 的。**
六轮的分层让最危险的错误逃过检查:未被 flag 的 TIER1 字段仍有 **7.8% 真错**,
含 5 倍(`422,539` vs `83,625`)、8 倍(`6467` vs `800`)的金额错误,**六个门禁全过** ——
因为它们是自洽的误读。而实测这 8 例的真值 **8/8 都印在页面上**,读图本有机会全拦。

---

## 7. 分诊 —— 支持矩阵的投影,不是独立功能

支持矩阵按 `support_strength` 升序排列,即复核队列。实测(60 份新文档,TIER1 字段):

| | 偏差率 |
|---|---|
| 门禁挑出的 | **50.0%** (43/86) |
| 未挑出的 | 11.8% (12/102) |
| **集中度** | **4.2×** |

**看 46% 的字段(86/188),覆盖 78% 的偏差(43/55)。**
端到端:偏差 29.3% → 10.6%,人工 35.5%;每 1pt 人工换 0.52pt 偏差削减,
是纯确定性检查的 **1.8 倍**。

**分诊不要求任何一档"可信"**,只要求排序优于随机 —— 4.2× 已证明。
这让 §6 那个 7.8% 从"致命缺陷"变成"如实标注的一格"。

---

## 8. 校准与其限定

`support_panel` 展示每个门禁的**实测拦截率**,来自六轮预注册实验。
按宪章六,**必须同时展示三条限定**:

1. 门禁是**看过第一轮数据之后**设计的(`THRESHOLDS.md §6c B-4` 自陈),带乐观偏差,
   而**留出集确认从未执行**
2. DocILE 标注本身有争议 —— 第四轮逐份读图,14 例中 **8 例是标注错**
3. 校准集全为美国广播广告发票,**分布外表现未知**

---

## 9. 主张与不主张

**主张**
- 每个字段带可机械验证的支持关系:证据片段、四维强度、六个门禁裁决、修复路由
- 支持矩阵可从存盘响应**零 API 重算**
- 分诊排序经 160 份预注册文档实测:4.2× 集中度、78% 覆盖
- 冻结事务能结构性拒绝错位绑定(实测对一个真实故障拒绝 66%)

**不主张**
- **不主张 DWS 可信,不主张抽取质量提升。** 六轮说的恰恰相反,**且要写进 demo**
- 不主张语义正确性 —— 输出是支持矩阵,不是"这个值是对的"
- 不主张可无人值守 —— 无支持项按设计就要人看
- 不主张适用于生产 —— 160 份、英文、单一供应商、单一时间点

---

## 10. 明确不做

BriefLoop 的这些机制是为**并发多智能体、长周期可恢复运行**设计的。
单张发票抽取是单写入者、几秒钟、无并发修改 —— **照搬是 cargo cult**:

乐观并发(`store_revision_conflict`)、Unit of Work、按请求指纹回放、
artifact supersession、repair cycle、finalize render、跨运行改进账本。

**保留的三条与并发无关**:内容寻址冻结、草稿/冻结分离、负面发现即阻断。

---

## 11. 里程碑(截止日决定做到哪一层,每层独立可演示)

| M | 交付 | 依赖 |
|---|---|---|
| **M0** | `extract` + 证据片段注册 + 声明图 | 已有 `extract.py` |
| **M1** | 六个确定性门禁 + `gate_report.json` | 已有全部检查逻辑 |
| **M2** | `freeze` 事务 + 绑定拒绝 | 新写,~150 行 |
| **M3** | 支持矩阵四维 + `support_panel.html` | 新写,demo 主画面 |
| **M4** | 人工裁决记录 + `audit_bundle.zip` | 可选 |

**M0–M1 大部分是把 dws-derisk 已有代码搬过来。** 真正新写的是 M2 与 M3。

---

## 12. 已定的四个决定(可推翻)

问过四次未得答复,按最合理默认执行,以便开工:

1. **代码位置**:`~/Developer/invoiceloop/`(独立仓库,产品身份);
   `~/Developer/dws-derisk/` 保持为**校准档案**,InvoiceLoop 通过配置指向它
2. **panel 形态**:静态 HTML,可离线演示,无需服务
3. **输入**:v0 仅 DocILE(证据链完整、可零 API 重算);
   上传路径后续加,且必须标注"不在校准集内"
4. **截止日**:未知 → 里程碑设计成每层独立可演示,截止日只决定停在哪一层
