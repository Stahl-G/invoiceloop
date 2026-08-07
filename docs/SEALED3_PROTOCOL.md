# SEALED-3 封箱评测协议(2026-08-07,执行前冻结)

SEALED-2 已因开发期词表/原型污染撤权退役(不再作未见晋升集;
见 `docs/SEALED2_RESULTS.md` 与污染裁决 F)。本协议再建一批真正未见的
100 份,作当前唯一 final held-out / 晋升资格集候选。

**与 SEALED-2 的关键差异:**
- 排除池已含 SEALED-1 + SEALED-2 全 200
  (`docs/development_exposure_manifest.json`,unique≈460);
- 抽样 PRNG 语境为 `invoiceloop-sealed3-v1`,避免撞流;
- **抽取后默认封箱不读**:不得用本批内容做发票类型/词表/策略挖矿;
  未开箱评测前不得写 RESULTS、不得挂资格标记。

## 0. 冻结对象(本文件 commit 时即冻结)

- 产品代码:本文件的首次提交即冻结点;
- 排除池:`docs/development_exposure_manifest.json`(须含 sealed1-100 + sealed2-100);
- 抽样实现:`invoiceloop/heldout.py::sealed_list(..., context="sealed3-v1")`;
- harness:开箱评测时锁定的 active harness(写入 RESULTS 时照登 digest)。

## 1. 随机种子承诺

- 随机源:drand 主网 beacon(`https://api.drand.sh/public/{round}`);
- **本批轮次:6356175**;种子 =
  `c3062ff4dfea53a7b36c67ee8f9a95b1180e37bb1999272d6bdb37d8284ad0e9`
  (该轮 `randomness` 字段原文;取种 UTC 2026-08-07);
- 抽样 = `heldout.sealed_list(seed, context="sealed3-v1")`:
  `random.Random("invoiceloop-sealed3-v1|" + seed).sample(sorted(pool), 100)`,
  pool = ≥4 记分字段标注 ∧ 不在暴露清单;
- 名单落盘:`docs/sealed3_doc_list.json`(与 workspace 副本一致);
  任何人可公开复算。

### 种子落盘

- 轮次:`6356175`
- 种子(hex):`c3062ff4dfea53a7b36c67ee8f9a95b1180e37bb1999272d6bdb37d8284ad0e9`
- 取种时间(UTC):`2026-08-07`(协议冻结时 `api.drand.sh/public/latest`)

## 2. 执行顺序(不许颠倒)

1. 暴露清单并入 SEALED-2 的 100 并 commit;
2. 本协议 commit(**先于名单开奖**);
3. 取 drand 公开轮次 → 填入 §1「种子落盘」→ commit;
4. `python3 -m invoiceloop sealed plan --workspace runs/sealed3-workspace
   --context sealed3-v1 --seed <hex> --seed-source "drand round <N>"`
   → 复制为 `docs/sealed3_doc_list.json` 并 **单独 commit**(先于任何 DWS 调用);
5. **仅在明确预算授权后**:
   `python3 -m invoiceloop sealed extract --workspace runs/sealed3-workspace`
   —— 200 次调用(understand + agentic),预算熔断 6000 credits;
6. **封箱不读**:extract 完成后只记录 ops 摘要
   (`extract_summary.json` 的 done/failed/spent);**不得** `run` / 开箱评测 /
   阅读 raw / 用本批调词表或策略,除非另开「开箱」裁决并写 RESULTS;
7. 开箱后:评测一次 → `docs/SEALED3_RESULTS.md`,数字照登;
   若作晋升资格:点名 harness 放置 `improve/sealed3_qualified.ok`
   (机制对齐 S2 的 harness 绑定,不得让派生候选继承)。

网络失败按断点续跑恢复;**结果驱动的规则/代码修改 = 本批作废,
SEALED-3 自动降级为回归集**,另批新种子重来。

## 3. 预注册终点

主终点沿用 SEALED-1 / HELDOUT 的 H1–H7 区间(见 `docs/SEALED1_PROTOCOL.md` §3)。
另增晋升门(开箱评测时适用):

| # | 量 | 通过 |
|---|---|---|
| P1 | Gate 2 silent_absent / silent_wrong 相对基线 | 不上升 |
| P2 | 字段复核负载相对基线 | 不上升 |

## 4. 主张纪律

- SEALED-3 未开箱前 ⇒ **不得**声称未见封箱减负或晋升资格;
  仅可报告抽取 ops(调用次数 / 失败 / 花费估计);
- SEALED-3 开箱通过 ⇒ 可以说「当前 HEAD 在一个开发期未见的 100 份封箱集上
  保持 H1–H6 量级 / 负载不升且静默错不升」;
- SEALED-1、SEALED-2、HITL、旧 heldout-100 **一律不得**再称为 final held-out;
- SEALED-2 上的 `sealed2_qualified` 路径已撤权,不得复活为未见证据。
