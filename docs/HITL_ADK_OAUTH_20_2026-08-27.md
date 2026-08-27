# HITL 实验记录：ADK OAuth 20 份独立 run（2026-08-27）

状态：**开发集 / 探索性结果**。本记录不构成资格测试、不构成晋升依据，
也不估计模型抽取准确率。

协议背景：本轮沿用
[`HITL_NARROW_PROTOCOL_2026-08-14.md`](HITL_NARROW_PROTOCOL_2026-08-14.md)
的 20 份广播语料和 `HAR-0023` 付款字段范围，但增加了 ADK 读图建议层，
并在工作台中进行了人工裁决。因此它不是原协议预注册指标的干净复测，不能
和 2026-08-14 的人时或零触达数字拼接。

## 1. 结论先行

- ADK 建议层在本轮 20 份单据上成功完成；20/20 没有 ADK 请求失败。
- 窄放行工作台实际落盘 **32 条人工裁决**：`accept 13`、`correct 11`、
  `confirm_absent 7`、`reject 1`。
- 对 7 条同时满足 `label_convention_disputed` 和
  `arithmetic_consistency = fail` 的 `amount_due` 行，人工全部接受了原值。
- 这支持一个**适用性 / 归因缺陷**判断：算术门按普通发票恒等式计算没有数值错误，
  但把“Gross 刊例价、Net/Due 扣除佣金或折扣后的实付额”当成了
  `gross == amount_due` 的普通发票模型，并在槽位层显示成算术失败。
- 这不支持关闭算术门，也不支持宣称“抽取变准”。同一批人工裁决仍包含 11 条
  修正和 1 条拒绝，说明队列中有真实抽取 / 绑定问题。

## 2. 实验身份与边界

| 项 | 记录 |
|---|---|
| 单据池 | `docs/hitl_narrow_doc_list.json`，20 份 DocILE 广播语料 |
| 单据名单 SHA-256 | `20315c0daa606ad098bcce6e91d16b01dcfc635805e9f9049fa6c9336496f25d` |
| 工作区 / run | 本机 `/private/tmp/invoiceloop-adk-oauth-20.jqyavx/hitl-clean/runs/run-0001` |
| Harness | `HAR-0023` |
| 输入 fingerprint | `140726a760d533c72c422c509182b66f729ddf63567c2ecb0b32091c40fccf06` |
| 代码版本 | `2dfb7b7db3327123eda638dfef1fb55b528fb228-dirty` |
| ADK 模型 | `gemini-3.7-flash` |
| ADK 路径 | Vertex AI / `aiplatform.googleapis.com` / `global` |
| ADK 鉴权 | gcloud 短期 OAuth access token，仅驻留内存；token 未写入工件 |
| 执行方式 | 并行，4 workers；此前成功 8 份，本次处理 12 份，12 成功、0 失败 |
| 人工身份 | `stahl`；单一 warm reviewer，裁决时可见 ADK 建议 |

账本、审批账本、ADK 读法、路由/矩阵、closeout/mine 报告与单据名单等
9 项关键工件已冻结进 repo：
[`docs/evidence/hitl-clean-2026-08-27/postwalk/`](evidence/hitl-clean-2026-08-27/postwalk/)
（含 `MANIFEST.sha256`）。PDF、OCR 与页面渲染图仍只在本机工作区，§8 的
哈希用于定位这些外部工件。`code_revision` 带 `dirty`，所以本记录不能被
解释为某个干净 Git commit 上的资格结果。

## 3. 机器侧结果（人工裁决前）

以下数字从本轮 `support_matrix.json` 和 `gate_report.json` 读取 / 重算，描述的是
机器分层，不是真值准确率：

| 项 | 数量 |
|---|---:|
| 文档 / 字段槽 | 20 / 200 |
| `corroborated` / `single_source` / `unsupported` | 128 / 4 / 68 |
| `requires_adjudication` | 114 |
| 全矩阵 `human_queue` | 89 |
| `machine_decided` / `machine_absent` | 86 / 25 |
| `applicability_disputed` | 21 |
| blocking findings | 18 |
| admitted claims / rejected drafts | 269 / 132 |
| rejected drafts：`dws_understand` / `dws_agentic` | 66 / 66 |

