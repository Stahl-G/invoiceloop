# L1 自适应实测(2026-08-06)

负面结果登记:动态降档(understand 先跑、仅风险文档再 agentic)**在 SEALED-1
的 88 份未人工文档上不划算**,不得升为默认路径。

复算:`INVOICELOOP_CORPUS=runs/sealed1-workspace python3 scripts/adaptive_probe.py`
(零 API;`truth` / `eval_norm` 与 `safety_metrics` 同函数)。

## 数字

| 量 | 值 |
|---|---|
| 未人工文档 | 88 |
| `diagnose_risk` 判 clean | **4** |
| 判 escalated | 84 |
| 双模式 DWS 调用 | 176 |
| adaptive 调用 | 172 |
| 节省 | **4 次(2.3%)** |
| clean 文档上失去的 `cross_mode=fail` 槽 | 7 |
| 其中有真值可判 | 4 |
| 这 4 个槽上 understand 对真值 | **0/4(全错)** |

全量 `cross_mode=fail` 且有真值的 142 槽拆分:

| 谁对 | 槽数 | 占比 |
|---|---|---|
| 仅 understand 对 | 29 | 20% |
| 仅 agentic 对 | 66 | 46% |
| 两者都错 | 47 | 33% |

## 结论

1. 节省可忽略(2.3%),不是产品级成本杠杆。
2. 被跳过 agentic 的「干净」文档上,失去的双模式分歧信号里**有真值的全部是
   understand 错** —— 省成本直接换静默错。
3. 双模式分歧本身是高价值信号(agentic 在分歧子集上明显更准),不该被省掉,
   也不宜用第三读者多数投票自动放行(两者都错仍占 1/3)。

## 工程护栏

- `ingest --adaptive` 保持 **opt-in、不推荐**;密封/留出路径遇
  `adaptive.json` **硬拒**(`heldout.cmd_extract`)。
- `diagnose_risk` 必须忽略 `FIELD_KINDS` 外键(真实 DWS 几乎必回
  `invoice_type` 等;漏守卫 → KeyError 必崩,见 `tests/test_adaptive.py`)。

## 不做

不把 adaptive 设为默认;不在 sealed/heldout/demo 上开 `--adaptive`;
不把「省了几次调用」写成产品卖点。
