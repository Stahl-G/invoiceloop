# SEALED-4 广播封箱结果（2026-08-10，一次开箱，数字照登）

协议与增补件：`docs/SEALED4_PROTOCOL.md`；机器计划与名单：
`docs/sealed4_plan.json`、`docs/sealed4_doc_list.json`；钉板记录：
`docs/SEALED4_PIN_2026-08-10.md`。开箱 revision：
`8defabf0db512d9240f144b7d59a06f094840ce5`。
评分器协议版本 `sealed4-broadcast-v1`；资格判定集为 **strong 子集**
（增补件 A4），weak 子集单列照登。

## 结论先行

1. **SEALED-4 资格通过（广播范围，strong 子集）**：主臂 HAR-0021 相对
   保守基线 HAR-0001，人工队列 **433/680 (63.7%) → 321/680 (47.2%)**，
   少 112 槽（−16.5pp）；两类静默错均不升（P1 ✓），队列下降（P2 ✓），
   H1–H7 全过。
2. **真静默缺席 0**：主臂 149 个 auto_absent 中 2 例真值非空，但全部
   落入预注册口径规则（truth-caliber-v1）—— 1 例 T2(ii)（别名目日期）、
   1 例 T1（单总额归槽），照登为口径争议，不进真静默列。
   `silent_wrong` 31 → 31（strong）、35 → 35（全集），不升。
3. **预测偏差照登**：增补件 A4.1 预测 strong 子集队列降 4–12pp、
   真静默 0、口径争议 0–3 例。实际 **−16.5pp，超出预测区间上沿**；
   真静默 0 ✓、争议 2 ✓。减负收益好于预测，不解释原因，照登。
4. **H7 首验 FAIL → 修复 → 复验 PASS**：交付侧 bundle 验证器漏传
   `absence_probes`，AV 规则槽路由重算全不符（见 §5）。修复不在冻结面，
   批次数字不变，全过程照登。
5. **资格边界**：本次资格只覆盖**广播子池**（broadcast-pilot-v1 范围，
   strong 子集）。通用 DocILE 池的资格不由本批证明。

## 1. 执行与封缄

- drand round **6363898**（承诺于 commit `6a0db9f`，承诺时最新 round
  6363858）；种子
  `184789911618e785e004bde36a5b02b6bb94e3eeae82d960d593c7fdfb6336b4`。
- 名单 100 份 = **68 strong / 32 weak**；
  `docs/sealed4_doc_list.json` sha256
  `e48b5ffae058444ab201467ade62e9f24a30cdfdaf22f568a46d586d913785a8`。
  旧全池名单作废留盘 `docs/sealed4_doc_list_voided_fullpool.json`。
- 钉板 commit `8defabf`（#6）：主臂 **HAR-0021**，policy 文件 sha
  `bed2a209…`，policy_digest
  `25a1713278eae03d9132f0b16bee830fa716c8fb03752bffc4bf4a0dd08d8c00`；
  基线 **HAR-0001**；三臂 B0 / P / P-REPEAT；25 个 frozen_files。
- 抽取（#7a）：两程完成，200/200 status 200，总花 **5,304 credits**
  （2877 + 2427；第一把 key 中途耗尽，补第 5 把 key 续跑，事实照登）。
  工作区 `runs/sealed4-v2-workspace`。
- 开箱（#7b）：`scripts/sealed4_batch.py --expected-head 8defabf…`
  一次执行；三臂全过三个批不变量；`batch_complete.json` sha256
  `b30d3a8941a554db5ee0a013682c91bae2df99ba9c68524f17fb91713be3c988`。
- metrics sha256：
  `7eebf10a1b3dbeda9b92354a10fe4458a1908436f7af84e72cd952ae474ec115`
  （H7 修复后重打分版；首验 FAIL 版
  `c20bc5772d8837d66433fdcce8b4577f86c7d2591763484c47b224e07b9e9006`
  已删除，见 §5）。
- 主臂 field ledger：1246 claims，账本内 sha256
  `5b5c0c3d0780409ebea8e8ea1af49b983d84f3d0264fdba42368d0ef9ae69e93`。
- 主臂 audit bundle：417 members，sha256
  `48b89f690c6dab77223bb32cfb930915dd649f1efb6558ab01332e13b24b2f25`；
  members/snapshot/semantics 全过，空裁决所以 binding=None，未做 DWS
  signature sealing（不影响预注册 H7 的四层 verify）。

## 2. 主终点 H1–H7（P = HAR-0021，strong 子集判定）

| # | 量 | **SEALED-4 strong** | 区间 | 判定 |
|---|---|---|---|---|
| H1 | 分诊 lift | **5.08×** | > 1.5 | **PASS** |
| H2 | coverage@46% | **79.11%** | > 55% | **PASS** |
| H3 | 历史 requires 口径复核召回 | **80.38%** | > 55% | **PASS** |
| H4 | extraction_present 缺失率 | **12.79%** | 10–45% | **PASS** |
| H5 | citation 可判子集失败率 | **12.89%** | < 15% | **PASS** |
| H6 | understand 冻结拒绝率 | **30.28%** | 5–35% | **PASS** |
| H7 | 运行闭环 | **bundle verify PASS**（修复后复验，见 §5） | run + verify | **PASS** |