`arithmetic_consistency = fail` 共 20 行：`amount_due 7`、`total_gross 7`、
`total_net 2`、`total_vat 2`、`issue_date 1`、`due_date 1`。其中 16 行属于
`label_convention_disputed`。

窄工作台没有走完全部 89 条矩阵 human queue，而是按付款契约取出 32 条：
契约字段 24 条（`invoice_number`、`seller_name`、`amount_due`）加 8 条 QA
探针（`seller_vat_id`、`due_date`、`total_net`、`total_vat`）。因此“32 条裁决完成”
不等于 200 个字段全部人工复核完成。

## 4. 人工裁决结果

### 4.1 总量

| 指标 | 结果 |
|---|---:|
| 账本裁决行 | 32 |
| 覆盖文档 | 16 / 20 |
| `accept` | 13 |
| `correct` | 11 |
| `confirm_absent` | 7 |
| `reject` | 1 |
| 看见建议的裁决 | 19 / 32 |
| supersession | 0 |
| 裁决身份 | 32/32 为 `stahl` |

人工原因码分布为：`CONFIRMED_ABSENT 7`、`ROUTING_FALSE_POSITIVE 6`、
`WRONG_FIELD_MAPPING 4`、`WRONG_VALUE 3`、`BAD_SOURCE_BINDING 3`、
`OTHER 3`，另有 6 条未填写原因码。

交付投影当前为：18 份 `ready_for_approval`、1 份
`approved_for_export`、1 份 `blocked`。另有 1 条单独的审批记录，不能代表
整轮已经批准或外发。

AP-0001 的一个事实必须照登：被批准的 `075d4722` 是一张**零裁决单据**——
32 条裁决里没有任何一条落在它身上，审批记录的 `policy_disposed_fields`
列出了全部 10 个受评字段（全部由 HAR-0023 策略处置、无人读过任何槽），
批准理由是 `good`。这在本轮是合法动作（人签了字），但零触达 + 单词批准
理由这个组合作为产品信号偏弱，记录在案。

### 4.2 建议采纳与人时（closeout 口径）

| 指标 | 值 |
|---|---:|
| 计时裁决（excluded_gaps 2） | 29 |
| 中位人时/槽 | **112 s** |
| accept / correct / confirm_absent / reject 中位 | 78.5 / 167.5 / 157.5 / 119 s |
| 有字段级建议的槽 | 19 / 32 |
| 建议状态 agree / agree_rejected / split | 15 / 3 / 1 |
| agree 槽中被采纳 | 14 / 15（0.933） |

对照 2026-08-14 普查走查的中位 52 s/槽：本轮窄队列单槽更慢，但那轮是
十字段普查、本轮含 correct 类长耗时槽（167.5 s）。两轮测量口径不同，
不可拼接，照 2026-08-14 记录的规矩并列展示。

### 4.3 算术门 / 口径争议队列

7 条 `amount_due` 行的机器结果全部是“算术失败 + 口径争议”，人工结果全部
接受原值：

| doc_id | Gross | Net / Due | 人工结果 |
|---|---:|---:|---|
| `5c1c7960b46f4dfc9a5a44db` | 1,040.00 | 884.00 | accept |
| `9a359ef4cc4644ae9b5caaa4` | 23,600.00 | 20,060.00 | accept |
| `a39706cb2762474cb3e155b4` | 9,335.00 | 7,934.75 | accept |
| `db60e02cb0074cd5baf3cf01` | 1,472.40 | 1,418.66 | accept |
| `0c7df66268614502b65f4a3f` | 1,125.00 | 956.25 | accept |
| `5a8c7ec3518c4daa978b4eb9` | 780.00 | 663.00 | accept |
| `ba388b327d254ed384f97624` | 2,040.00 | 1,734.00 | accept |

