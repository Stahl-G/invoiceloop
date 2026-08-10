# Phase 0+1 计划：HITL + 离线建议多轮优化（2026-08-10)

目标：**让"越来越有用"变成三条可测曲线**，带进 8/17 开赛窗口：

1. 每槽人时（中位秒，run-0002 口径：相邻裁决时间差，排除隔夜间隔）
2. 建议采纳率（采纳 / 建议在场且可采纳的槽）
3. 反事实队列率（开发集,`improve.evaluate`,带开发集限定)

**不是目标**：整单清零、silent_wrong 压降、"AI 在学习"的叙事。三者分别
被 SEALED-3/4 数据、资格流程、宪章否决，本计划不碰。

## 0. 现状锚点（开工前核实,2026-08-10)

**已落地,不要重做：**

- UI 四修复已于 2026-08-08 落地(`docs/ARM_RUN_LOG_2026-08-08.md` §终止后):
  rationale 必填下沉 `adjudicate.py:128`;高亮框透明底+描边+「隐藏高亮框」
  +「打开无框原图」(`workbench.py:674,792,1902`);表单 400 保留已填内容;
  原因码随决策联动。Phase 0 只做**回归确认**,不再修。
- 槽级建议通道已存在:读 `vision/answers6.<tag>.tsv`
  (`dws.py:101 load_vision_answers`,按 tag 自动收新读者),裁决页
  `_vision_suggest`(`workbench.py:1530`)—— 多读者一致给「采用」预填按钮
  (只填表单不写账本),分歧摊开,全弃权如实显示,同值被冻结拒过则**不给**
  采用按钮。归一化与双模式门禁同一函数。
- 规则级顾问层已存在:`invoiceloop suggest` → `improve/suggestions.json`
  (`suggest.py`),改进页展示采纳/试算/署名晋升。
- 改进控制面:`improve.mine` / `improve.evaluate` / `improve.promote`
  (`improve.py:36/921/1377`),晋升署名制。
- 每槽人时测量:账本 `decided_at`,run-0002 已用过同一分析方法
  (中位 28s,accept 20s / correct 66s)。

**缺口(Phase 0 要补的):**

| # | 缺口 | 说明 |
|---|---|---|
| G1 | 离线建议注入器 | TA 臂/ADK pilot 的输出不是 `answers6.<tag>.tsv` 格式;要一个转换脚本,**离线**写好 TSV,demo 与轮次都不依赖现场 API(deepseek/Gemini 额度事故与 demo 解耦) |
| G2 | 建议处置的结构化记录 | 现在采纳只能从 rationale 文本痕迹推断;要一个随表单提交的可选字段(建议在场状态: agree/split/blind/none),进账本新字段,append-only 加字段合法 |
| G3 | 计时协议冻结 | 两轮的人时测量口径(换人/换单/排除规则)必须赛前写好,不然曲线一出来就可疑 |
| G4 | 轮次语料与曝光登记 | 轮次用广播开发池、不在 sealed4-100 内的单;用完登记进 `docs/development_exposure_manifest.json`,SEALED-5 抽样排除 |

## 1. Phase 0(赛前,纯工程,无资格动作)

### P0-1 建议注入器 `scripts/suggest_inject.py`

- 输入:任一 `{doc_id, field, value, note}` 表(TA 臂裁决、ADK broadcast
  pilot 输出、确定性派生值均可为源)+ 目标 run 目录 + tag 名。
- 输出:`<run>/vision/answers6.<tag>.tsv`,走 `load_vision_answers` 既有
  校验;多个源 = 多个 tag = 多读者,agree/split/blind UI 自然生效。
- 建议来源优先级(第一轮):① 确定性派生(due_date 推导、门禁算术)打
  `derived` tag;② ADK pilot 离线批(跑一次,允许重试,失败不阻塞轮次);
  ③ TA 臂工件只在文档重合且注明 repurposing 时用(H2 已终止,配对结果
  永不报告,这条写进轮次记录)。
- 验收:对 `runs/arm-h2` 只读验收 —— 注入一个合成 tag 后裁决页出现建议行,
  分歧/弃权/冻结拒绝三态各至少一例;`pytest tests/` 全绿。

