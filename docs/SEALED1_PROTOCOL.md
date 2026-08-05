# SEALED-1 封箱评测协议(2026-08-05,执行前冻结)

69 评判决:旧 100 份留出集的案例进过开发过程(C3/C8 修复、漂移分析),
只能当回归/演化集,不再是 final held-out。本协议建一个真正未见的封箱集。
**与旧 HELDOUT.md 的关键差异:取样种子来自代码冻结之后才存在的外部
随机源,开发期间名单机械不可预知(高级裁决一);排除池是全量暴露清单,
不只是两份正式名单(高级裁决二)。**

## 0. 冻结对象(本文件 commit 时即冻结)

- 产品代码:commit `___`(本文件同 commit 记录);
- 评测脚本 sha256:
  - `scripts/heldout_metrics.py` = a486e82f…01d804
  - `scripts/baseline_comparison.py` = 5eb34dcb…c865eb
  - `invoiceloop/heldout.py`(取样/抽取驱动) = e5588497…40d4cbf
- 排除池:`docs/development_exposure_manifest.json`(260 份:
  校准 160 + 旧留出 100 + vendored demo 3,逐条带 reason/source);
- harness:包内 HAR-0001(`release_tier1_explicit: true`,零 cohort)。

## 1. 随机种子承诺(先承诺,后开奖)

- 随机源:drand 主网 beacon(`https://api.drand.sh/public/{round}`,
  30 秒一轮,链上不可预测、事后可公开验证);
- **承诺轮次:6350246 ≈ 2026-08-05T14:00:00Z**(本文件 commit 于
  ~10:15Z,轮次在未来 —— commit 时该轮随机性尚不存在);
- 种子 = 该轮 `randomness` 字段(hex)原文;抽样 =
  `heldout.sealed_list(seed)`:`random.Random("invoiceloop-sealed1-v1|" +
  seed).sample(sorted(pool), 100)`,pool = ≥4 记分字段标注 ∧ 不在暴露清单;
- 任何人事后可用同一轮次 + 同一代码复算名单 —— 可验证,不可预知。

## 2. 执行顺序(不许颠倒)

1. ✅ 修复 1–5 落地、345 测试全绿、commit;
2. ✅ 暴露清单生成并 commit;
3. 本协议 + 脚本哈希 commit(**先承诺轮次**);
4. 轮次开奖后:取 randomness → `python3 -m invoiceloop sealed plan
   --workspace runs/sealed1-workspace --seed <hex> --seed-source
   "drand round 6350246"` → **名单 commit**(先于任何 DWS 调用);
5. `python3 -m invoiceloop sealed extract --workspace runs/sealed1-workspace`
   —— 200 次调用(understand + agentic),预算熔断 6000 credits
   (参照旧留出集实测 4,758);key 只从 `DWS_API_KEYS` 或
   `~/.config/invoiceloop/heldout.keys` 读;断点续跑;4xx 也是证据;
6. `INVOICELOOP_CORPUS=runs/sealed1-workspace python3 -m invoiceloop run
   --out runs/sealed1 --doc-ids <名单>`;
7. 评测**一次**(见 §3),结果写入 docs/SEALED1_RESULTS.md,数字照登;
8. 打 evidence bundle(raw + run 工件 + 评测输出 + 命令日志),
   公布 sha256。

网络失败按既有断点续跑恢复;**结果驱动的规则/代码修改 = 本批作废,
SEALED-1 自动降级为回归集**,另批新种子重来。

## 3. 预注册终点(执行后不得修改)

### 主终点(资格目标:解除 held-out ceiling)

当前 HEAD 在未见集上的可靠性与运行闭环。判据沿用 HELDOUT.md 的区间
(对照组 = 校准 160 同口径实测值):

| # | 量 | 通过区间 |
|---|---|---|
| H1 | 分诊 lift(前50%偏差率/后50%) | > 1.5 |
| H2 | coverage@46% | > 55% |
| H3 | 复核召回 | > 55% |
| H4 | extraction_present 缺失率 | 10–45% |
| H5 | citation 可判子集失败率 | < 15% |
| H6 | 冻结拒绝率 | 5–35% |
| H7(新) | 运行闭环 | run 完成 + bundle 四层 verify 通过 |

判定同旧协议:H1 不达标 = 整体失败;其余不达标 = 如实写入限定清单,
附数字,不调判据重测。

### 次终点(研究目标:排序比较,**不预设 InvoiceLoop 胜出**)

- paired recall difference @ 复核预算 10/20/30/40%(分诊序 vs 置信度升序,
  同一批槽、同一预算,配对差);
- matched-coverage selective risk:取两排序覆盖相同的点比静默错误;
- 按文档 bootstrap 的 paired 95% CI(种子固定 42);
- tie 规则:confidence 平局固定 (doc_id, field) 破 + 切入同分组时报
  best/worst/expected(已在 baseline_comparison.py 实现并冻结);
- 功效声明(事前写下):100 份 × 285 槽量级,几个百分点的差异**可能
  达不到统计显著**;不显著不是实验失败,如实报告点估计 + CI 即可。
  任何结果下都不改代码继续用本批。

## 4. 主张纪律(评测前后都有效)

- SEALED-1 通过 ⇒ 可以说「当前 HEAD 在一个开发期未见的 100 份封箱集上
  保持 H1–H6 量级」;不 ⇒ 限定清单照登;
- 次终点无论方向 ⇒ 只报数字与 CI;「优于 confidence 排序」只有在
  paired CI 下界 > 0 时才许说,且必须带 tie 范围附注;
- 本批不兼任 PROMOTION-1 资格集(晋升资格集是一次性消耗品,要另批)。
