# 文档触达四臂结果(2026-08-18,开发集,零 API)

不带资格语义。不主张抽取变准。不把本轮接到 R1 S1,也不接到 HITL-narrow 4/20。
零触达 ≠ 抽取正确。残余仍带 `ARCHITECTURE.md` §8 三条限定。

协议:`docs/DOCTOUCH_PREREG_2026-08-18.md`(commit `2f4a31c`,15:55:30,早于任何结果)。
仪器:`scripts/doctouch_arms.py`(commit `c0b0e49`)。
指标文件 mtime:2026-08-18 16:02:40。时间序可查。

## 0. 本轮能说和不能说的

窄契约把必须打开的发票从 **100% 降到约 89%** —— 真的降了,但不是「大部分发票不用打开」。
预注册 §5 写过:若 D 落在 20–35%,结论必须用「约七成要打开」那句;实测 **10.8%**,连那个区间都没进,**不许把「约七成」套在「约九成」上**。

本轮 **不是**资格结果。660 份全部在 `development_exposure_manifest.json` 里,其中 400 份属封箱名单。既未曝光又未封箱的非广播文档:0 份。

## 1. 预注册五条预测(错了照登)

| 预测 | 实测 | |
|---|---|---|
| A、B 零触达 ≈ 0% | A 0/660;B 6/660 = 0.9%(strong 6 张) | 大致对 |
| D 落在 **20–35%** | **71/660 = 10.8%**(strong 11.0%) | **错,偏低** |
| D 优于 C,差 < 10pp | D **差于** C(10.8% vs 12.3%) | **方向反了** |
| none 零触达低于 strong | D:none **13.3%** > strong **11.0%** | **方向反了** |
| none 真静默会上升 | 三层各 1,合计 3;B/C/D 相同 | **不是 none 独有** |

## 2. 四臂 × 三层(主要终点 = 文档零触达)

| 臂 | 闸 | `release_tier1_explicit` | strong 372 | weak 198 | none 90 | ALL 660 |
|---|---|---|---|---|---|---|
| A HAR-0001 | 普查 10 | true | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | **0 (0.0%)** |
| B HAR-0021 | 普查 10 | true | 6 (1.6%) | 0 (0.0%) | 0 (0.0%) | **6 (0.9%)** |
| C HAR-0021 投影付款 3 | 付款 3 | true | 49 (13.2%) | 19 (9.6%) | 13 (14.4%) | **81 (12.3%)** |
| D HAR-0023 | 付款 3 | **false** | 41 (11.0%) | 18 (9.1%) | 12 (13.3%) | **71 (10.8%)** |

协议要求三层分开报,不合并成一层。ALL 只作合计,不当成第四层。

触达构成(ALL):

| 臂 | 契约未解槽 | QA 探针槽 | 人队列槽 | 真静默 | 口径争议 | silent_wrong / value_hits |
|---|---|---|---|---|---|---|
| A | 3988 | 0 | 3988 | 0 | 0 | 359/2224 |
| B | 3148 | 218 | 3148 | 3 | 9 | 359/2224 |
| C | 854 | 218 | 3148 | 3 | 9 | 359/2224 |
| D | 889 | 287 | 3217 | 3 | 9 | 357/2175 |

C 与 D 的差 = `release_tier1_explicit: false` 引入的 TIER1 5% QA(探针槽 218→287)。**D 按文档口径差于 C,不是噪声**:出货旗标带着它,是为了「不伪造人工 accept」,不是为了性能。真静默与口径争议未升。

分层明细见 `docs/evidence/doctouch_2026-08-18/doctouch_metrics.json`。

## 3. 机制:三闸合取,不是流水线故障

HAR-0023 三张闸的自动率(`auto_accept` 或 `auto_absent`):

| 字段 | 自动 | 独立合取中的角色 |
|---|---|---|
| `invoice_number` | 400/660 = **60.6%** | |
| `seller_name` | 383/660 = **58.0%** | |
| `amount_due` | 308/660 = **46.7%** | 上限 |

0.606 × 0.580 × 0.467 = **16.4%**。盘上三闸都自动 **113/660 = 17.1%**,合取成立。QA 探针再拉走一批,落到 10.8%。

「探针不算打开」= **126/660 = 19.1%**(含被探针拉进复核的 35 个 CLEAN 闸槽)。与「invoice_number 总能自动」同为 126 是巧合,两行同值不矛盾。

打开形状(互斥,和 660):

