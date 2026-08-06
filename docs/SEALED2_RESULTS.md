# SEALED-2 封箱评测结果(2026-08-06 执行,一次完成,数字照登)

协议:`docs/SEALED2_PROTOCOL.md`(判据、种子、排除池、晋升门先于结果冻结)。
名单:`docs/sealed2_doc_list.json`(drand 轮次 6352483;种子
`b99de6bbc5e0c20707ceda77aae574391266b8d8dd5114bb8227523b680a1e59`;
PRNG 语境 `sealed2-v1`;与暴露清单 360 / SEALED-1 100 / 旧 heldout 零重叠)。

## 执行记录

- 双模式抽取:续跑汇总 `done=175 / skipped=25 / failed=0`
  (先前一轮 key 402 耗尽后用授权 key 续完);spent_estimate **4,368**
  credits(熔断 6,000 未触发);`runs/sealed2-workspace/extract_summary.json`。
- 主臂 run:`runs/sealed2`(HAR-0004 = 当前 active;
  policy_digest `eab9228721f59981…15f9f3`;
  code_revision `9bef179d956812dccd2c3fed6db5d5ccdc96772e`)。
- 记分槽 584,偏差 218;队首偏差率 56.8% vs 队尾 17.8%。
- 路由摘要(交付口径):human_queue **468/1000 (46.8%)**,
  machine_decided 432, machine_absent 100,
  requires_adjudication 568(含历史兼容口径)。
- audit bundle:`runs/sealed2/audit_bundle.zip` sha256 =
  `91ee9cbc7b276d31f06e911e26e14169da2f3d8f5bd726375eddda76ba42566d`,
  verify 成员 417,failures=[](空裁决 → binding 层按既有语义)。
- field_ledger sha256 =
  `92a28fa2e0f3177ccb5072a16d139933825cfda603b3f595cd98f75405490c3c`。

复算:

```bash
INVOICELOOP_CORPUS=runs/sealed2-workspace \
  python3 scripts/heldout_metrics.py runs/sealed2 runs/demo
```

## 主终点:H1–H6(+H7)(HAR-0004;区间沿用 SEALED-1 / HELDOUT 预注册)

| # | 量 | 校准 | 旧留出 | SEALED-1 | **SEALED-2** | 区间 | 判定 |
|---|---|---|---|---|---|---|---|
| H1 | 分诊 lift | 4.10× | 3.04× | 4.03× | **3.19×** | > 1.5 | **PASS** |
| H2 | coverage@46% | 78.1% | 74.3% | 77.3% | **75.2%** | > 55% | **PASS** |
| H3 | 复核召回 | 75.1% | 72.5% | 77.7% | **72.0%** | > 55% | **PASS** |
| H4 | 缺值率 | 26.8% | 27.9% | 29.3% | **12.8%** | 10–45% | **PASS** |
| H5 | citation 失败率 | 15.3% | 14.4% | 15.3% | **13.6%** | < 15% | **PASS** |
| H6 | 冻结拒绝率 | 18.9% | 34.6% | 36.6% | **34.6%** | 5–35% | **PASS** |
| H7 | 运行闭环 | — | — | — | bundle 417 成员,verify 全过 | — | **PASS** |

**判定:H1–H7 全过。** H1 为线的约 2.1 倍。H5/H6 在 SEALED-1 擦线未过,
本批站回区间内 —— **不得解读为「修好了 citation/冻结」**:本批 harness
是 HAR-0004(含演化 cohort),语料分布也不同,对照 SEALED-1 的 HAR-0001
数字不是同臂配对。

## 晋升资格(协议 §2 步 7 / §3 P1–P2)

本文件即为 SEALED-2 **基线冻结点**。此后 scored promote 相对本基线做
Gate 2(静默错不升 + 复核负载不升);人工确认后资格标记已落盘:

- `runs/hitl-sealed/improve/sealed2_qualified.ok`
- `runs/sealed2-workspace/improve/sealed2_qualified.ok`
- `runs/hitl-evo-b1/improve/sealed2_qualified.ok`

标记里的 `harness_id` 是**它资格化的那一个 harness**(本批是 `HAR-0004`)。
只有该 harness 自己晋升时 `basis` 才升为 `sealed2_qualified`;
**从它派生出来的新候选不继承这个资格**,要这个口径就得自己在 SEALED-2 上跑。

> 2026-08-06 修正:初版实现只看标记文件在不在,于是它成了 workspace 级
> 通行证。在工作台上跑通改进闭环时实测复现:一个刚从 12 份 HITL 挖出来的
> `due_date` 缺席候选被盖上「已在 SEALED-2 资格集上通过、公开口径可说在未见
> 封箱集上减负」—— 而它在本地 12 份上 `silent_absent 0→0`,同一条 cohort 在
> 88 份未见文档上实测多出 5 个真实到期日被静默丢掉
> (`docs/LOOP_GENERALIZATION_2026-08-06.md` 同口径)。现在
> `improve.sealed2_qualifies()` 要求标记点名候选本身,没点名的旧标记一律
> 不升级(宪章六:不说工件证明不了的话)。回归测试:
> `tests/test_improve.py::TestPromoteSafetyGate::
> test_sealed2_marker_for_another_harness_does_not_transfer`。

## 封存纪律(本批角色)

1. **SEALED-2 是当前唯一 final held-out / 晋升资格集**;
2. SEALED-1、HITL、旧 heldout **不得**再称为 final held-out;
3. **禁止**从本批挖 cohort、调判据、或把本批数字当开发反馈;
   结果驱动的规则/代码修改 = 本批作废,另抽 SEALED-3;
4. 开发/演化继续用 SEALED-1 未见子集与 HITL 批次。

## 限定清单

1. 主臂是 HAR-0004,不是 SEALED-1 的 HAR-0001 —— 跨批复述排序能力可以,
   跨批比较负载/拒绝率必须声明臂不同;
2. H4 缺值率 12.8% 显著低于前几批(~27–29%),方向与 machine_absent=100
   一致,可能是分布或策略差异,未做因果分解;
3. H6 34.6% 贴上界(线 35%),与旧留出/SEALED-1 同量级常态,不是「已压住」;
4. 抽取分两段完成(402 后续跑),`failed=0` 但 spent 口径以续跑摘要为准;
5. 未跑第二臂(HAR-0001 对照);需要同证据换策略时另开,不回溯改本文件。