### P0-2 建议处置记录(小改两处,不进冻结面)

- `workbench.py` `_decide_form`:渲染时把建议状态(`agree:<值>` /
  `split` / `blind` / `none`)写进 hidden input `suggestion_seen`。
- `adjudicate.py::append_adjudication`:接受可选 `suggestion_seen=None`,
  原样进账本条目;缺省 None,旧账本不受影响。
- 验收:新测试 —— 提交带/不带该字段各一条,账本逐字节检查;761 全绿。

### P0-3 计时协议(半页,赛前冻结)

写进轮次工作区 `protocol.md`:

- 同一复核者(stahl),两轮各 100 份,**换单不换人** —— 「人变熟练」与
  「系统变好」分开估计;分不开就在结果里照登混淆,不硬讲。
- 每槽人时 = 相邻 `decided_at` 差的中位数;间隔 > 1h 视为休息,剔除;
  逐轮报 accept/correct/confirm_absent 分位数。
- 建议采纳率分母 = `suggestion_seen` 为 agree 的槽;分子 = 最终值与建议
  规范化一致且决策为 accept/correct 同值。
- 两轮间只允许晋升**确定性**产物(门禁/缺席规则/建议模板),过
  `improve.evaluate` 反事实 + 全套测试;模型权重、词表删除、口径变更
  一律禁止。

### P0-4 轮次语料

- 源:广播开发池(scope pool strong 2725 / weak 1471)剔除 sealed4-100,
  抽 Round-1/Round-2 各 100 份不重合样本;名单落盘
  `runs/hitl-r1/doc_list.json`、`runs/hitl-r2/doc_list.json`,sha 记进
  轮次记录。
- 抽取:**零新 API** —— 复用已存盘响应;缺响应的单直接换,不补抽。
- 跑管线出 run 工件 → P0-1 注入建议 → `workbench --review-scope` 起服务。
- 两份名单 + 轮次裁决完成后登记 `docs/development_exposure_manifest.json`;
  SEALED-5 名单生成时按 manifest 排除(既有机制,不改代码)。

## 2. Phase 1(窗口第一周,两轮 HITL)

### Round 1(约 3.5–4h 人时)

1. `runs/hitl-r1` 起 workbench,复核者按 P0-3 协议过完全部队列
   (预计 ~470 槽 @ 47% 队列率)。
2. 关账本,记 sha256;跑分析脚本出:每槽人时分位、建议采纳率、
   分决策类型分布。
3. `improve.mine` 出候选 → 逐条人审 → 只晋升确定性候选:
   `improve.promote --approved-by stahl`,晋升记录落盘。
4. `improve.evaluate` 反事实验证晋升后 harness(开发集)+ `pytest tests/`
   全绿,才允许进 Round 2。

### Round 2(约 3.5–4h 人时)

5. 同一协议、`runs/hitl-r2`(新 100 份),用晋升后的 harness 出队列。
6. 关账本轮分析,与 Round 1 并排:三条曲线各两点 + 限定。
7. 产出 `docs/HITL_ROUNDS_R1R2_<日期>.md`:数字照登,含混淆声明
   (学习效应)、口径裁定(复核者中途定的规则全写进 rationale 与文档)。

**时间预算**:Phase 0 约 1.5 天工程;Phase 1 两轮约 8h 人时 + 2h 分析。
**花费**:零新 DWS credits(ADK pilot 离线批失败就只用确定性派生源)。

## 3. 纪律(全程有效)

- 不碰冻结面:policy/门禁/规范化/路由/scorer 的改动一律走
  mine → evaluate → promote 署名流程,不直改。
- 不碰任何 sealed 集;SEALED-3/4 不调参;轮次数字永远带「开发集」限定。
- 建议层只预填表单,永远不写账本;同值被冻结拒过的建议绝不给采用按钮
  (既有守卫,注入器不得绕过)。
- 对外不说「AI 在学习」;口径是「人的裁决沉淀为确定性规则,经冻结评测
  晋升」。
- 任何中途口径裁定(如 \$0.00、推导值那两条的先例)当时写进 rationale,
  事后进结果文档,不回改已判槽。
