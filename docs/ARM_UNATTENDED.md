# Arm U — 无人值守裁决与批准(实验臂)

> 状态:**实验臂,非产品默认**。默认路径的批准仍只有具名人类能签
> (`approve.py` 的产品纪律不变);本臂只通过显式的
> `python3 -m invoiceloop unattended --run …` 进入,其批准署名与
> policy digest 在账本里与人类批准一眼可分。
>
> 来源:2026-08-27 独立评审查验(grokbot 实验)后的实现计划书
> (PLAN-UNATTENDED-AP-ARM,已并入本仓库)。设计动机见
> `HITL_ADK_OAUTH_20_2026-08-27.md`:单职员臂的三条真实失败
> (假 net、EIN 当发票号、队列空就签)证明"一个模型又判又批"不可接受。

## 这条臂是什么

```
PDF → DWS → Python 冻结/六门/矩阵            (既有,一字未动)
              │
              ▼
   Runner.run_async() — SequentialAgent "unattended_pipeline"
     ├─ clerk    LlmAgent  逐槽读整页图 → AdjudicationDraft(无 ID)
     ├─ binder   BaseAgent Python: append_adjudication,署名 agent:<model>
     ├─ critic   LlmAgent  逐槽复读同一组图 + clerk 草稿 → CriticDraft
     ├─ binder2  BaseAgent Python: 不一致 → supersedes 改判,
     │                    署名 agent:critic:<model>
     ├─ gate     BaseAgent Python: 重算交付投影 + unattended_policy 审计;
     │                    不 ready 的单据根本不送到 approver
     ├─ approver LlmAgent  逐 ready 单 → {release, rationale}(无 ID)
     └─ binder3  BaseAgent Python: 策略 ∧ approver 双 yes 才
                  append_approval(policy_digest=…)
```

三个模型角色是三个独立 ADK app(`invoiceloop_arm_u_clerk` 复用
adjudicator 的 `invoiceloop_arm_ta` 模式、`…_critic`、`…_approver`),
会话不混;binder/gate 是 BaseAgent 而非工具 —— 工具在模型裁量下调用,
BaseAgent 在 SequentialAgent 里**不可跳过**(与 improve 循环的
EvaluatorNode 同一论证)。

## 批准的署名与摘要

```text
approved_by   = unattended-policy-v3+agent:critic:<model>
policy_digest = sha256(POLICY_ID + R1..R10 规则文本)
```

改规则 = 新 policy id + 新 digest,旧批准不携带新语义(v1→v2:第一轮 live
验收后 R5 补格式等价、新增 R10;v2→v3:PR 审查后 R4 把任一角色草稿缺失
记为无共识、R3 禁止 critic 为自己改判出的缺席作证)。批准时间
由操作者经 `--decided-at` 注入(未来 Cloud Run Job 由触发器注入),
工件不读墙钟。人类批准不传 `policy_digest`(缺省 None),行为不变。

## 策略(unattended-policy-v2,R1–R10)

| 规则 | 拦截的失败(全部来自实测) |
|---|---|
| R1 挡账槽全有 tip(含 census 的 pending/pending_tier1) | 「队列空了就签」;第一轮验收还暴露了只走 review 槽会让 TIER1 印证槽永远 pending |
| R2 交付投影可批 | blocked/pending 单据到不了 approver |
| R3 缺席要有证据(改判 tip 只认页面探针) | 假缺席;以及一个角色为自己改判出的缺席自我作证 |
| R4 TIER1 两角色一致(草稿缺失=无共识) | 单模型自检自己的判断;单角色读过的 TIER1 槽放行 |
| R5 修正值印在页上(含格式等价) | 发明的数字;以及 ISO 日期/无符号金额被误判为不在页上(§4.4 同族) |
| R6 EIN≠发票号 | `58-0391492` 是税号 |
| R7 条款≠日期 | `Due on Receipt` |
| R8 无标签字段不准 correct | 页面没有 Net 列却填了 net |
| R9 approver 还要独立 yes | 策略通过 ≠ 获得批准 |
| R10 页上印着 EIN 而 seller_vat_id 判缺席 | 假缺席 —— 第一轮 live 验收里 clerk 与 critic **同漏** Taxpayer ID,只有确定性规则能补 |

策略是纯 Python(`invoiceloop/unattended_policy.py`,当前 **v3**),夹具测试
`tests/test_unattended_policy.py` 每条失败一个反例,零 API。

## 权限边界(实现不许做的事)

