# Loop 泛化实测:一批文档的经验用于另一批(2026-08-06,供外部裁决)

**问题**:改进循环在一批文档上学到的东西,能不能用到**另一批从未人工
接触**的文档上 —— 而不是只对重复证据有效(carry 只解决重复证据)。

**方法(零 API,可重算)**:SEALED-1 的 100 份封箱文档中,12 份经过完整
人工复核(`runs/hitl-sealed`,123 条裁决)并产出两个 absent_expected
cohort(seller_vat_id、total_vat,均由 mine 从裁决事件独立发现,人工
签署晋升 HAR-0003/HAR-0004)。把这版策略回放到**其余 88 份从未人工
复核**的文档上:从权威工件(field_ledger + gate_report + raw 响应)
重建槽位事实(单一事实源 derive_document_records),按策略重放路由,
工作量与安全性分开报。安全性用 DocILE 真值评测。

**角色声明**:SEALED-1 已按协议完成 final held-out 职责并降级为
演化/回归集 —— 用它做 cohort 开发与泛化分析是它的合法角色;
本文件是演化集分析,不是新一轮封箱评测。

## 数字(88 份未人工文档 × 10 字段 = 880 槽)

| 策略 | 复核负载 | 文档触达 | auto_absent 静默缺席错 | auto_accept 静默错值 |
|---|---|---|---|---|
| HAR-0001(保守基线) | 63.7% | 88/88 | — | 49/272 (18.0%) |
| HAR-0002(TIER1 策略放行) | 64.4% | 88/88 | — | 48/266 (18.0%) |
| **HAR-0004**(两个缺席 cohort) | **55.1%** | **87/88** | 3/85 (**3.5%**) | 49/266 (18.4%) |

(HAR-0002 复核负载略高于 HAR-0001:policy_accepted TIER1 的 5% QA
抽检回队,是设计代价,不是退化。)

## 读法

1. **经验迁移成立且有真值背书**:两个 cohort 都是字段级语义(美国发票
   无 VAT 字段/无 VAT 金额行),不引用任何具体文档 —— 套到 88 份陌生
   文档上复核负载 −9.3pp。这不是重复证据的红利(carry 的领域),
   是跨文档的泛化。
2. **「100% 文档触达」首次出现反例**:87/88 —— 一份文档的 10 个槽全部
   政策接管且真值无恙。此前所有口径下文档触达都是 100%。
3. **代价是实测的,不是猜的**:85 个 auto_absent 中 3 个真值其实有
   (3.5%,与全 100 份独立估计的 3.4% 一致)—— 缺席政策的静默漏标率。
   它由 QA 20% 抽检持续观测;severity 注记:3 例含一个真欧盟 VAT 号
   (DWS 漏抽),两个 EIN 格式号(数据集口径争议的另一面)。
4. **auto_accept 静默错值 18% 各策略持平**:这是 policy_accept 固定操作
   点的既有风险(此前基线表里的 17.91% 同量级),与 cohort 无关,
   由 5% QA 探针观测。cohort 没有让它变好或变坏。

## 不主张

- 不主张泛化到 DocILE 之外(单一语料、单一供应商、单一时间点,
  ARCHITECTURE §8 限定同屏有效);
- 不主张 55.1% 是终点:复核负载的剩余主体是门禁失败与真缺值,
  需要新的 cohort 类型(不是缺席类)才能继续;
- 不主张缺席政策无代价:3.5% 静默漏标是实际价格,晋升记录
  (PROM-0003)的理由里已写入;
- 不主张 carry 与本文是一回事:carry 解决重复证据,本文解决跨文档泛化。

## 复算

```bash
# 88 份名单 = sealed1 名单 − runs/hitl-sealed/input/pdfs/ 的 12 份
# 方法与数字(本文全部表格的来源,零 API):
INVOICELOOP_CORPUS=runs/sealed1-workspace python3 <本分析脚本>
# 输入:runs/sealed1/{gate_report,field_ledger}.json +
#       runs/sealed1-workspace/raw/*.understand.json +
#       runs/hitl-sealed/harnesses/HAR-0004/routing_policy.json +
#       DocILE 标注(heldout_metrics.truth 同一口径)
```
