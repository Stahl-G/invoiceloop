# 双评审(83/100 与 69/100)+ 高级裁决的应答(2026-08-05)

评审对象:commit 4ce8728(状态总账)。两份打分迥异 —— 83(工程增量视角,
无封顶机制)与 69(raw 77,但「无有效 final held-out」触发 69 硬性封顶)。
**分歧的根源是两把尺子,不是谁错**:83 评看控制面工程,69 评看证据有效性
(留出集污染 + 提交材料)。两边的主张我们都逐条对代码核查过,**全部属实**
(这轮没有可反驳项;核查记录见下)。

## 分歧诊断(为什么会出现 83 vs 69)

| | 83 评 | 69 评 |
|---|---|---|
| 框架 | 增量评分,无 ceiling | rubric + 硬封顶(无有效 held-out → 69) |
| 核心攻击面 | Improve 控制面权威链 | 证据有效性(留出集污染)+ 基线合同 |
| 共同结论 | 工程成熟,但「eval-gated」名不副实;未见数据上无正向循环 |

## 逐条核查与修复(修复 1–5,commit 3fa6184)

**83 评四条对抗声称 —— 全部复现成立,全部修复:**

1. **promote 可绕过 evaluate**(improve.py 旧 268-276 行:eval 不存在记 None
   照样晋升)→ 修复 1:promote 强制门。**按高级裁决四加强**:不是查文件,
   而是 promote 时**确定性重算 evaluate 并与存盘逐字节比对** —— 评测输入
   (每 run 的 snapshot id + routing/ledger/gate/adjudication/raw 五路
   sha256)评测后被动过,重算即分叉,拒绝。零覆盖评测不许晋升。
2. **active_harness.json 是实际权威**(伪造指针即可换 harness)→ 修复 2:
   active 由 PROM **哈希链**重放(裁决五:文件名连续、记录 ID 与文件名
   一致、previous_promotion_digest 链、from/to 双侧 policy digest 匹配),
   指针只是缓存,不一致 fail closed。manifest 出生后不可改,不再有
   status 字段(不当第二权威)。
3. **mine 不过滤 actionable**(actionable 只在 feedback.py 计算,从未被
   消费)→ 修复 3:事件标 superseded(只计裁决链 tip)与 random_qa,
   mine 分桶报告(all/actionable/superseded/random_qa/不可行动原因),
   cohort 统计只用合格事件。
4. **协调篡改过四层 verify**(改 matrix 事实 + routing_report + 重算快照
   → 全过,因为语义层从投影取事实)→ 修复 4:`matrix.derive_document_records`
   单一事实源(**文档级签名**,裁决六:口径争议判据跨字段,槽级装不下),
   build_matrix / verify 语义层 / improve.evaluate 三处共用;verify 从
   field_ledger + gate_report + raw understand 重建事实,三路槽集合比对
   (缺行/多行也算篡改)+ 矩阵行 vs 权威重建交叉 + 路由逐槽含心码比对。
   **行为守恒证明**:HEAD 代码与重构后代码各跑留出集 100 份,
   support_matrix / routing_report / gate_report / field_ledger
   **逐字节相同**(r5-pre vs r4)。

**69 评两条判定点:**

5. **基线合同不对称**(raw DWS 缺值也算它的静默错误,其他系统缺值进人工;
   confidence 借 InvoiceLoop 的 value_present 与 queue_idx)→ 修复 5:
   评估器重写(裁决三),五系统各自从自己的预测源打分(raw 存盘响应
   vs 冻结账本),错值/缺值拆报,confidence 平局固定 (doc_id, field)
   tie-break + 切入同分组报 best/worst/expected。
6. **留出集污染**(C3/C8/漂移分析案例来自那 100 份 —— 我们自己记录在
   LIVE_TEST 文档)→  methodological 判决成立。处置:旧 100 降级为
   回归/演化集;SEALED-1 真封箱(下节)。

## 公平合同下的新数字(基线重测,TIER1)

| 系统 | 静默错误率(旧 → 新) |
|---|---|
| raw DWS(全信) | 29.97% → 26.32%(其中缺值放行 7.37pp) |
| 置信度阈值 | 16.10% → **20.69%**(旧口径借了冻结闸门) |
| 双模式一致 | 14.95% → 11.27% |
| InvoiceLoop | 8.98% → 8.98%(不变 —— 它本来就用自己的账本) |

同预算排序(recall@30%):旧「67.4% vs 67.4% 打平」→ 新 **48.0% vs 67.1%**
(CI [35.4,58.2] vs [58.5,76.9])。旧「打平」部分是两处借用造成的
(value_present 借闸门、queue_idx 借排序)。

**诚实边界(与裁决一致,不包装成胜利)**:confidence 同分组范围极宽
(30% 预算处 [24%, 100%],均匀随机期望 42.4%)—— 粗粒度两档置信度
决定其排序真实不确定性很大;点估计领先 + CI 恰好不重叠**不等于**稳健
胜出。正式结论留给 SEALED-1 预注册次终点(paired diff + paired CI)。
「打平」作为历史测量结果保留在 BASELINE_COMPARISON.md 的口径差异表里,
完整交代两处借用如何造成它。

## SEALED-1(真封箱,按裁决一/二,commit 83c7204 + 5050dfb)

- 排除池 = `docs/development_exposure_manifest.json`(260 份,逐条
  reason/source:校准 160 + 旧留出 100 + vendored demo 3);
- 种子 = **drand beacon 轮次 6350246**(≈ 2026-08-05T14:00Z,协议 commit
  于 ~10:15Z —— 承诺时该轮随机性尚不存在,任何人事后可复算名单);
- 顺序:代码/脚本/清单/协议先冻结 commit(脚本 sha256 入协议)→ 开奖 →
  名单落盘 commit → 才许调 DWS(200 次,熔断 6000);
- 预注册终点:主 = H1–H6 沿用区间 + H7 运行闭环(解除 69 封顶);
  次 = paired 排序比较(10/20/30/40% 预算,paired CI,tie 规则事前冻结),
  **不预设 InvoiceLoop 胜出**;100 份可能功效不足,事前声明不显著不算失败;
- 结果驱动的改动 = 本批作废降级回归集。

## 这轮评审错的地方

没有。两份评审的全部技术声称经代码核查成立(与前几轮不同 —— 「H6 分母
1305」「DWS 不给置信度」那类错误这轮没有出现)。唯一保留的立场分歧仍是
TIER1 显式人裁(用户批准的放行策略,走 R1 候选流程改,不是开工默认)。
