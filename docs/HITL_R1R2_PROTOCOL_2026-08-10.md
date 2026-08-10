# HITL R1/R2 轮次协议(2026-08-10,Round 1 开始前冻结)

依据:`docs/PHASE01_HITL_SUGGESTION_PLAN_2026-08-10.md` P0-3。
本文件首次提交即冻结;Round 1 第一次裁决之后改动任何一字 = 两轮作废。

## 1. 语料

- 池:sealed1/2/heldout/sealed3 四工作区双模式存盘文档 ∩ 广播 strong/weak
  (`docs/BROADCAST_PILOT_SCOPE_2026-08-09.json` 的既有分类,不重新分类),
  剔除 `h2_excluded` 17 份(H2 终止实验人工见过,计时不纯)。
- **sealed4-100 永不进入轮次语料** —— 那是资格集的测量面,挖它的裁决 =
  在资格集上调参。
- R1/R2 各 100 份,不重合;种子与抽样脚本随名单同 commit 落盘
  (`runs/hitl-r1/doc_list.json`、`runs/hitl-r2/doc_list.json`,各带 sha256)。
- 零新 DWS 调用:只用四工作区已存盘的 understand/agentic 响应。

## 2. 建议来源(Round 1 冻结,全部为离线确定性源)

| tag | 源 | 说明 |
|---|---|---|
| `derived` | `due_date.derive_due_date` 对独立 OCR 的派生 | 只填派生成功的槽;派生规则钉 `due-date-relative-term-v2` |
| `xmode` | 同一文档**另一模式**存盘响应里该字段的值 | understand 的槽看 agentic,反之亦然;跨模式分歧本身是既有信号 |

两源均为确定性、零 API、可复算。ADK 离线批若跑成,加 `adk` tag 并在
轮次记录里写明模型与日期;跑不成不影响轮次。

## 3. 测量口径

- **每槽人时** = 相邻 `decided_at` 差的中位数;间隔 > 1h 视为休息剔除;
  逐轮报 accept / correct / confirm_absent / reject 分位数
  (run-0002 同法,只报中位不报均值 —— 隔夜污染的先例)。
- **建议采纳率**:分母 = `suggestion_seen` 为 `agree:<值>` 的槽;分子 =
  决策为 accept 且声明值与建议规范化一致,或 correct 且修正值与建议规范
  化一致。`agree_rejected` / `split` / `blind` 单列,不进分母。
- **反事实队列率**:`improve.evaluate`,开发集,数字永远带「开发集」限定。
- 计时对照(手工 vs harness)不在本协议内,另立。

## 4. 轮间纪律

- 同一复核者(stahl),**换单不换人** —— 「人变熟练」与「系统变好」分开
  估计;分不开(两轮不是同一批单)就在结果文档照登混淆,不硬讲。
- 两轮之间只允许晋升**确定性**产物(门禁/缺席规则/建议模板),走
  mine → 人审 → `improve.promote --approved-by stahl` →
  `improve.evaluate` 反事实 + 全套 pytest 绿,才允许开 Round 2。
- 禁止:模型权重调整、词表删除、口径变更、碰任何 sealed 集。
- 中途口径裁定当时写进 rationale,事后进结果文档,不回改已判槽
  ($0.00 / 推导值两条先例的同一条纪律)。

## 5. 产出

`docs/HITL_ROUNDS_R1R2_<日期>.md`:三条曲线各两点(每槽人时、建议采纳率、
反事实队列率)+ 混淆声明 + 全部 sha(名单、账本、晋升记录)。
