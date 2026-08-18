# HITL 窄放行轮(2026-08-14,第一次裁决前冻结)

本轮不是 R1 的 S2–S5,也不是原协议的 R2。R1 已在 S2 第一次裁决前预注册终止
(`docs/HITL_R1_TERMINATION_2026-08-14.md`)。本文件第一次提交即冻结;
本轮第一次裁决之后改任何一字 = 本轮作废。

产品契约:`docs/RELEASE_PROFILE_DESIGN_2026-08-14.md`。
办法 1 为主(付款三字段挡住放行,预算封顶,不再普查十字段);
办法 2 为辅(口径一次签署,建议层预填,金额三元组同屏看)。

不主张抽取变准。不把自动字段比例当首要成功指标。

---

## 1. 语料

- 池:原 R2 的 100 份(`docs/hitl_r2_doc_list.json`),即 R1 用剩的广播
  strong/weak 存盘文档。R1 的 100 份不进本轮(人已见过,计时不纯)。
- **sealed4-100 永不进入**。
- 本轮 20 份,种子 `invoiceloop-hitl-narrow-2026-08-14`,
  `random.Random(int(sha256(seed)[:16], 16)).sample(r2, 20)` 后排序。
  名单 `docs/hitl_narrow_doc_list.json`,同 commit 冻结,sha 校验。
- 零新 DWS 调用。无 API 预读(R1 组合臂 52s/槽 vs 对照 28s,本轮不复用该臂)。

---

## 2. 冻结 harness 与口径

- 路由:HAR-0023 = HAR-0021 的缺席规则
  + `release_profile.id = payment_required_v1`
  (`invoice_number`, `seller_name`, `amount_due`)
  + `release_tier1_explicit: false`(CLEAN TIER1 标 `policy_accepted`,
  5% `policy_accepted_tier1` 探针进队列)。
  政策文件:`docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json`。
  产品 active / HAR-0021 不动。
- 口径政策一次签署,建议层预填,不写账本:
  `docs/evidence/narrow_v1_2026-08-14/caliber_broadcast_v1.json`。
  买方 = 账单名块(保留 Attn,去掉街道);卖方 = 台站/刊物;
  到期日 = 印出的日历日,否则 `due_date.py` 派生。人不再在每张单上改口径。
- 金额三元组(Gross / Commission / Net Due)由独立 OCR 对齐,建议进
  `amount_due`(及能唯一对应的 gross/net)。工作台在付款槽上同屏展示三元组,
  人签的是 `amount_due`,不是三个槽。

建议 tag(run 后展示型注入,不进指纹):`caliber`、`triad`、`derived`。
不注入 xmode(R1 的 split 是人时成本)。

---

## 3. 队列

- 行走范围 = 契约三字段 ∩ `in_human_queue`,并集任何 `QA_SAMPLE` 探针。
  其余字段留在支持矩阵,状态未复核。
- 序:先按单据最弱 `support_strength`(unsupported → corroborated),
  再按契约字段顺序。从高风险单据往下,不是随机翻。
- **不设工作时间上限。** 不写 `review_budget.json`,不因人时拒绝 `/decide`。
  关账仍可按相邻 `decided_at` 记耗时(>1h 休息剔除),那是测量,不是闸。
  未批的单保持 `ready_for_approval`,不外发。
- 残余风险必须写在队列页上,带 §8 限定:未挑出约 12%;未被 flag 的 TIER1
  仍有 7.8% 真错。未复核 ≠ 正确。

---

## 4. 测量(开发集,不带资格语义)

预注册,不挑着报:

1. **零触达张数**:契约字段 ∪ 探针 都不是 `review` 的张数 / 20
2. **被打开的单的耗时**:该单第一条与最后一条行走槽裁决的间隔
   (休息 >1h 剔除);未打开的单不进分母
3. **付款三字段未解数**:行走范围内仍 `pending`/`abstain` 的槽
4. **探针静默错**:人推翻 `auto_accept` / `auto_absent` 的探针槽数

对照:R1 S1 普查 0/20 零触达、中位 52s/槽、约 3 小时/20 张。不拼接那条曲线。

---

## 5. 产出

`docs/HITL_NARROW_<日期>.md`:上列四点 + 混淆声明 + 名单/账本/harness sha。
无晋升义务。改进候选另立,不在人时预算里。
