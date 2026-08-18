# 文档触达预注册(2026-08-18,开发集,零 API)

**本文件在跑出任何数字之前冻结。** 冻结机制 = 提交本文件的 commit 早于产出
结果的 commit;两者都在公开仓库里,时间顺序可查。看到结果之后改本文件正文
= 本轮作废,按 `HITL_R1_AMENDMENT_STAGED_2026-08-11.md` 的同一条纪律。

## 0. 问的是什么

**窄放行契约(`payment_required_v1`)能让多少张发票根本不用被人打开?**

AP 按「碰过几张单」计价。字段级复核负载从 60.2% 压到 55.7% 时,300 份开发集
的文档触达是 **300/300 = 100%**(`scripts/doc_touch_economics.py`,十字段合取,
每字段自动率 p 时零触达 ≈ p^10)。这一轮量的是文档口径,不是槽口径。

**为什么不需要人:** `release_profile.document_touch_metrics()` 只吃 routes
(`release_profile.py:127-148`)。零触达是**路由时属性**。窄放行轮那个 4/20
是路由算出来的;人做的是计时与探针捕获率,那两件在第二轮,不在本轮。

## 1. 冻结的定义

- **触达**:该单据存在任一槽满足「`route` 不在 `("auto_accept","auto_absent")`」
  且(该字段属契约字段集 **或** 该槽带 `QA_SAMPLE*` reason code)。
  **QA 探针算触达** —— 打开探针就是打开单据。与窄放行轮同一口径。
- **零触达**:该单据不满足上条。**零触达 ≠ 抽取正确**;残余误差仍按
  `ARCHITECTURE.md` §8 三条限定。
- **契约字段集**:`payment_required_v1` = `invoice_number` / `seller_name` /
  `amount_due`(`release_profile.PAYMENT_REQUIRED_V1`)。普查 = 全部 10 个记分字段。
- **静默错**:`safety_metrics.score_routes`,与晋升 Gate 2 同函数。
  `silent_absent_true` 与 `caliber_disputes` 分两列(truth-caliber-v1)。

## 2. 语料与分层

盘上**双模式响应齐全**的全部文档,`n = 660`。按 `scope.classify_broadcast_ocr`
的冻结实现分三层(逐字自 broadcast-pilot-v1):

| 层 | n |
|---|---|
| strong(呼号 + 术语 ≥2 次) | 372 |
| weak(单侧证据) | 198 |
| **none(非广播)** | **90** |

三层分别报,**不合并成一个总数**。none 层同时回答泛化问题:广播语料上挖出来
的缺席规则,搬到非广播上还成不成立。

## 3. 四个臂(A/B 分离两个变量)

| 臂 | 路由策略 | 放行闸 | 分离出什么 |
|---|---|---|---|
| **A** | HAR-0001 | 普查(10 字段) | 保守基线 |
| **B** | HAR-0021 | 普查(10 字段) | 广播 harness 单独在文档口径上买到了什么 |
| **C** | HAR-0021 | 付款 3 字段(投影) | **只把闸收窄**买到了什么 |
| **D** | HAR-0023 | 付款 3 字段 | 出货契约(= C + `release_tier1_explicit: false`) |

C 与 D 的差就是 `release_tier1_explicit: false` 的作用。HAR-0021 与 HAR-0023 的
`absent_*_cohorts` 与 `qa` 逐字相同(已核),所以这个分解是干净的。

政策文件取自仓库内已提交的冻结件:
`docs/evidence/absence_v3_2026-08-10/HAR-0021.routing_policy.json`、
`docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json`、
HAR-0001 取 `harness._builtin_policy()`。

## 4. 报哪些数(每臂 × 每层)

1. **零触达张数**(主要终点)与占比
2. 触达单据的**契约字段未解槽数**
3. **QA 探针槽数**(触达里有多少是探针拉进来的)
4. `silent_absent_true` / `caliber_disputes` / `silent_wrong`(安全侧,不许降人工
   靠多静默)

## 5. 预测(写在前面,错了照登)

- **A 与 B 的零触达都 ≈ 0%**。十字段合取,`doc_touch_economics` 的算术决定的。
- **D 的零触达落在 20–35%**,即**仍有约七成发票要打开**。依据:窄放行轮
  4/20 = 20%,`doc_touch_economics` 三字段口径 27.7%。
- **D 优于 C**,差值来自 `release_tier1_explicit: false`,幅度 < 10pp。
- **none 层的零触达低于 strong 层**,且 `silent_absent_true` 在 none 层**会上升**
  —— 缺席规则挖自 `seller_vat_id` 出现率 2% 的广播语料,而非广播是 16%(实测)。

**若 D 显著高于 35%**,我预测错了,照登,并且必须先查是不是探针没被算进触达。

**结论口径也先定死:** 若 D 落在预测区间,结论写成「窄契约把必须打开的发票从
100% 降到约七成 —— 真的降了,但不是『大部分发票不用看』」。不许跑完之后挑一个
更好听的说法。

## 6. 本轮**不能**得出的结论

- **不是资格结果。** 660 份**全部**在 `development_exposure_manifest.json` 里,
  其中 400 份属封箱名单。既未曝光又未封箱的非广播文档:**0 份**。
- 不测人时、不测探针捕获率 —— 那要人,在第二轮,另立协议。
- 不主张抽取变准。零触达单据的字段没有被任何人看过。
- n(none) = 90,小样本,只作方向性观察。

## 7. 执行

语料装配一次(复用 `hitl_round_setup._populate` 的形状,raw 源扩到全部
workspace),四臂在同一份装配上跑,零 API:

```bash
python3 scripts/doctouch_arms.py --out runs/doctouch-2026-08-18
```

结果写 `docs/DOCTOUCH_RESULTS_2026-08-18.md`,与本文件逐条对照。复算命令随结果
一起登。

## 8. 冻结签章

- 本文件 commit:结果产出前
- 代码状态:`main` @ 合并 PR #2 之后(`6905e63`)
- 参与臂的政策文件 sha256 随结果登记