1. 不改 `append_adjudication` / `append_approval` 的 ID 语义 —— 模型
   仍只出无 ID 草稿,Python 仍是唯一写者;
2. 运行时不读 DocILE 标注 / 真值 / `eval_normalise` 对照;
3. 公开 Cloud Run 工作台保持只读 —— 公网可写裁决账本 = 伪造证词;
4. clerk 与 critic 不共享调用或 session;approver 看不到演示指令;
5. 凭据不进镜像、不进 `raw/`、不进任何工件
   (`agents/vertex_oauth.py` 的 token 只驻内存)。

## 凭据通路(演示/验收)

`generativelanguage.googleapis.com` 在本网络不可达,且本机无 ADC 文件。
`--gcloud-oauth-project <id>` 走内存态 gcloud 短时 OAuth + Vertex AI
`global` 端点(token 不落盘;元数据写 `oauth_run_metadata.json`,
只记形状不记 token)。重放照旧:`INVOICELOOP_REPLAY=1` 零 API,
录音在 `workspace/agent_calls/`(clerk `adj_*`、critic `crit_*`、
approver `appr_*` 前缀)。

## 与两场比赛的对齐

- **ATA**:视频可拍 Arm U 把单据送到 export(Utility 故事),但
  权威边界(ADK 不写账本、gate 不可跳、批准带 digest)必须同时出镜
  —— 这是与「一个 Agent 自己过账」的差异化。
- **Nutrient**:Arm U **不进** Nutrient 叙事;那边的 demo 仍是
  Arm A(人签、审计包)。两臂同仓,README 段落分开,避免评委以为
  默认无人过账。

## P0 验收记录(2026-08-27,三轮 live,demo 三张)

证据:[`evidence/arm-u-2026-08-27/acceptance/`](evidence/arm-u-2026-08-27/acceptance/)(第三轮工件 + MANIFEST)。
模型 `gemini-3.7-flash`(Vertex AI global,内存态 gcloud OAuth)。

| 轮 | 结果 | 学到什么 |
|---|---|---|
| 1(v1 策略) | 0 批准。critic 当场抓住 clerk 假 net(Powell);ISO 日期/裸金额被 R5 误判;两角色同漏 Taxpayer ID;TIER1 印证槽不在队列 | → v2:R5 格式等价、R10 EIN 反缺席、队列扩到挡账槽 |
| 2(v2) | 中途崩:无冻结声明的槽上 clerk 选 accept,单槽炸整臂;429 配额 | → binder 逐槽隔离记 binding_failures;clerk 补充 claim 语义事实;退避 3s/6s/9s |
| 3(v2,验收轮) | **26/26 落账,0 失败;三张全部到达可批状态(2 ready + 1 ready_with_caveats);策略拦下全部三张,0 批准** | 见下 |

第三轮每张单据的拦截原因(照 `unattended_run.json` 原文,不归并):

- **UMI**(1 条):R8 —— clerk 把日期修正为日历日(对),但页面没印
  "Due Date" 标签,缺席探针说 label-absent。R8 为抓假 net 而设,
  对"无标签但印着日期"的单据偏严 —— **v3 的已知候选改动,未改**:
  放宽它是对真实风险的取舍,不当夜拍板。
- **Powell**(1 条):R4 —— clerk 与 critic 在 total_net(gold 无此槽)
  分歧。双角色共识门**按设计工作**:有分歧就不放,这是特性不是缺陷。
- **Cumulus**(7 条):OCR 受阻单。5 个被 clerk 修正的槽 R5 全挂
  (独立 OCR 无词,机检判不了),另有 total_gross/total_net 两条 R4
  (critic 改判 confirm_absent)。终态是
  `ready_for_approval_with_caveats`(independent_ocr),策略不放。
  宪章四的正确表现:机检查不了的单一律不放。

**三轮零不安全放行;每一个"没批"都有具名规则与真实原因。** 对照计划书
§6 的验收:UMI 差一条 R8;Powell 走了合法终态②(分歧即阻断);
Cumulus 属诚实失败。P0 的结论是:**内核吃得下 agent 闭环,而确定性
策略在 demo 语料上一条不放 —— 这个"不放"每一条都站得住。**

## 尚未做(按计划书顺序,本地绿了才碰云)

- P2:Cloud Run Job(IAM 私有)+ Secret Manager + GCS 工件上传;
  公开 `.run.app` 继续只读,只当部署证明。
- approver 只看摘要不看像素的取舍是否站得住,等首轮真实运行数据。
