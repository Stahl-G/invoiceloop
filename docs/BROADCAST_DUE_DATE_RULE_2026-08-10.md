# 广播发票 due date 规则

这次修正把两个概念分开：

- `due_date`：DWS 只抽页面直接印出的绝对日期。
- `calculated_due_date`：系统根据独立 OCR 中的明确输入和付款条款计算出的派生结果。

例如页面明确写 `Invoice Date: 2026-07-01` 和 `Net 30`，系统记录：

```text
calculated_due_date = 2026-07-01 + 30 calendar days = 2026-07-31
```

派生工件同时保存公式、输入字段、付款条款原文和 OCR 词位置。它不会覆盖 raw `due_date`，也不会把派生结果当作页面上的原文证据。

如果页面写的是 `30 days after receipt` 或 `Due on Receipt`，但没有明确的收件日期，结果是 `not_computable`，不会把 invoice date 偷换成 receipt date。节假日和工作日规则也不在当前版本内。

## 本次 pilot

30 份双模式候选抽取消耗 1,599 credits。候选 schema 让 `silent_wrong` 从 23 降到 17，但人工 review slots 从 191 增到 201，release decision load 从 79.67% 增到 81.00%，因此候选不晋升。

这说明 schema 文字可以减少一部分错误值，但目前不能证明它减少人工工作量；`calculated_due_date` 的页面规则层独立保留，等待更多明确条款样本和后续测量。
