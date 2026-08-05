# 81/100 评审(高级模型裁决)的应答(2026-08-05)

评 commit b5fe7a0,结论 81/100 CONDITIONAL PASS + 一个 P0 语义完整性漏洞
+ improve 设计 HOLD-RECUT。这轮评审在副本上实跑了攻击链,不是纸面评审。

## P0-1:投影被当成权威值(评审实测攻击,全部属实)

攻击:只改 support_matrix.json(不在快照成分内)→ accept → deliverable
输出污染值 → 三层 verify 全过。我们复现确认后按四层修:

1. **deliver.py 值源切换到冻结账本**:accept 的值从 field_ledger 的 claim 取,
   matrix 只提供行集与 requires 标记;accept 指向不存在的 claim → 整单 blocked;
2. **append 投影↔权威交叉检查**:matrix 同槽行值与冻结声明不符 → 拒绝裁决
   (「在被动过的证据上不记裁决」原则的延伸);
3. **verify 第 4 层(语义层)**:包内投影值与权威交叉比对 —— matrix 行值 vs
   冻结声明、deliverable 接受值 vs 声明、修正值 vs 裁决、拒绝/缺失槽不许带值;
   攻击者重算 MANIFEST 也过不了这层(回归测试钉死:members/snapshot 全过、
   semantics 抓);
4. **回归测试** `tests/test_projection_integrity.py`:三层防线各一条 +
   完整攻击链一条,7 条。

## P0-2:决策语义拆分(已实现)

`accept`(必须带 claim_id)/ `confirm_absent` / `not_applicable` / `reject` /
`correct` / `abstain`。无 claim 的 legacy accept 投影为 confirmed_absent 并标
legacy;workbench 表单按槽位形状出不同决策集(有声明:accept/reject/correct/
abstain;无声明:confirm_absent/correct/not_applicable/abstain)。
「确认没有」与「人看不懂」从此是两个信号 —— 对任何未来反馈循环都关键。

文档级阻断的放行:不新增 document_override 决策类型(裁决对象是槽位),
改为独立状态 `released_with_caveats` —— 与正常 released 分开计数,
caveats 列明哪些机检没跑。披露不变,状态不再混。

## P1:基线扩充与数字收敛

- **更正事实错误**:「DWS 不给字段级置信度」是错的 —— `output.metadata.
  <field>.confidence` 存在(0.95/0.4,groundingScore,no-logprobs)。
  BASELINE_COMPARISON.md 已更正并留痕;
- **新增置信度阈值基线**(≥0.95):TIER1 静默错误 16.10%,召回 55.8%;
- **新增同人工预算比较 + 按文档 bootstrap CI**:诚实结果 —— 分诊序与
  置信度升序在 recall@budget 上**打平**(CI 完全重叠)。文档读法已收敛:
  分诊的差异化在操作点安全性与可验证性,不在排序质量;
- **真实人工负载**:deliverable summary 新增 `decision_load_for_release`
  (requires_adjudication ∪ TIER1),demo 实测 0.83 —— 与反事实分诊负载
  0.42 并排报告,不藏;
- bootstrap 修了一个自发现的 bug:按文档重采样后必须按 queue_idx 重排,
  否则 CI 不含点估计(已修,测试钉死)。

## Step 6:执行身份进指纹

`build_input_manifest` 现在把 `code_revision`(git HEAD)纳入指纹:
代码/策略变了,同输入不再重放旧 run,自动开新一代。非 git 环境记 null 并
如实披露。docs-only 提交也会换代 —— 保守方向,宁可新 run。

## improve 设计:按用户指示暂缓

用户决定 improve 层需要更多讨论,本轮不重写设计文档。评审的 HOLD-RECUT
意见(Tax AI 前提误读、可编辑面其实存在、fitness function 与提案不匹配、
sealed final eval)已完整保留在评审记录里,待讨论后回写。

## 评审指出、我们评估后不动的

- **matrix 整体进快照成分**:不进。matrix 是可重建投影,架构上快照只绑权威;
  正确修法是值源归权威 + 语义层交叉验证(已完成),不是把投影抬成权威。
- **verify 全量重建 matrix/deliverable 做字节比对**:暂不。语义层已覆盖
  值级一致性;全量重建需要 bundle 内重跑矩阵构建(含 understand 响应解析),
  复杂度与收益不匹配,列入 backlog。

## 数字

本地 309 passed;fresh-venv 259 passed + 41 skipped(语料守卫)。
