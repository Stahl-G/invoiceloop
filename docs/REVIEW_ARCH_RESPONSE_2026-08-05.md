# 架构裁决(对实施计划)的应答(2026-08-05)

评审对象是我写的实施计划 + b5fe7a0 的 zip(计划之后的实现它没看到)。
裁决:方向 PASS,计划 CONDITIONAL PASS + 八条修订。逐条对照落地情况:

## 已按修订实施(本轮)

| 裁决 | 落地 |
|---|---|
| 二、input/execution identity 分离 | `input_manifest.fingerprint` 回到纯输入;新增 `execution_fingerprint`(输入+code_revision+harness_id+harness_digest+routing-v1);`find_run_by_fingerprint` 按执行指纹,legacy 回退自动换代;测试钉死「同输入同输入指纹(配对可证)、换 harness 换执行指纹」 |
| 三、verify 重算 routing | matrix 行补 `slot_blocking`/`doc_blocked`;verify 语义层新增:嵌入 policy 的 digest 一致性 + 从包内行事实重算 routes 逐槽比对(伪造 routing + 同步重算快照也过不了,回归测试钉死);deliver 的 route/requires 改从 routing_report(快照成分)取,不从 matrix 取 |
| 四、确定性 QA 采样 | `routing._qa_hit`:sha256(seed+harness+doc+field+version) 哈希采样,非随机数;policy 配 `policy_accepted_tier1_rate` 5% / `cohort_relax_rate` 20%;HAR-0001 两类目标皆空,零 diff 不破;5 条测试(确定性/rate 0/rate 1/HAR-0001 零命中/cohort 命中) |
| 五、EVO 评测不叫 promotion | PROM 记录带 `basis: evo_replay_only` + `claim_limits`(未经未见资格集 = demo activation,公开口径受限);PROMOTION-1 新数据 + credits 是用户决定项 |
| 六、反馈诊断合同 | `reviewer_confidence`(high/medium/low)+ reason↔decision 组合校验(CONFIRMED_ABSENT 不许挂 accept 等);feedback 事件带 `actionable`(心码+中高把握+非弃权),业务裁决与诊断标签两层语义保持 |
| 七、active 指针是投影 | PROM 记录绑 candidate/baseline policy digest + eval result digest;`improve rollback` 命令:回滚 = 新 PROM 记录(append-only),包内 HAR-0001 自动物化 |
| 八、运营/安全指标分母拆分 | R0 文档已拆:运营指标(全部槽,无真值)61.2%/100%/82.3%;安全指标(有真值子集)只见三方基线文档 |

## 裁决一(P0-6 语义立场)—— 与评审不同的选择,记录在案

评审要求 HAR-0001 把 requires=false 的 TIER1 直接 policy_accept。
我们保留 `release_tier1_explicit: true`(TIER1 印证槽整单放行前显式人裁):
这是 78 评 P2 后**用户批准的放行策略**,不是实现偷懒。policy_accept 机制
已就绪(机制本身不是伪审批 —— 它显式记录策略版本),把 TIER1 显式改成
policy_accept 是第一个 R1 候选的合法内容,走完整评测+晋升,不是开工默认。
两种立场的分歧点已写进 IMPROVE_LAYER_V01_IMPLEMENTATION 文档。

## 评审对但本期不动的

- QA 多层自适应抽样(只做两档固定率);
- 双人复核工作流(记录维度在,流程是组织问题);
- sealed final eval(需新数据 + credits,用户决策);
- PROMOTION-1 资格集(同上)。

## 资格时间线(评审提醒)

官方开赛 8/17 10:00 PDT = 8/18 00:00 ICT。本批代码仍在开赛前产出,
按披露策略走:本轮提交后打 `pre-hackathon-baseline` tag,赛期内增量
(任何新功能/视频/复测)与该 tag 的 diff 一目了然。
