# QUALIFICATION_NARROW_2026-08-22 —— 资格集确认轮协议

冻结于本 commit,先于任何 API 调用。改了正文 = 臂不干净,照 HITL-narrow 先例声明。

实施计划:`docs/superpowers/plans/2026-08-22-hackathon-sprint.md`

## 1. 要回答什么

窄放行契约(`payment_required_v1`)在**从未被这个项目碰过**的文档上的零触达率。

`docs/DOCTOUCH_RESULTS_2026-08-18.md` §6 立的限定句是本轮的直接动因:
「在未曝光资格集给出同样闸定义下的数字之前,『窄放行降低打开张数』不得写成
产品能力。」08-18 那轮 660 份**全部是开发期曝光过的**,10.8% 因此只能当上限
参考,不能当产品能力。

## 2. 语料与抽样(可复算)

- 池 = `heldout_pool`(≥4 个记分字段标注、非校准 160)减
  `development_exposure_manifest.json` 全量(560),再减 `docs/sealed4_doc_list.json`
  (100),再要求 pdf 与词级 OCR 齐全。
- 池大小 = **4,831**
  `pool_sha256` = `c5232063e6cd03c0979bd8adcc2cd8dfe73b585fe5ca107285221eed03303ce5`
- 抽样 = 最小哈希:按 `sha256("invoiceloop-qual-narrow-v1|" + doc_id)` 升序取前 200,
  再按 doc_id 排序。语境 `qual-narrow-v1`,实现 `invoiceloop/heldout.py::qual_list`。
- 名单 200 份,副本 `docs/qual_narrow_doc_list.json`,冻结副本
  `docs/evidence/qual-narrow-2026-08-22/plan/`
  `doc_ids_sha256` = `22c566997043c5c8185431cb813f84d3eef5a95ca1b2b61bf6182a381fbdb052`
- **冻结那一刻盘上已有双模式响应的文档 660 份**
  `dual_mode_on_disk_sha256` = `c1e9372b82876d9d99c2f5431fdfc0f681a0089e3cbaca4eb14a133440a9f7ea`
  与本轮名单的交集 = **0**(`cmd_plan_qual` 在落盘前活查,非零直接 RuntimeError)。
- **为什么这轮的盐可以是常量**:SEALED 轮用 drand 是因为名单要在结果存在之前
  不可预知。这里池内 4,831 份**没有任何一份跑过**,挑盐挑不出好看的样本;
  换来的是第三方拿池和盐用四行脚本就能复算,不必信任我们的 PRNG 版本。
- 不分层抽取。strong / weak / none 三层用 `classify_broadcast_ocr` 事后分组报告
  (与 doctouch 08-18 同口径)。

复算命令(零 API):

    .venv/bin/python -c "
    import hashlib
    from invoiceloop.heldout import qual_pool, doc_ids_line_digest
    salt = 'invoiceloop-qual-narrow-v1'
    pool = qual_pool()
    ids = sorted(sorted(pool, key=lambda d: hashlib.sha256(
        f'{salt}|{d}'.encode()).hexdigest())[:200])
    print('pool', len(pool), doc_ids_line_digest(pool))
    print('ids ', len(ids), doc_ids_line_digest(ids))"

## 3. 提取(本轮唯一的 API 花费)

- 200 份 × 双模式(understand + agentic)= 400 次调用。
- 驱动 = `invoiceloop.heldout.cmd_extract`(串行、断点续跑、余额换 key、预算熔断)。
- 响应存 `runs/qual-narrow-2026-08-22/raw/`。
- 失败处理:该函数对网络异常退避重试 2 次、429 退避重试 2 次、401/402/403 换 key;
  仍失败则写进 `extract_summary.json` 的 `failures`。
  **`failures` 非空 = 本轮 `blocking_level: "blocking"`,结果文档头一句就写它,
  不跳过、不静默缩样本。**
- 不做并发。串行 400 次 ≈ 70–90 分钟,没必要为此造新机制。

## 4. 四臂与指标

| 臂 | harness | 闸 | 说明 |
|---|---|---|---|
| A | HAR-0001 | census | 结构性锚点,普查闸全挡 |
| B | HAR-0021 | census | 现役策略 |
| C | HAR-0021 投影 | payment_required_v1 | 同路由换闸,不重跑 |
| D | HAR-0023 | payment_required_v1 + `release_tier1_explicit: false` | 候选 |

- 运行:`scripts/doctouch_arms.py --out runs/qual-narrow-2026-08-22/doctouch
  --doc-list runs/qual-narrow-2026-08-22/doc_list.json`。**必须带 `--doc-list`** ——
  不带就会把盘上 660 份已曝光文档一起测进来,把 860 份的混合数字写成「未曝光」结果。
- 臂目录复用要核 `arm_identity.json`(策略 / schema / 名单摘要),不一致即阻断。
- 指标定义不变:`release_profile.document_touch_metrics`,主终点 = **文档零触达**。
- 三层分开报,ALL 只作合计。真静默(`silent_absent_true`)与口径争议照登。

## 5. 预注册预测(错了照登)

| # | 预测 | 依据 |
|---|---|---|
| P1 | A 臂零触达 = 0% | 普查闸全挡,结构性锚点 |
| P2 | D 臂零触达落在 **5–20%** | doctouch 实测 10.8% 为中心的诚实先验;上一轮 20–35% 的预测错了,不重复那个错法 |
| P3 | C ≥ D | `release_tier1_explicit: false` 的 QA 探针只增触达 |
| P4 | 真静默 ≤ 3 | 不高于 doctouch 各臂 |
| P5 | 三闸全自动占比 15–19% | doctouch 盘上 17.1%,合取机制应复现 |
| P6 | D 臂 `silent_wrong` ≤ B 臂 `silent_wrong` | 窄放行只减少**打开张数**,不该让错值更多地静默通过。这是本轮的安全终点,与 P4 的真静默分开报 |

零触达率按二项分布报 95% Wilson 区间(n=200,点估计 ±7 个百分点量级)。
**区间与点估计一起进对外句子** —— 200 份的一个百分数看起来比它实际的精度高。

## 6. 结果语义与顺序纪律

**升级为「产品能力」的闸有四条,全过才准写,P2 只是其中一条:**

1. 无阻断:`extract_summary.json` 的 `failures` 为空。
2. 样本完整:四臂各测满 200 份,`--doc-list` 无缺件。
3. 安全:P4(真静默 ≤ 3)与 P6(D 臂 `silent_wrong` ≤ B 臂)都成立。
4. 效果:P2 成立。

任何一条不过,数字照登,措辞退回 08-18 的限定句。**猜中预测和产品安全是两回事** ——
零触达率再好看,若 D 臂让更多错值静默通过,那就不是能力是隐患。

- 顺序:先跑臂、算完 200 份的路由指标,人再碰任何一份。ADK 行走集从这 200 份里抽,
  但必须在路由指标算完并提交之后 —— 行走不得污染路由数字。
- 两轮独立记账,数字不拼接。

## 7. 废臂条款

提取开始后改动以下任何一项 = 臂不干净,照实声明:抽样盐或语境、名单、
四臂的策略文件、`document_touch_metrics` 的定义、本协议正文。
