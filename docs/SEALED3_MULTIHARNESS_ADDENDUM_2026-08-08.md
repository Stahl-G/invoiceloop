# SEALED-3 多 harness 开箱附录（2026-08-08，结果前冻结）

本附录不改 `docs/SEALED3_PROTOCOL.md` 的主终点、通过线或污染后果。它只在
任何 SEALED-3 run / 结果尚未产生时，把一次开箱扩为**同一冻结证据上的配对
多臂评测**。用户已明确授权先进行无需完整人类臂的部分；agent-vs-human
实验里的人类裁决准确率以后再完成，不是本次开箱的输入或通过条件。

## 1. 为什么不是“看一轮，再让 ADK 改一轮”

SEALED-3 只能打开一次。若第 1 轮结果进入 ADK prompt，再据此生成第 2 轮
policy，第 2 轮已经把 SEALED-3 当训练/开发反馈，立即触发原协议 §2 的作废
条件。因此本实验只有一个合法形态：

1. 先冻结所有臂、摘要、比较方向和 scorer；
2. 一个批处理进程让所有臂分别从同一份 raw/OCR/PDF 重跑完整确定性流水线；
3. `batch_complete.json` 出现前不读取任何中间臂结果；
4. 批次完整后才统一评分；结果无论方向都照登，不再用本批改规则。

HAR-0006 / HAR-0007 是 **SEALED-3 开箱前已经由真实 Google ADK Runner 产生、
但未晋升**的候选。本次只测它们冻结的 policy，不调用 ADK，也不让 agent 看
SEALED-3。这样能回答“ADK 候选若直接 promotion 会怎样”，但不会把 agent
变成有权写 active state 的主体。

HAR-0005 不进本实验：它改变 extraction schema，验证它必须重新调用 DWS。
拿 HAR-0004 已抽好的 raw 重路由，只能测出“同 policy 的同结果”，不能测 schema
变化；把这种伪实验叫 schema arm 会违反不说工件证明不了的话。

## 2. 冻结批次与单一变量

权威机器可读计划：`docs/sealed3_multiharness_plan.json`，sha256
`9b275801349e3f684b29748a1db50882c6dcaad8ca25df88c6923bcecbf9702e`。
它内嵌以下约束：

- 名单：`docs/sealed3_doc_list.json`，100 份，sha256
  `bad85f534fbf7fa5d98bcca9529087b3bd438988c27df56e72fe96c5d8f70439`；
- 所有臂使用同一 extraction schema，canonical digest
  `19e7516de0c5f98be6aa5448074ef9c0c35782ba6abad300d0372e0eb9f6452e`；
- `include_vision=false`、`render_crops=false`，不引入未冻结读图输入；
- 20 个流水线、门禁、归一化、scorer、运行器文件逐个钉 sha256；
- 每份 routing policy 复制进 Git 内的 evidence 目录并同时钉文件 sha256 与
  canonical policy digest；开箱不读取 `runs/adk-real-*` 的可变候选文件。

`invoiceloop.sealed_batch` 只在一次 `pipeline.run` 的上下文里临时提供冻结
harness；`finally` 必须恢复真实 `harness.load_active`。它不写 promotion、
不改 `active_harness.json`，所以不是第二个产品权威写者。

`absent_expected` 会在 `gates.run_gates` 内把 `extraction_present=fail` 改成
`expected_absent`。因此这里**不能**只拿一份既有 matrix 换 routing；每个臂
都必须从相同存盘证据独立重跑 artifact → freeze → gates → matrix → deliver。

## 3. 七个臂（六个 harness + 一个精确重复）

