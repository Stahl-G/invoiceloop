# SEALED-2 封箱评测协议(2026-08-06,执行前冻结)

SEALED-1 已完成 final-held-out 职责并降级为演化/回归集
(见 `docs/SEALED1_RESULTS.md` 限定 4、`docs/LOOP_GENERALIZATION_2026-08-06.md`)。
本协议再建一批真正未见的 100 份,作晋升资格集(PROMOTION-1)与「未见数据」
公开口径的唯一依据。

**与 SEALED-1 的关键差异:**
- 排除池已含 SEALED-1 全 100(`docs/development_exposure_manifest.json`);
- 抽样 PRNG 语境为 `invoiceloop-sealed2-v1`(不是 sealed1-v1),避免撞流;
- 本批兼任晋升资格集;结果驱动的规则/代码修改 = 本批作废。

## 0. 冻结对象(本文件 commit 时即冻结)

- 产品代码:本文件的首次提交即冻结点;
- 排除池:`docs/development_exposure_manifest.json`(须含 sealed1-100);
- 抽样实现:`invoiceloop/heldout.py::sealed_list(..., context="sealed2-v1")`;
- harness:评测时锁定的 active harness(写入 RESULTS 时照登 digest)。

## 1. 随机种子承诺

- 随机源:drand 主网 beacon(`https://api.drand.sh/public/{round}`);
- **本批轮次:6352483**;种子 =
  `b99de6bbc5e0c20707ceda77aae574391266b8d8dd5114bb8227523b680a1e59`
  (该轮 `randomness` 字段原文);
- 抽样 = `heldout.sealed_list(seed, context="sealed2-v1")`:
  `random.Random("invoiceloop-sealed2-v1|" + seed).sample(sorted(pool), 100)`,
  pool = ≥4 记分字段标注 ∧ 不在暴露清单;
- 名单落盘:`docs/sealed2_doc_list.json`(与 workspace 副本一致);
  任何人可公开复算。

## 2. 执行顺序(不许颠倒)

1. 暴露清单并入 SEALED-1 的 100 并 commit;
2. 本协议 commit(**先于名单开奖写入仓库的可验证顺序:
   协议与排除池冻结 → 取种子 → 名单落盘 commit → 才许 extract**);
3. `python3 -m invoiceloop sealed plan --workspace runs/sealed2-workspace
   --seed <hex> --seed-source "drand round <N>"` → 复制为
   `docs/sealed2_doc_list.json` 并 **单独 commit**(先于任何 DWS 调用);
4. **仅在明确预算授权后**:
   `python3 -m invoiceloop sealed extract --workspace runs/sealed2-workspace`
   —— 200 次调用(understand + agentic),预算熔断 6000 credits;
5. `INVOICELOOP_CORPUS=runs/sealed2-workspace python3 -m invoiceloop run
   --out runs/sealed2 --doc-ids <名单>`;
6. 评测一次,结果写入 `docs/SEALED2_RESULTS.md`,数字照登;
7. 若作晋升资格:在目标 workspace 放置
   `improve/sealed2_qualified.ok`(人工确认 SEALED-2 eval 已过 Gate 2),
   此后 scored promote 的 `basis` 升为 `sealed2_qualified`。

网络失败按断点续跑恢复;**结果驱动的规则/代码修改 = 本批作废,
SEALED-2 自动降级为回归集**,另批新种子重来。

## 3. 预注册终点

主终点沿用 SEALED-1 / HELDOUT 的 H1–H7 区间(见 `docs/SEALED1_PROTOCOL.md` §3)。
另增晋升门:

| # | 量 | 通过 |
|---|---|---|
| P1 | Gate 2 silent_absent / silent_wrong 相对基线 | 不上升 |
| P2 | 字段复核负载相对基线 | 不上升 |

## 4. 主张纪律

- SEALED-2 通过 ⇒ 可以说「当前 HEAD 在一个开发期未见的 100 份封箱集上
  保持 H1–H6 量级 / 负载不升且静默错不升」;
- SEALED-1、HITL-12、旧 heldout-100 **一律不得**再称为 final held-out;
- 未跑 extract 前,promote 即使 `pareto_gated` 也只能用
  `basis=evo_truth_replay`,不得声称未见封箱减负。
