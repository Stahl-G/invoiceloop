# QUALIFICATION_NARROW_V2_2026-08-23 —— 污染恢复轮协议

本协议与名单在任何 v2 DWS 调用之前冻结。v1 已按其自身废臂条款撤权；见
`docs/QUALIFICATION_NARROW_CONTAMINATION_2026-08-23.md`。v1 的 200 份已成为
开发暴露数据，只用来形成本协议的先验与安全终点，不进入 v2 池。

## 1. 两个问题，禁止混成一句

1. **工作流效果**：HAR-0023 在全新未曝光文档上的路由时零触碰率是否仍落在
   5–20%。这是“有没有 review 槽/QA 探针使人打开”的属性。
2. **安全晋升**：那些零触碰文档的三个付款闸字段，是否在本语料真值下零真静默、
   零错值、零不可对拍。只有这条也过，工作流效果才可升级为产品能力。

第一条成立、第二条失败 = 有效的负资格结果，不是“差一点通过”。

## 2. 语料、曝光 registry 与抽样

- context：`qual-narrow-v2`；盐：`invoiceloop-qual-narrow-v2`。
- 基池：`heldout_pool` 减 `development_exposure_manifest.json` 全量；再按
  `docs/qualification_exposure_registry.json` 的 context 关系减 SEALED-4 100 份与
  qual-narrow-v1 200 份；要求 PDF、词级 OCR 齐全。
- v1 历史复算不漂移：v1 池仍是 4,831，v1 名单摘要仍为
  `22c566997043c5c8185431cb813f84d3eef5a95ca1b2b61bf6182a381fbdb052`。
- v2 池：**4,631**；
  `pool_sha256=e7265a79aacf57fd4dd9af3d709c7b5963ab71d36a3d17ae762af202ab797fb8`。
- 抽样：按 `sha256("invoiceloop-qual-narrow-v2|" + doc_id)` 升序取前 200，
  再按 doc_id 排序。
- v2 名单：200 份；
  `doc_ids_sha256=50be4e8f4554055c8e0a83cc19ecc20b31319728879dbf6f663218d8b82df853`；
  完整 JSON 字节
  `sha256=c533ba47d720ae0912425158b8b69fafac8d8b0470dc9475ff1eaee7ab36d614`。
- 冻结时盘上双模式齐全 860 份；摘要
  `010714561860f1e4b22429f2a31cd17cc18e135e1689d8fbd483c192f6f36ec4`；
  与 v2 名单交集 **0**。
- 名单权威副本：
  `docs/evidence/qual-narrow-v2-2026-08-23/plan/doc_list.json`。
- sampler / identity 控制面首次冻结于 `f70fc30`。池、名单摘要与 v1/v2 互斥均有测试钉住。

最小哈希使用常量盐，不用 drand：在冻结前，v2 池中没有任何文档有双模式结果，
因此盐不能用结果挑样；换来第三方无需信任 PRNG 版本即可复算。

## 3. 提取与身份门

- 200 份 × `understand + agentic` = 400 次 DWS 调用。
- 预算：**15,000 data-extraction credits**。预算熔断仍保留；若需续跑，身份必须完全相同。
- workspace：`runs/qual-narrow-v2-2026-08-23/`。
- 唯一合法命令形态：

      python -m invoiceloop qualify extract \
        --workspace runs/qual-narrow-v2-2026-08-23 \
        --round qual-narrow-v2-2026-08-23 \
        --protocol docs/QUALIFICATION_NARROW_V2_PROTOCOL_2026-08-23.md \
        --budget 15000

在读取 key、装载客户端或发 API 前，确定性控制面必须验证：

1. `plan/MANIFEST.sha256`、协议、冻结名单及 registry 副本都已提交且等于 HEAD；
2. workspace 名单逐字节等于冻结副本，且可由当前 context / pool 复算；
3. 当前 tracked worktree 干净；
4. `qualification_run_identity.json` 不存在时 raw 必须为空；存在时身份必须完全相同。

抽取期间每次调用前重核同一身份。协议、名单、registry、sampler、extractor 或 tracked
代码一旦变化，立即阻断；不得用“改动与数字无关”自行豁免。提取完成后由
`scripts/qual_extract_audit.py --qualification-round ... --qualification-protocol ...`
扫描 400 份原件、重算 run identity、记录每文件哈希与原始树哈希。

