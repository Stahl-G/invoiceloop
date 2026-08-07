# 单据类型接入调查(阶段 B,2026-08-07)

计划:`docs/DOCTYPE_PLAN_2026-08-07.md`。本文件只登记调查结论,**不落产品接入**。

复算:

```bash
INVOICELOOP_CORPUS=runs/sealed2-workspace python3 scripts/doctype_block_impact.py
```

## Q1 — 文档级裁决放哪?

### `evaluations` 消费方(穷举)

| 消费方 | 怎么读 | 若塞 `__document__` |
|---|---|---|
| `matrix.derive_document_records` | `evaluations[doc][field]` | 忽略未知 field 键 → 无害但类型裁决不可见 |
| `improve` 反事实重路由 | 同上 | 同上 |
| `adjudicate` verify 语义层 | 同上 | 同上 |
| `scripts/heldout_metrics.py` H4/H5 | **展平** `for doc in evaluations.values() for v in doc.values()` | **污染缺值率/citation 分母** |
| `scripts/adaptive_probe.py` | `.items()` 按字段 | 把 `__document__` 当字段 |
| C8 先例 | 盖回 `invoice_number` 槽 | 类型无自然归属槽 |

### 方案判定

| 方案 | 判定 |
|---|---|
| (a) `evaluations[doc]["__document__"]` | **否** —— 打断 heldout_metrics 展平与 probe |
| (b) `gate_report["document_checks"][doc_id]` | **首选** —— 加性;消费方显式读取;可进 `input_signature` |
| (c) 独立 `doctype_report.json` | 可作交付投影,但门禁事务签名要另挂 digest,两处真理 |

**选定(阶段 C 目标):(b)**。`findings` 仍可并行挂一条 `gate_id=doctype_evidence`
(blocking 与否由 Q2 粒度定)。历史 run 无该键 → 消费者必须 `.get`。

## Q2 — 阻断粒度对 SEALED-2 负载

无类型字面证据文档:**9** 份。

| 粒度 | human_queue | Δpp | 说明 |
|---|---|---|---|
| 基线 HAR-0004 | 468/1000 (46.8%) | — | |
| **文档级全槽 block** | **513/1000 (51.3%)** | **+4.5** | 新逼进队列 45 槽 |
| 仅依赖类型的判定 / 非阻断 finding | 468/1000 | **0** | 交付物标 9 份「类型不可信」 |

计划出口线是「三种都 >5pp 且抓不回静默错 → C 暂停」。
文档级 **+4.5pp < 5pp**,未触发暂停线;但 +4.5pp 换来的是把已机器放行的
无关字段也拖进队列 —— **与「抓类型谎报」不成比例**。

**选定粒度:只阻断/降级依赖类型的判定 + 非阻断 finding + 交付物可见。**
不把 9 份文档的全部 10 槽 `block`。阶段 C 按此接入;若后续要更严,
再开预注册测量。

## 阶段 C 入口条件

- [x] Q1 方案选定:(b) `document_checks`
- [x] Q2 粒度选定:typedep / finding(负载不净增)
- [x] 执行指纹加 `doctype_digest`(`snapshot.build_input_manifest` + `gates` input_signature)
- [x] 三套重放测试零 diff(`pytest` 489 passed,含 binding/port/heldout)

**阶段 C 已落地**(2026-08-07):`document_checks` + 非阻断 finding;
`deliverable.docs[*].type_trust`;SEALED-2 烟测 `40532c4e…` → fail/untrusted,
`086b0b4d…` → pass/`purchase_order`。下一站阶段 D。

阶段 D 已跑完并 **KILL**(见 `docs/DOCTYPE_STAGE_D_2026-08-07.md`)。
下一站阶段 E(适用性矩阵);不得用 `doc_class` 替代主体方向。