| arm | harness | 角色 | 预先写下的比较 |
|---|---|---|---|
| B0 | HAR-0001 | 保守基线 | 人工负载上界；无 auto-absent |
| B1 | HAR-0002 | TIER1 出口规则消融 | 对 B0 测取消无冲突 TIER1 强制确认 |
| B2 | HAR-0003 | seller VAT 缺席消融 | 对 B1 测 seller_vat_id cohort |
| P | HAR-0004 | **原协议主臂 / 唯一资格臂** | 对 B2 测 total_vat cohort；对 B0 跑 P1/P2 |
| P-repeat | HAR-0004 | 精确重复性控制 | 全部 run 工件应逐字节一致 |
| A1 | HAR-0006 | ADK near-placebo | 重复添加已有 total_vat cohort；注意 harness_id 会重排 QA 哈希抽样，所以不是纯 placebo |
| A2 | HAR-0007 | ADK due_date 候选 | 对 P 测 due_date 缺席减负及静默缺席风险 |

所有次臂只作配对描述，**不得**取得 SEALED-3 资格，也不得因方向好看而晋升。
HAR-0004 仍是原协议“开箱时 active harness”的主臂。

## 4. 冻结终点与比较

### 4.1 原协议主终点

主臂 P 仍按原协议 H1–H7：H1–H6 直接调用未修改的
`scripts/heldout_metrics.py`；H7 = 主臂 run 完成、audit bundle 离线 verify
通过。原区间和“错误照登”规则不变。

### 4.2 工作量（全部 1,000 槽，无需人类完成裁决）

- `human_queue`：`route ∉ {auto_accept, auto_absent}`；
- `requires_adjudication`：历史兼容口径，含 `auto_absent`；
- `decision_load_for_release`：`requires_adjudication ∪ TIER1`；
- document touch：至少一个槽在 `human_queue` 的文档数 / 100；
- machine_decided / machine_absent 分开报告。

这些是确定性路由工作量，不是“人工裁决准确率”。后者仍为
**NOT MEASURED**，直到完整人类臂完成。

### 4.3 安全性（DocILE truth 只作共同裁判）

每臂使用同一个 `safety_metrics.score_routes`，拆报：

- `silent_absent / absent_hits`；
- `silent_wrong / value_hits`；
- H1–H6 的记分槽、偏差和可判分母。

DocILE 标注不构成第三个实验臂，也不替代人类体验实验；它只用同一规则给
所有 policy 判分。

### 4.4 预注册配对方向

- lineage：B1−B0、B2−B1、P−B2；
- 资格门：P−B0；P1 要求 silent_absent 与 silent_wrong 均不升，P2 要求
  human_queue 不升；
- 重复性：P-repeat−P 必须全零且 run tree digest 相同；
- ADK 控制：A1−P、A2−P。

多次比较全部是描述性 effect size（槽数、百分点、静默错计数），不做显著性
筛选，也不从中挑“最好的一臂”写主张。

## 5. 开箱事务与失败语义

开箱命令必须在本附录和运行器均 commit 后执行，并把该 commit 的完整 SHA
作为 `--expected-head`。运行器还会拒绝任何已跟踪未提交改动；未跟踪的用户
文件不进入 code revision。

```bash
.venv/bin/python scripts/sealed3_multiharness.py \
  --expected-head <本附录提交的完整 SHA>
```

批目录必须从不存在。进程先写 `batch_started.json`；每臂写独立不可变 run；
只有七臂全成、输入指纹一致、上游工件一致、精确重复逐字节一致后才写
`batch_complete.json`。任一步失败会留下 `batch_failed.json` 和部分臂，不删、
不原地续写；那是可 grep 的负面工件。

批次完整后，先给主臂打 audit bundle，再一次运行冻结 scorer。scorer 会重新
核验开箱时登记的每个文件哈希；后加的 bundle 可以存在，但既有 run 字节不可
变化。

## 6. 结果后的纪律

- 本次开箱后，SEALED-3 永久不可再用于新 policy、prompt、doctype 或门禁的
  未见评测；任何受结果启发的改动只能进下一版本，并等待 SEALED-4。
- 若主臂未过 H1、P1、P2 或 H7，资格失败，数字照登；不得换基线、删臂或再跑
  一次种子。
- A1/A2 无论好坏都不自动晋升。agent 只有建议权，promotion 仍需确定性验证、
  人类签名和新的未见证据。
- 本次不补写 agent-vs-human 的“人工准确率”；H2 的 200 槽人类臂以后独立
  完成和开封，不与 SEALED-3 结果混成一个分母。
