# Improve Layer 实现记录(2026-08-05,v0.2 收窄版)

实施基线:`docs/IMPROVE_LAYER_V0.2_DESIGN.md`(外部裁决后的冻结设计)。
本文件记录**收窄版**落了什么、没落什么、实测数字。

## 落地映射

| v0.2 设计项 | 状态 | 证据 |
|---|---|---|
| P0-1 最终值来自冻结账本 | ✅(前批 b4ad192) | tests/test_projection_integrity.py |
| P0-2 决策语义拆分 | ✅(前批 b4ad192) | accept/confirm_absent/not_applicable/reject/correct/abstain |
| P0-3 routing 独立 | ✅ | `routing.py` + `routing_report.json`(进快照成分);HAR-0001 与旧内联判据**逐字节等价**:heldout 100 份重跑(r2 vs r3)行级零差异、H1–H6 逐位相同;tests/test_routing.py |
| P0-4 harness 进指纹 | ✅ | `input_manifest` 含 harness_id + policy_digest;晋升后同输入开新 run(test_improve.py 钉死) |
| P0-5 normalization 分离 | ✅ | `eval_norm.py` 冻结拷贝,eval scripts 专用;冻结点一致性测试 |
| P0-6 policy_accept | ✅ | `release_tier1_explicit=false` 的策略放行投影为 `policy_accepted`,值仍来自冻结 claim,source=policy:HAR-xxxx |
| FeedbackEvent | ✅ 收窄 | `feedback.py` 从裁决账本+矩阵派生;reason_code 可选(最小心码集,人给系统不代填);workbench 表单有下拉 |
| Weakness mining | 🟡 降级 | `improve mine` = 确定性 cohort 统计 + 低收益候选标出;报告头部印选择偏差警告;不自动归因 |
| Candidate + lint | ✅ | `improve propose`:只许加 cohort、只许通用特征(field/tier/strength),白名单外一律拒 |
| Evaluate | ✅ 收窄 | `improve evaluate` = 反事实重路由(不重跑 pipeline,零 API);明确不给安全性结论(真值评测属 sealed 协议) |
| Promotion | ✅ | `improve promote` 唯一写 active 指针,必须人名+理由+ISO 时间;PROM 记录 + rollback 目标 |
| 沙箱/三进程 | ❌ 不做(单人黑客松) | 以 linter + CLI 权限边界代替 |
| QA 抽样器 | ❌ 不做 | 随机性进 run 破坏确定性纪律;需 seeded 设计,另行讨论 |
| escalation/schema 候选 | ❌ v0.2/v0.3 内容 | |
| sealed final eval | ❌ | 需新数据 + DWS credits |

## R0 实测(设计禁令 #16 的执行)

`docs/R0_BASELINE_2026-08-05.md`:mandatory field review load **61.2%**、
document touch **100%**、decision_load_for_release **82.3%**。
**「41%」是 TIER1-only 反事实子集口径,不是 R0** —— 对外叙事按实测。

## P0-6 的语义立场(架构裁决一的答复)

HAR-0001 保留 `release_tier1_explicit: true` —— 「TIER1 印证槽整单放行前
必须显式人裁」是 78 评后**人批准的策略**(防止伪人工审批),不是实现偷懒。
评委裁决要求无冲突 TIER1 自动 policy_accept,是把「静默进交付物」换成
「带策略版本的显式 policy_accept 进交付物」 —— 后者的诚实度收益成立,
但作为 R1 候选走完整评测+晋升,不是开工即默认。
PROM 记录带 `basis: evo_replay_only`:没有未见资格集的晋升只是
demo activation,公开口径不许说「在未见数据上减少人工」。

## 闭环演示(全 CLI,实测通过)

```bash
python3 -m invoiceloop improve mine --workspace ws       # 38 事件 14 cohort
python3 -m invoiceloop improve propose --workspace ws --cohort-id C1 \
  --field seller_name --strength corroborated --finding FIND-001 --prediction "..."
python3 -m invoiceloop improve evaluate --workspace ws --candidate HAR-0002
python3 -m invoiceloop improve promote --workspace ws --candidate HAR-0002 \
  --approved-by <名字> --rationale "..." --approved-at 2026-08-17T10:00:00
# 之后 run --workspace 自动开新一代(harness digest 变了),绑 HAR-0002
```

evaluate 的 delta 可以是 0.0pp(小 workspace 没有命中 cohort 的槽)——
如实的零,不是 bug。演示时用 mine 报告里真实命中的 cohort。

## 测试

326 全绿(新增 test_routing 7 + test_improve 7 + test_eval_norm 2 +
policy_accept 1);fresh-venv 评委门 278 过 41 跳。
