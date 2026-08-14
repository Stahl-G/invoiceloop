# HITL 窄放行轮结果(2026-08-14)

开发集测量,不带资格语义。不主张抽取变准。不把本轮接到 R1 S1 曲线上。

协议:`docs/HITL_NARROW_PROTOCOL_2026-08-14.md`。
产品契约:`docs/RELEASE_PROFILE_DESIGN_2026-08-14.md`。
对照只作背景:R1 S1 普查 0/20 零触达、中位 52s/槽。本轮队列更窄、中途改过系统,数字不可拼接。

---

## 预注册四点

| 指标 | 值 |
|---|---|
| 1. 零触达张数 | **4 / 20** |
| 2. 被打开的单的耗时(中位) | **12.5 s**(16 张开;单槽间隔记 0;>1h 休息剔除) |
| 3. 付款三字段未解数 | **0**(行走范围内无仍 `pending`/`abstain` 的槽) |
| 4. 探针静默错 | **0**(8 个 `QA_SAMPLE` 槽无人推翻 `auto_accept` / `auto_absent`) |

零触达 id:`075d4722d308410da3d8e3dd`、`50bbaa7c37374cc584cb06d3`、`848916b2c5264818be60e1f1`、`d264eaf836b642c6aae03d8b`。这四张付款三字段 ∩ 队列为空、也无 QA 探针,行走未打开。未打开 ≠ 抽取正确。残余仍按 ARCHITECTURE §6/§7,带 §8 限定:未挑出约 12%;未被 flag 的 TIER1 仍有 7.8% 真错。

打开的 16 张里,工作时间集中在两张:`31f273ad` 约 25 min,`a39706cb` 约 20 min。其余多槽单多数 4–81 s。单槽 4 张间隔为 0,把中位拉到 12.5 s。这不是「每张 12 秒审完」。

付款行走 24 槽均有裁决。`9a359ef4` 的 `amount_due` 被拒绝(估计单,页面上没有应付额),交付状态 **blocked**(1/20)。19 张 `ready_for_approval`,0 张已外发。

8 个探针:6 个缺席类探针人签 `confirm_absent`(与 expected-absent / absent-evidenced 同向,不是推翻自动接受);2 个 `QA_SAMPLE:policy_accepted_tier1`(`total_vat` / `total_net`)人签 `accept`。无人把自动接受/自动缺席改成相反结论。

---

## 关账快照(开发集)

行走 32 槽(付款三字段 ∩ `in_human_queue` 24 + QA 探针 8)。账本 33 行(含 `31f273ad invoice_number` 重写一次)。

- 裁决:accept 15 · correct 10 · confirm_absent 7 · reject 1
- 相邻槽中位:**30.0 s**(n=30;2 段 >1h 休息剔除;合计工作间隙约 74 min)
- 建议 `agree` 槽采纳 10/13(0.77)。17 行 `suggestion_seen` 空(注入前或该槽无建议)。3 个 agree 未采纳:`a39706cb seller_name`(建议 KTVL,接受了抬头 concat)、`db60e02c invoice_number`(建议少一位 9)、`96e0f58a seller_name`(建议呼号串,接受了 KBOT)

`correct` 中位 61.5 s,`accept` 中位 18 s。改值比点原值慢,符合「口径/绑定失败」而不是「看一眼」。

---

## 混淆声明

本轮**不是**冻结无预读臂:

1. 第一次裁决之后注入了中途 ADK 读图建议(`adk-invoice` / `gemini-3.7-flash`,stahl 同意)。账本前后 `suggestion_seen` 不可比。
2. 协议正文在第一次裁决后改过(人时闸先装后撤;stahl:不要时间限制)。按协议自己的冻结句,改字 = 臂不干净。
3. 复核中途查过 DocILE 标注(`a39706cb vendor_name` = Sinclair Broadcast Group)。盲读作废。
4. 与 R1 S1 比的是另一份行走(付款 3 + 探针 vs 普查十字段)、另一套建议、另一份名单。禁止画成同一条人时曲线。

无晋升义务。HAR-0023 仍是本轮冻结 harness,产品 active / HAR-0021 未动。

---

## 工件 sha

| 项 | 值 |
|---|---|
| 工作区 | `runs/hitl-narrow` |
| run | `runs/hitl-narrow/runs/run-0001` |
| 冻结 harness | HAR-0023 / `payment_required_v1` |
| 名单 sha256 | `2e3ed7ed8aec8c1c2849aeec96251c6f240ba3f602ef7616db9a53a91c035037` |
| 政策 sha256 | `3bb39cb83c3d0785f5b0c487fab6d2fe28823dce76df05557069cca72fc3fbc8` |
| 账本 sha256 | `838d38e06098efe4753fc5f3966a6442ba02403f8ab6fc49f6a35162319e4a6d` |
| 支持矩阵 sha256 | `f7b24e88dc02fa82279b910e02dd5c90cfa9c1db255aba7dfe7e5aede0f958d2` |
| 关账快照 | `runs/hitl-narrow/improve/closeout_run-0001.json` |
