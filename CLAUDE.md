# CLAUDE.md — InvoiceLoop 开发指引

## 先读

1. `ARCHITECTURE.md` —— 奠基文档,自包含。里面每个数字都可从校准仓库重算
2. `~/Developer/dws-derisk/REPORT.md` §9c/§9d —— 六轮实验结论(为什么不承诺"抽得准")
3. `~/Developer/dws-derisk/THRESHOLDS.md` §6f/§6g —— 预注册判据与结果对照

**不需要**读六轮的全过程。架构文档已把结论与依据提炼进去。

## 这个项目的论点

**抽取的正确性不可信,支持关系可验证。** 交付物是**支持矩阵**,不是判决。
任何时候想写"提高了准确率""让 DWS 可信",停下 —— 违反 `ARCHITECTURE.md` §1 宪章六。

## 硬约束(违反就是错的)

- **单一写者**:模型只能写 `field_drafts.json`(无 ID);Python 分配 ID 并冻结账本
- **负面发现即阻断**:门禁跑不了 = `blocking_level: "blocking"`,不是跳过
- **口径冲突不进错误率**:纸面 Gross vs EN 16931 gross 是 `applicability` 维度的争议,
  按宪章五保持显式、进人工裁决
- **不说工件证明不了的话**:校准数字必须带 §8 那三条限定

## 复用哪些代码

校准仓库 `~/Developer/dws-derisk/` 里六个门禁全部已实现并测过,直接搬:

| 要的东西 | 在哪 |
|---|---|
| 规范化规则(预注册,六轮冻结) | `score.py::normalise` |
| C1-C7 确定性检查 | `routers.py::consistency_review` |
| 独立 OCR 引用校验 | `round3.py::citation_holds` |
| 双模式分歧 | `paired.py::agree` |
| bbox → 相对坐标 → 裁剪 | `vision_eval.py::_rects` / `crop_field` |
| 整页渲染 | `vision_eval6.py::cmd_render` |
| DWS 客户端 | `extract.py` |

**注意** `round3.py` 在 dws-derisk 里是从 git 历史恢复的(`git show ddf9205:round3.py`)。

### 两条搬运陷阱(M2 已踩过,均已验证)

- **`score.normalise` 做不了 token 匹配。** 它是 kind-dependent 的,
  AMOUNT 分支把值塌成单值(`'$8,500.00'` → `'8500.00'`),CODE 分支整串剥
  (→ `'850000'`),两者都产不出 token 序列。要 token 就自己按
  `[a-z0-9]+` 切,**两侧用同一个函数**。
- **`citation_holds` 不是 token 匹配。** 它是 `want in have` 的子串包含。
  "去掉区域过滤即可"复现不了绑定判定 —— 实测 11/454 行判定不符。

复用前先读实现,不要照搬交接说明里的一句话描述(包括我写的)。

## 数据

- 校准语料:`~/Developer/dws-derisk/data/docile/`(5,680 份 PDF + 标注 + 词级 OCR)
- 已存盘 DWS 响应:`~/Developer/dws-derisk/raw/`(320 次调用,零失败)
- **打分只读存盘文件,不碰 API** —— 比较规则可以改了重跑而无需再计费

## 里程碑

见 `ARCHITECTURE.md` §11。M0–M1 主要是搬代码,M2(冻结事务)与 M3(支持矩阵 + panel)
是真正新写的。**建议从 M2 开始** —— 它是唯一有实测证据能挡住真实故障的部分。

## 提交习惯

每条消息一行,动词开头,说清做了什么而不是"更新了文件"。
参考 dws-derisk 的 git log。