H5 首次在封箱批落回区间内（SEALED-3 为 15.35% 照登 FAIL）；这是广播
子池上的观察，不说 citation 在通用池上修好了。

## 3. 工作量与安全结果（strong / weak / 全集）

`human_queue` 是对外人工队列口径：route 不是 auto_accept/auto_absent。
`silent_absent` 为原口径（真值非空即计）；`silent_absent_true` 按
truth-caliber-v1 扣除口径争议后计。

| 子集 | arm | human_queue | auto_absent | silent_absent | 口径争议 | 真静默 | silent_wrong |
|---|---|---:|---:|---:|---:|---:|---:|
| **strong (680)** | B0 HAR-0001 | 433 (63.7%) | 0 | 0 | 0 | 0 | 31/210 |
| **strong (680)** | **P HAR-0021** | **321 (47.2%)** | 112 | 1 | 1 (T2(ii)) | **0** | 31/210 |
| weak (320) | B0 HAR-0001 | 186 (58.1%) | 0 | 0 | 0 | 0 | 4/114 |
| weak (320) | P HAR-0021 | 149 (46.6%) | 37 | 1 | 1 (T1) | 0 | 4/114 |
| 全集 (1000) | B0 HAR-0001 | 619 (61.9%) | 0 | 0 | 0 | 0 | 35/324 |
| 全集 (1000) | P HAR-0021 | 470 (47.0%) | 149 | 2 | 2 | 0 | 35/324 |

精确重复臂 P-REPEAT 与 P 全部配对差为 0，确定性控制通过。

### 配对差（P − B0，资格比较）

| 比较 | Δ human_queue | Δ silent_absent (raw) | Δ 真静默 | Δ silent_wrong | 结论 |
|---|---:|---:|---:|---:|---|
| strong（判定） | **−112 (−16.5pp)** | +1 | **0** | 0 | **P1 ✓ P2 ✓** |
| weak（照登） | −37 (−11.5pp) | +1 | 0 | 0 | 单列 |
| 全集（照登） | −149 (−14.9pp) | +2 | 0 | 0 | 单列 |

## 4. 两个口径争议槽（照登，不归零不隐藏）

| doc | 字段 | DocILE truth | 口径规则 | 子集 |
|---|---|---|---|---|
| `4c355e84b7524a3d8f573bb9` | due_date | `9/22/2021` | T2(ii)：日期在页面 OCR 出现，±12 词窗内含冻结词集（transaction/donation/authorization/adjustment）之一 —— 别名目日期 | strong |
| `961a7ea0624341f2b83544da` | total_net | `$72,000.00` | T1：与 truth[amount_due] 规范化为同一金额 —— 单总额归槽 | weak |

两例均按增补件 A3 从真静默列拆出、单列照登。它们仍是**争议**，不是
正确；按宪章五保持显式，进人工裁决视野。

## 5. H7 首验 FAIL → 定位 → 修复 → 复验 PASS（照登）

- **首验 FAIL**：开箱后首次 bundle verify，数百条
  "routing_report 槽 X 的路由与策略重算不符"。
- **根因**：`adjudicate.py::verify_bundle` 重算路由时调
  `derive_document_records` 漏传 `absence_probes`（探针在
  gate_report.json 里，运行时 matrix.py 会传）→ 所有 AV 规则槽重算成
  absence_evidence=not_measured → 路由全部不符。
- **修复**：commit `fbfbe7f`，验证器传入探针 + 回归测试
  （`test_absence_evidenced_routes_recompute_from_bundle`）。`adjudicate.py`
  **不在 25 个 frozen_files 里** —— bundle 是开箱后构建的交付侧校验，
  不是批计算；policy/门禁/规范化/路由/scorer/基线/名单/种子均未动，
  批次数字不变。
- **复验 PASS**：重建 bundle（sha `48b89f…`）→ 重打分（metrics sha
  `7eebf1…`）→ H7 verify ok，failures=[]。

## 6. 资格、候选与后续边界

- **HAR-0021：SEALED-4 qualification = PASS（strong 子集，广播范围）**。
- 资格语义按增补件 A4：只说"在开发期未见的 100 份广播子池样本上，
  strong 子集里 HAR-0021 减负且真静默不升"。**不推广到通用 DocILE 池，
  不推广到 weak 子集**（weak 是单列照登，不是判定集）。
- **人工裁决准确率：NOT MEASURED**；继续保留为独立的人类臂终点。
- sealed4-100 不并入 exposure manifest；那是 SEALED-5 的设置动作，
  现在并入会破坏增补件 A1 的 digest 回归测试。
- 本批已完成它对 revision `8defabf` 的一次性测量。由本结果启发的任何
  规则改动只能用开发/回归数据；下一次未见资格另抽 SEALED-5。

本次可以公开说的最强一句话是：**在开发期未见的 100 份广播子池
SEALED-4 上，strong 判定集（68 份 680 槽）中 HAR-0021 把人工队列从
63.7% 降到 47.2%（−16.5pp），真静默缺席与 silent_wrong 均不升，
H1–H7 全过；2 例真值非空的 auto_absent 全部为预注册口径争议，单列照登。**