这 7 条结果不能单独证明可以自动放行；它们证明的是：在当前窄队列和这位
人工复核者的观察下，`amount_due` 的值与页面一致，而机器的普通发票算术
解释不足以判断其错误。

### 4.4 重点案例：千分位金额的冻结绑定误报（`f47b8ee0...`）

`f47b8ee00eae416c94a083ca` 的三个金额槽（`amount_due`、`total_gross`、
`total_net`）在冻结事务被**同因拒绝**：DWS 返回 `1744.20`，页面印的是
`$1,744.20`。按 `[a-z0-9]+` 分词，值侧 token 为 `{1744, 20}`，文档侧是
`{1, 744, 20}`，交集只剩 `{20}`，覆盖率 0.5 < 0.8，三条草稿全部
`draft_rejected_at_freeze` → `unsupported` → 进人工队列。

- `amount_due` 在窄队列内，人工修正为 `$1,744.20`（HD-0020，
  `suggestion_seen: agree_rejected:$1,744.20`——ADK 读法也给了
  `$1,744.20`，但建议层不能补回被冻结拒绝的 DWS 声明）；
- `total_gross` / `total_net` 不是付款契约字段，留在支持矩阵上未经人看。

这是 [`ARCHITECTURE.md` §8b](../ARCHITECTURE.md) 已知边界的实战形态：
分词器把带千分位的金额切成高频 token。此前 §8b 记录的是"$0.00 切成
高频 token 导致**该拒的不拒**"（假阴性方向）；本例是同一个分词器的
**假阳性方向**——格式不同就把真值拒绝。两个方向都是 §8b 预言的
"换语料会放大、需重测"的家族。修法方向是 AMOUNT 绑定的格式等价
（`1744.20` ≡ `1,744.20`，保留纸面原值），不是放宽 0.8 阈值。



## 5. 重点案例：`0c7df662... / amount_due`

裁决记录为 `HD-0022`：

```text
decision:      accept
value:         $956.25
reason_code:   ROUTING_FALSE_POSITIVE
suggestion:    agree:$956.25
```

页面第 2 页的独立 OCR 同时读到：

```text
Gross Amount:      $1,125.00
Agency Commission: ($168.75)
Net Amount Due:    $956.25
```

页面关系是：

```text
1,125.00 - 168.75 = 956.25
```

但 `dws_understand` 返回的输入是：

```text
total_net   = 956.25
total_vat   = 68.75
total_gross = 1,125.00
amount_due  = 956.25
```

于是当前门禁按普通发票恒等式计算：

```text
C1: 956.25 + 68.75 = 1,025.00 != 1,125.00
C2: 1,125.00 != 956.25
```

`68.75` 没有页面 VAT 标签和绑定支持，支持矩阵将该值列为 unsupported；它不能
被用来证明 `amount_due` 错误。这里的缺陷不是浮点数计算，而是：

1. 通用 C2 把 `total_gross == amount_due` 当作所有发票都适用；
2. 算术失败按 feeding 字段归属，导致正确的 `amount_due` 也得到 fail；
3. `matrix.py` 已识别 `label_convention_disputed`，但 `routing.py` 先输出
   `GATE_FAIL:*`，遮住了口径争议和具体恒等式。