聚合审计任何 missing / extra / malformed / misbound / non-200 / identity mismatch =
`blocking_level: blocking`。最后一次 resume summary 不是总量证据。

## 4. 四臂与唯一代码身份

| 臂 | harness / 投影 | posting gate | 作用 |
|---|---|---|---|
| A | HAR-0001 | census | 结构性锚点 |
| B | HAR-0021 | census | 现役路由基线 |
| C | B routes + `payment_required_v1` | payment | 只换 posting gate |
| D | HAR-0023 | payment + `release_tier1_explicit:false` | 候选 |

A/B/D 都跑完整 pipeline；C 只投影 B routes。`scripts/doctouch_arms.py` 必须带 v2
`--doc-list`，且只能从干净 commit 执行。三个 arm identity 与 run_manifest 必须绑定
同一个代码 revision、策略/schema/名单摘要；任何旧目录身份不等立即阻断。

每臂必须有 200 × 10 = 2,000 个唯一 `(doc_id, field)` 路由槽，不能缺、不能多、
不能重复。strong / weak / none 分层照登，ALL 只作合计。

## 5. 预注册预测：错了照登

v1 已污染，不能作 qualification；但它已经曝光，允许作为开发先验。基于 v1：

| # | 预测 | 性质 |
|---|---|---|
| P1 | A 零触碰 = 0/200 | 结构性锚点，不算效果 |
| P2 | D 零触碰落在 5–20% | 工作流主终点 |
| P3 | C 零触碰 ≥ D | D 的额外 QA 探针只会增加触碰 |
| P4 | D 全臂 `silent_wrong` ≤ B | 与旧报告连续，但不是零触碰安全门 |
| P5 | D 零触碰付款子集 `silent_wrong` 落在 8–18，错误文档 6–14 | v1 为 12 槽/10 文档；预期风险会复现 |
| P6 | D 零触碰付款子集不可对拍 auto-accept 槽 0–6 | v1 为 4；缺口单列，不准藏在分母里 |
| P7 | 三付款闸全自动占 15–19% | v1 为 17.0% |

P5 明确预期非零，与下面安全晋升线的“必须为零”并不矛盾：本轮很可能得到一个
有效、可预期的资格失败。预注册不是许愿。

零触碰率报 95% Wilson 区间。错值按 DocILE 标注 + 现役 `eval_normalise` 计；
口径争议单列，不偷进 silent_absent_true，也不把值差异自动解释成供应商错误。

## 6. 晋升裁定

分三层裁定，不许用下一层掩盖上一层：

### I. 轮次完整性

- 聚合抽取审计完整且 identity 一致；
- A/B/D 三臂同代码身份，路由矩阵完整；
- 无协议/名单/registry/code 污染。

不过：本轮作废；数字只能进污染记录。

### II. 工作流效果复现

- P2 成立；P1/P3 用于管道与机制校验。

过：只准说“在该未曝光 DocILE 轮次测得路由时零触碰 X%”，仍不得说安全产品能力。

### III. 安全产品能力

D 臂**零触碰付款子集**同时满足：

1. `silent_absent_true == 0`；
2. `silent_wrong == 0`；
3. `unscored_auto_accept_slots == 0`。

任何一项非零 = safety qualification **FAIL**。P4 的全臂非劣不能替代这三条，
因为产品主张指向的正是没人打开的文档。

只有 I、II、III 全过，才可把窄放行写成安全产品能力。否则 HAR-0023 不晋升，
默认 census 不变，结果页头部直接写失败原因。

## 7. 与 ADK 人类行走的顺序

先完成 v2 路由、补充安全指标、结果裁定与证据提交，之后才从 v2 人队列确定性抽
20 份 ADK walk。走前建议工件与 provenance map 必须先冻结并提交；人类第一条裁决
之后不许补读、改建议或改协议。

即使安全资格失败，ADK walk 仍可作为独立的人类问责证据继续，但材料必须明确：
它不能把失败的自动放行重新包装成通过。

## 8. 公开边界

始终带：单一语料 DocILE、单一供应商 Nutrient DWS、单一真值口径。
不说抽取更准；不把零触碰率写成人力节省率；不把路由支持写成值正确；
`NOT MEASURED` 与失败项原样公开。
