# SEALED-4 封箱评测协议(2026-08-09,执行前冻结)

SEALED-3 已被 2026-08-08 那次一次性开箱用掉(`SEALED3_RESULTS.md` §7),并且
**本批要考的 16 条类别缺席规则正是由它的失败启发的** —— 拿它复考等于用同一批
数据既出题又改卷。所以再抽一批,作当前唯一未见晋升资格集。

## 0. 冻结对象(本文件首次提交即冻结)

- 产品代码:本文件首次提交时的 HEAD;
- 排除池:`docs/development_exposure_manifest.json`(**已含 sealed3-100**,
  unique 560);
- 抽样实现:`invoiceloop/heldout.py::sealed_list(..., context="sealed4-v1")`;
- 主臂策略:**HAR-0017**,policy digest
  `9b6df44236d1e22d19b760e1b1d786906f88c8d5a7d6ba58e5895982a699c7c7`,
  文件已钉在 `docs/evidence/class_absence_2026-08-09/HAR-0017.routing_policy.json`;
- 基线策略:包内 **HAR-0001**(`invoiceloop/harnesses/HAR-0001/`)。

## 1. 随机种子承诺

- 随机源:drand 主网 beacon(`https://api.drand.sh/public/{round}`);
- **本批轮次**:`6360483`;
- **种子(hex)**:`1e3119dd512be9b86f1f1db49687704a3856ae5331f4ced7232258a8aa58cbd7`(该轮 `randomness` 字段原文);
- 取种时间(UTC):`2026-08-09T03:18:31Z`;
- 抽样 = `heldout.sealed_list(seed, context="sealed4-v1")`:
  `random.Random("invoiceloop-sealed4-v1|" + seed).sample(sorted(pool), 100)`,
  pool = ≥4 记分字段标注 ∧ 不在暴露清单(本次 4,931 份);
- 名单落盘 `docs/sealed4_doc_list.json`,任何人可公开复算。

## 2. 执行顺序(不许颠倒)

1. 暴露清单并入 SEALED-3 的 100 → commit;
2. 本协议 commit(**先于开奖**),§1 的三个空位留白;
3. 取 drand 公开轮次 → 填入 §1 → commit;
4. `python3 -m invoiceloop sealed plan --workspace runs/sealed4-workspace
   --context sealed4-v1 --seed <hex> --seed-source "drand round <N>"`
   → 复制为 `docs/sealed4_doc_list.json` → **单独 commit**(先于任何 DWS 调用);
5. **仅在明确预算授权后**:`sealed extract` —— 200 次调用
   (understand + agentic × 100),预算熔断 6000 credits;
6. **封箱不读**:extract 完成后只记 ops 摘要;不得 `run`、不得读 raw、
   不得用本批调词表或策略;
7. 开箱一次 → `docs/SEALED4_RESULTS.md`,数字照登。

## 3. 预注册终点

主终点沿用 H1–H7 区间(`docs/SEALED1_PROTOCOL.md` §3),主臂为 HAR-0017。

晋升门,**基线 = HAR-0001**,两臂在同一批证据上各跑一次完整确定性流水线:

| # | 量 | 通过线 |
|---|---|---|
| P1 | `silent_absent`(对 DocILE 真值) | 相对基线**不上升** |
| P2 | `silent_wrong` | 相对基线**不上升** |
| P3 | `human_queue`(route ∉ auto_accept/auto_absent) | 相对基线**下降** |

P1 单列而不与 P2 合并,是因为 SEALED-3 就死在这一项上:主臂 `silent_absent`
0 → 1,`silent_wrong` 持平。合并成一条「静默错不升」会让那次失败读起来像
一次擦边,而它不是 —— 被误判成缺席的槽再也不会有人看到,没有事后发现的机会。

### 3.1 结果前就写死的预测

开发集(300 份)上 HAR-0001 → HAR-0017 的实测是:人工队列
1,806 → 1,736(−2.33pp),`auto_absent` 0 → 70,`silent_absent` 0/70,
`silent_wrong` 179/1,015 不变(`CLASS_ABSENCE_PROMOTION_2026-08-09.md`)。

**预测**:SEALED-4 上人工队列下降 1–4pp,`silent_absent` ≤ 2。

写下这条是为了让偏差可见。偏差本身**不是**作废条件,照登即可;
真正的作废条件在 §5。

## 4. 主张纪律

- 未开箱前 ⇒ 只可报告抽取 ops(调用次数 / 失败 / 花费),
  **不得**声称未见集减负或资格;
- 开箱通过 ⇒ 可以说「在一个开发期未见的 100 份封箱集上,16 条类别缺席规则
  减少了人工队列且两类静默错都没上升」;
- 开箱未通过 ⇒ 数字照登,不写资格标记,不换基线、不删规则、不再跑第二次;
- SEALED-1 / SEALED-2 / SEALED-3 / 旧 heldout-100 **一律不得**再称 final held-out。

## 5. 作废条件(结果出来之后再改任何一项 = 本批作废)

- 改动 HAR-0017 的 policy(增删规则、改 QA 率、改 sampler 版本);
- 改动门禁、规范化规则、路由代码或 scorer;
- 换基线、换名单、换种子、重抽;
- 看过本批结果之后再调上述任何一项 —— SEALED-4 自动降级为回归集,
  另批新种子重来。

**用完就没了。** 本批之后若还要未见资格,得再抽 SEALED-5;而语料池
(4,931 份)是有限的,每抽一次少 100 份。
