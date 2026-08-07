# 阶段 D — 主体方向原型(2026-08-07)

## 结论

**KILL。** 预注册主指标在 SEALED-2 100 份上准确率 **51.8%**(29/56),
远低于 80% 生死线。第 3 项(主体方向机检)**作废** —— 不接线
`gates` / `routing` / `improve`;卖方认错继续只靠人工队列。

复算:
```bash
INVOICELOOP_CORPUS=runs/sealed2-workspace \
  python3 scripts/subject_direction_proto.py
```

引擎:`subject-direction-v1` · digest 前缀 `edc49c71a2874d10`
(完整值由 `subject_direction.digest()` 给出)。

## 预注册规则(不许为好看回调)

来自 `docs/DOCTYPE_PLAN_2026-08-07.md` Q3:

| 侧 | 标签 |
|---|---|
| 卖方 | `Remit to` / `Pay to` / `Station` |
| 买方 | `Bill to` / `Advertiser` / `Agency` |

对 `runs/sealed2` 里抽出的 `seller_name` span(同页),取词级 OCR 上
欧氏距离最近的标签侧:

- 近卖方侧 → 预测抽取与 DocILE `vendor_name` 一致
- 近买方侧 → 预测不一致

准确率 = 预测与 `eval_normalise(PARTY)` 对错一致的比例。
可评分前提:有 seller span、有真值与抽取、同页至少一枚标签。

## 数字

| 项 | 值 |
|---|---|
| 文档 | 100 |
| 页上有任一标签 | 68 |
| 主指标可评分 | 56 |
| 主指标正确 | 29 |
| **主指标准确率** | **51.8%** |
| 生死线 | 80% |
| **裁决** | **FAIL** |

跳过:无 seller span 4 · 无真值或抽取 14 · 同页无标签 26 · OCR 不可用 0。

### 旁证变体(同一词表,不改极性;全部 FAIL)

| 变体 | n | 准确率 |
|---|---|---|
| 最近标签 + max_dist≤0.20 | 22 | 50.0% |
| 同页双侧都在 → 更近侧 | 26 | 46.2% |
| 真值 vendor bbox → 最近是否卖方侧 | 59 | 47.5% |

变体不是放行旁路:用来排除「只是距离阈值 / 缺少对照标签」的假象。
全部贴着掷硬币,没有一条接近 80%。

## 为什么这不意外

计划已警告 PARTY 引用原型 137/151 失败。本原型换了几何近邻,
失败模式同类:广告单据上 Agency / Station / Advertiser / Remit to
同时出现时,抽出的卖方名并不稳定落在「该近」的那一侧;真值 bbox
本身也只有约一半最近卖方侧标签 —— 标签几何**定位不了**卖方。

已知静默错里的代理↔电台倒置(如 `503f49c0` Regional Reps→WARU-AM,
`ce6ab66e` Shorr Johnson Magnus→WPGH)不会被这条规则稳定抓住。

## 产品含义

1. **不做** `subject_direction` 门禁 / finding / 自动放宽。
2. `seller_name` / `buyer_name` 错位继续进人工;交付物不宣称方向可验证。
3. 阶段 E(类型级适用性矩阵)与主体方向**解耦**,可按计划推进;
   不得把 `doc_class` 当成主体方向的替代品。

## 工件

| 路径 | 角色 |
|---|---|
| `invoiceloop/subject_direction.py` | 冻结词表 + 几何(标明不进产品) |
| `scripts/subject_direction_proto.py` | SEALED-2 零 API 复算 |
| `tests/test_subject_direction.py` | 几何/极性单元测试 |
