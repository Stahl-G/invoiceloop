# 放行契约 `release_profile`(2026-08-14)

HITL R1 在 S2 第一次裁决前终止,见
[`HITL_R1_TERMINATION_2026-08-14.md`](HITL_R1_TERMINATION_2026-08-14.md)。
本文件是下一版本的产品契约,不是那一轮的补丁。

一句话:**交付从「十字段全裁决」改成「窄放行契约 + 全量支持矩阵 + 风险抽查」。**

不主张抽取变准。不主张未复核槽是对的。不把自动字段比例当首要成功指标。

---

## 1. 两个问题,分开答

| 问题 | 谁回答 | 不是谁 |
|---|---|---|
| 这个值有什么支持?该信到哪一档? | 支持矩阵(十字段全在,可零 API 重算) | 人不必给每个槽签字 |
| 这张单能不能付款/过账? | `release_profile` 规定的字段 + 文档级署名批准 | 路由策略不得授予外发权限(`approve.py`,2026-08-09) |

R1 把两个问题收成同一条「人工队列走完」。字段自动率约 50% 时,十字段合取
的零触达 ≈ 0(`scripts/doc_touch_economics.py`)。S1 实测 20/20 打开。

---

## 2. `release_profile`(加法,不改 HAR-0001)

政策键 `release_profile`。**缺省 = 普查**:全部记分字段的 `pending` /
`pending_tier1` / `abstain` 都挡住 `ready_for_approval`。包内 HAR-0001
不带这个键,SEALED 重放字节不变。

`release_tier1_explicit` **不关**。它继续禁止把 TIER1 的自动放行伪装成
人工 `accept`(字段状态仍是 `pending_tier1` 或 `policy_accepted`,取决于
该旗标)。它不再偷偷等于「十个 TIER1 槽都要人点完才能等人批单」。

冻结的产品默认:

```json
{
  "id": "payment_required_v1",
  "fields": ["invoice_number", "seller_name", "amount_due"]
}
```

字段集与 `doc_touch_economics.py` 的「付款必需(3 个)」同一份,改 id 才许
改集合。可选 `posting_required_v1` = 再加 `issue_date`、`seller_vat_id`,
本版不设为默认。

人类署名候选(`register_policy`)可以加上这个键。机器 `propose` 加它 =
lint 拒绝(第一版只许加 cohort)。晋升仍要 `--approved-by` + evaluate。
**不许**写进 HAR-0021 再假装 R1 后半段还在比。

---

## 3. 字段状态 vs 整单状态

字段层(矩阵/panel/deliverable.fields)诚实标签不改:

- 队列里没裁的,还是 `pending`
- TIER1 自动放行且 `release_tier1_explicit: true`,还是 `pending_tier1`
  (「关键字段没人逐槽签字」,不是「机器认为正确」)
- TIER2 自动放行,还是 `unreviewed_corroborated`

整单层,仅当政策带了 `release_profile` 时:

- 挡住 `ready_for_approval` 的,只剩契约字段上的 `pending` / `abstained` /
  `reject`(含 TIER2 契约成员,如 `seller_name`),以及账本完整性破坏
  (`accepted_unbound`、文档级阻断)
- 契约外字段的 `pending` / `pending_tier1` **不挡付款**。它们留在矩阵上,
  意思就是未人工复核
- 契约内 TIER1 的 `pending_tier1`(路由已是 `auto_accept`)不挡
  `ready_for_approval`。逐槽签字不是这张单的放行条件;文档级批准才是,
  且批准账本已经记录 `tier1_policy_disposed_fields`(2026-08-09 Northstar:
  知情之后才谈得上把自动放行开大)

缺省普查路径(无 profile)保持今日语义,含「`pending_tier1` 挡住整单」。

外发权限不变:只有 `approved_for_export`。机器最远到 `ready_for_approval`。

---

## 4. 人工队列(写边界,不是展示滤镜)

路由(`in_human_queue`)不因 profile 变松。硬阻断、unsupported、门禁失败、
口径争议、QA 探针,该进队列还进。

工作台默认行走范围 = **契约字段 ∩ 人工队列**,并集 **任何带 `QA_SAMPLE`
的探针槽**(探针不是损耗,是自动决策的前提)。契约外的非探针槽仍在矩阵/
交付页,不进默认行走。

人按时预算从高风险单据往下看(矩阵本就按 `support_strength` 升序)。预算
用尽后,未看的契约外字段保持未复核标签;未批的单据保持
`ready_for_approval`,不外发。

终止的 R1 工作区:`round_status.json` 为 `terminated` 时,工作台拒绝
`POST /decide`。那是停轮闸,不是 profile 机制。

---

## 5. 辅线(本版设计,本版不实现)

办法 2,不挡第 2–4 节落地:

1. **批次口径政策**(一次签署,不是每张单改买方名):卖方/买方身份块怎么切、
   NET 30 是否走 `due_date.py` 派生。现有 `scope.py` 管的是语料域授权,
   不是字段口径;口径政策另立工件,建议层预填,不写账本。
2. **金额三元组一次看**:`total_gross` / `total_net` / `amount_due` 在工作台
   上是一组,不是连续三个槽。OCR 标签对齐是建议,不覆盖草稿。

这两条是减「口径裁决混进槽队列」的人时。不配第 2 节,零触达张数仍然起不来。

---

## 6. 下一轮要测的(新协议,不拼接 R1)

开发集限定,预注册后再跑:

1. 20 张里有多少张完全不用打开(契约字段 ∪ 探针 都不是 `review`)
2. 每张被打开的单实际耗时(打开→离开,不是槽间隔中位冒充张成本)
3. 付款必需字段还有多少未解决(`pending`/`abstain`)
4. 抽样探针发现多少静默错误(人推翻 auto_accept / auto_absent)

不把「自动字段比例」当首要成功指标。不在改契约之后续画 R1 的 52s/槽。