| 形状 | 张数 |
|---|---|
| 仅 `amount_due` | 141 |
| `amount_due` + `seller_name` | 79 |
| 三闸都要人 | 79 |
| 仅 `invoice_number` | 76 |
| **零触达** | **71** |
| 仅 `seller_name` | 67 |
| `amount_due` + `invoice_number` | 53 |
| `invoice_number` + `seller_name` | 52 |
| 仅非闸 QA 探针 | 42 |

`amount_due` 出现在 **352/660 (53.3%)** 张要打开的单上。字段级自动率 3383/6600 = 51.3% 只许出现在实验室索引,不是产品 KPI。

## 4. 打开原因:两口径都登(勘误)

裁决包写过 `amount_due` 352 张中 **131** 张算术门禁、`seller_name` 277 张中 **178** 张双模式不同意(64%)。复算后:

### `amount_due`(352 张在复核)

| 口径 | 数 | 说明 |
|---|---|---|
| 路由**首选**原因码 `GATE_FAIL:arithmetic_consistency` | **131** | 与裁决包一致,可复现 |
| `gate_report` `arithmetic_consistency == fail` | **140** | 全部落在这 352 内;另 79 槽 `unavailable`(恒等式没评到) |
| 某份裁决里的 106 | **无法复现** | 不采用 |

差额 9 张:门禁已 `fail`,但路由因 `UNSUPPORTED` 抢先,首选原因码不是算术。路由是 if/elif,硬条件里 `slot_blocking` / `unsupported` 先于 `GATE_FAIL:*`。

其余首选原因码:双模式不一致 53、UNSUPPORTED 51、SLOT_BLOCKING 50、引用打不回 43、CLEAN+QA 21、field_wellformed 3。

### `seller_name`(277 张在复核)

| 口径 | 数 | 占 277 |
|---|---|---|
| 路由首选 `GATE_FAIL:cross_mode_agreement` | **178** | 64% |
| `gate_report` `cross_mode_agreement == fail` | **242** | **87%** |

包上的 64% 是首选原因码,成立;门禁口径更重。差额 64 张被 `UNSUPPORTED`(47)或 `SLOT_BLOCKING`(17)抢先。

分解冻在 `docs/evidence/doctouch_2026-08-18/open_reasons.json`。

## 5. 反事实(标价,不是提案)

| 若 | 零触达 |
|---|---|
| 现口径(QA 算打开) | 71 (10.8%) |
| 探针不算打开 | 126 (19.1%) |
| `seller_name` 总能自动 | 122 (18.5%) |
| `invoice_number` 总能自动 | 126 (19.1%) |
| `amount_due` 总能自动 | 170 (25.8%) |
| amount_due 总能自动且忽略 QA | 263 (39.8%) |

即使 `amount_due` 总能自动,也只进入预注册写过的 20–35% 区间。关掉算术门禁会把宪章五点名的口径争议变成静默过账,本轮不改闸。

## 6. 产品裁决(2026-08-18,两份独立裁决的交集)

主 KPI 维持文档零触达。`amount_due` / `seller_name` 继续挡付款;QA 探针继续算打开;`release_tier1_explicit: false` 维持(D<C 照登)。HAR-0023 **不晋升**产品 active。默认 harness 仍是普查(HAR-0021);`payment_required_v1` 是可选付款 profile / HITL 工作台配置。

对外只许这一句数字句,且必须带全限定:

> On the 2026-08-18 zero-API development run (n=660, all previously exposed; not a qualification result), HAR-0023 left 10.8% of documents untouched; about 89% still required opening.

在未曝光资格集给出同样闸定义下的数字之前,「窄放行降低打开张数」不得写成产品能力。

原定人时第二轮不做。算术门禁失败里「口径争议 / 真算错」的比例路由测不出,若将来要测,须新写小协议、先冻结,不当整轮 HITL,禁止接到 R1 或接到 71/660。

## 7. 复算

```bash
python3 scripts/doctouch_arms.py --out runs/doctouch-2026-08-18
```

零 API。A/B/D 各一次 `pipeline.run`(门禁吃 policy,不能跑一次再换策略重算)。C 是 B 的路由投影到付款三字段,不重跑。

政策文件 sha256:

| 臂 | 文件 | sha256 |
|---|---|---|
| A HAR-0001 | `harness._builtin_policy()` | (digest `395c5650…cf97`) |
| B HAR-0021 | `docs/evidence/absence_v3_2026-08-10/HAR-0021.routing_policy.json` | `bed2a20912c59fd5355873448d2d0f6c5a18545c25e64404d59ddb83b776bbc4` |
| D HAR-0023 | `docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json` | `3bb39cb83c3d0785f5b0c487fab6d2fe28823dce76df05557069cca72fc3fbc8` |

路由 digest:HAR-0021 `25a17132…8c00`;HAR-0023 `001016d6…f112`。
