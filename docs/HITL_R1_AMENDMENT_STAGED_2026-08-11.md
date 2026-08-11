# HITL R1 增补件:阶段化 + AI 预读(2026-08-11,第一次裁决前冻结)

对 [`HITL_R1R2_PROTOCOL_2026-08-10.md`](HITL_R1R2_PROTOCOL_2026-08-10.md) 的修订。
合法性依据与 SEALED-4 增补件相同:**R1 至今零裁决**
(`runs/hitl-r1/runs/run-0001/adjudication_ledger.jsonl` 为 0 行),不存在任何
轮次结果;原协议「Round 1 第一次裁决之后改动任何一字 = 两轮作废」反向成立
—— 现在改,不毁任何东西。第一次裁决发生后本文件再动 = 轮次作废。

起因照登:复核者(stahl)指出单轮 ~495 槽 ≈ 4 小时无中间成果,设计反产品;
要求阶段化并要求 AI 分担预读。两条都采纳,形式如下。

## B1. R1 拆为 5 个阶段,每阶段 20 份单

- R1 的 100 份(名单 `docs/hitl_r1_doc_list.json` 不变)按种子
  `invoiceloop-hitl-r1-staged-2026-08-11` 顺序切成 5 段,段名单落
  `docs/hitl_r1_stages.json`,同 commit 冻结。
- 阶段 N 的 run = `runs/hitl-r1/runs/run-000<N+1>`(run-0001 的 100 份全量
  run 保留为参照基线,不进人队列)。
- 每阶段关账即出三条曲线的该阶段点(每槽人时、建议采纳率、反事实队列率),
  结果文档 5 个点全登,不挑。
- 预计人时每阶段 30–40 分钟;阶段间可以隔天,>1h 间隔照协议剔除。

## B2. AI 预读读者(tag `kimi`)

- 每阶段开台前,agent 对该阶段队列槽逐槽预读,产出
  `{doc, field, value | ABSTAIN}`,经 `suggest_inject` 以 tag `kimi`
  注入该阶段 run 的展示型建议层。
- **证据边界:只读 run 内工件(词级 OCR、页面渲染、span 注册表);
  永不读 DocILE annotations / truth / 任何打分器输出。** 违反 = 该阶段作废。
- agent 的预读是**建议**,与 vision 读者同地位:单一写者不变,账本只写
  stahl 的裁决;`suggestion_seen` 照协议记录人对建议的处置。
- 不确定就 ABSTAIN,不猜(读图五条纪律同一条)。
- agent 预读用时是机器成本,不进「人时」分子;但它使「人时/槽」下降的
  部分**不得**解释成「系统单独变快」—— 结果文档必须写成
  「AI 预读 + 人确认」组合臂的人时,与 run-0002 的纯人时(28s 中位,
  120 槽)对照时带这条限定。

## B3. 阶段间晋升

- 阶段关账 → `improve.mine` → 人审 → `improve.promote --approved-by stahl`
  → `improve.evaluate` 反事实 + 全套 pytest 绿 → 下一阶段 run 用晋升后的
  harness(frozen_harness,产品 active 状态不动)。
- 无候选过审 = 如实记「本阶段无晋升」,不为凑曲线降标准。
- R2(第二个 100 份,原协议)保留为可选项:5 阶段曲线若已回答
  「人时是否下降」,R2 是否执行由复核者看完阶段数据后定。

## B4. 不变的

语料规则(§1)、测量口径(§3)、轮间纪律(§4 的确定性-only、词表不删、
不碰 sealed)、照登义务(中途口径裁定写 rationale + 结果文档)。