这是已知的解释性缺陷；历史记录见
[`ARM_RUN_LOG_2026-08-08.md:184`](ARM_RUN_LOG_2026-08-08.md:184)。实现位置见
[`gates.py:74`](../invoiceloop/gates.py#L74)、
[`matrix.py:28`](../invoiceloop/matrix.py#L28) 和
[`routing.py:253`](../invoiceloop/routing.py#L253)。

## 6. 其他人工信号

本轮不是“所有入队都是误报”：

- 3 条 `WRONG_VALUE`、4 条 `WRONG_FIELD_MAPPING`、3 条 `BAD_SOURCE_BINDING`
  说明模型值或字段绑定仍会产生真实问题；
- 7 条 `CONFIRMED_ABSENT` 说明“模型没有返回”与“页面明确缺失”需要分开；
- 1 条 `reject` 说明页面上没有对应发票号；
- 6 条明确使用 `ROUTING_FALSE_POSITIVE`，包括本记录的算术 / 口径案例。

因此本轮的改进信号应被拆成 typed findings：算术模型适用性、字段映射、页面
绑定和确实缺失，不能压成一个“路由准确率”。

## 7. 可复用结论与限制

可复用的工程结论：

1. 保留底层 C1/C2 失败记录，但应把恒等式 ID、输入值和失败字段带到工作台；
2. 对已识别的口径争议，用户界面应把 `LABEL_CONVENTION_DISPUTED` 作为主解释，
   算术失败作为上下文，而不是暗示 `amount_due` 数值错误；
3. 若要改变门禁适用范围，应建立版本化的 billing-model / commission 或 discount
   语义契约，并新增回归样本；不能全局关闭算术门；
4. 本次 run 保持冻结，不能用修复后的规则回写成“原来就通过”；
5. AMOUNT 字段的文档级绑定需要**格式等价**：`1744.20` 与 `$1,744.20` 是
   同一个值（§4.4 案例，三个真值槽被拒）。等价要在绑定层做、保留纸面
   原值，不许靠放宽 0.8 阈值——阈值放松会把 §8b 记录的假阴性家族一起
   放进来。

限制：20 份是开发集；人工复核者为单一 warm reviewer；32 条是窄队列而不是
全矩阵 200 槽；19 条看到建议且 ADK 与裁决同时存在；代码版本带 dirty；本轮
没有盲法、没有独立真值复核，也没有资格语义。另有两条程序性缺口照登：
裁决开始前没有先做 prewalk 证据冻结 commit（读法工件在裁决前已在盘，
但"建议先冻结、后裁决"的性质只能靠本记录声明，无法靠 commit 时序证明）；
`suggest_provenance` 冻结未运行，19 条带建议的裁决行 `suggestion_model`
为空（`suggestion_seen` 由工作台从 live TSV 记录）——建议溯源的精确对账
（P1 口径）在本轮不可评。因此本记录不报告准确率、提升率、
安全晋升或通用化结论。

## 8. 工件索引与哈希

本机外部工件根目录：

```text
/private/tmp/invoiceloop-adk-oauth-20.jqyavx/hitl-clean/runs/run-0001
```

| 工件 | SHA-256 |
|---|---|
| `run_manifest.json` | `3c5073e4639a9b8868a5264999dfc94fbed4b4d608883ccbcf03b9f85222cca5` |
| `input_manifest.json` | `8604337e9db917ec36c4079d2b9ec9b24ea56f5a24f35ce5932915ba89fe361a` |
| `oauth_run_metadata.json` | `247851a7dc8ae965b8654d9eab1cc26cf1cbf80063d572004cae88e538a34163` |
| `adjudication_ledger.jsonl` | `76046cbcb0991681f6a85d2f3c386f6d1e47cb20683195cbcf5cb7797c3b55f0` |
| `approve_ledger.jsonl` | `d221a6a5058f31c37089d3cb51d85685d6a2d72d588fc27c813596bead93bfd0` |
| `support_matrix.json` | `f7b24e88dc02fa82279b910e02dd5c90cfa9c1db255aba7dfe7e5aede0f958d2` |
| `gate_report.json` | `e9a5ea845d5cf10300cb51c1e6638f2312fa95b562f6a15ad96e6d4c8411604e` |
| `routing_report.json` | `cbf358a87b2671d483998a44e122b68257a8fd884d1dfc10b5d6f5e3f6fd69b9` |
| `review_snapshot.json` | `40ca7b947d2bb32fbed7d1cbac2ec8e39412d767cb68696185e7d7fb36714047` |
| `deliverable.json` | `9dc93929e6d856af32c16b723f550fad58bebd72a99beebc64ac2e0b501cffdc` |

review snapshot ID：`24710c22ecf53504464af4ca2655cd8a2b8e18e6c3267c8440abccd30f70694a`。

