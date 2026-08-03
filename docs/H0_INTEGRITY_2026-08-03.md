# H0 完整性地基(2026-08-03)

外部代码复核(对 `ff2e26c`)发现四个会瓦解核心承诺的问题,本轮按复核者
收窄后的 14 条不变量修复,**不加门禁、不加模型、不复制 BriefLoop 控制面**。

复核者原话定性的问题:冻结没被真正强制(重跑静默覆盖 → 裁决错绑)、
audit bundle 不能独立复核上游证据、human loop 不闭环(裁决不回投影)、
没有安装入口(clean clone 直接 3 个测试挂)。

## 五条提交

| 提交 | 做了什么 |
|---|---|
| 909fb6f | 安装层:pyproject(运行时仅 requests)、`doctor` 自检、clean-clone 安全的对拍测试导入、赞助商中立的 README 措辞 |
| 0ef48fe | 不可变 run:非空目录永拒(无 `--force`);workspace 逐代 `runs/run-NNNN` + `current.json` 指针;同输入指纹重放;`input_manifest.json` + `review_snapshot.json` 落盘 |
| 1d0798c | 裁决 v2:绑定完整复核快照(不只是账本);`claim_id↔doc_id↔field` 三元精确一致;缺值槽用稳定 `target_id`;决策语义冻结(correct 必带值,余者禁带);二次决定必须显式 supersede;panel 成为可重建投影,渲染失败不回滚裁决 |
| e943412 | 自包含 bundle(方案 A):全量上游证据(PDF/OCR/raw×2)+ 抽取 schema + 范围元数据;`verify` 命令三层离线校验(成员哈希 → 快照成分重算 → 裁决绑定) |
| 1133483 | 自查补洞:读图作答进输入指纹(否则重放会返回旧 run);panel 叠加层 label 转义 |

## 关键设计决定(为什么这样做)

- **没有 `--force`,也不要求删除历史。** 销毁裁决账本不是显式 Human decision。
  想重跑就开新代,旧代永远原样保留 —— 阻断不是障碍,是产品语义。
- **裁决绑定 `review_snapshot_id`,不只是账本哈希。** 快照 = 输入清单 + 工件注册表
  + 证据片段注册表 + 冻结账本 + 门禁报告 五个成分。只绑账本的话,同一账本配上
  被替换的证据检测不到。
- **current state 由 supersession 链投影,不是"最后一行赢"。** v1 旧条目
  (2026-08-02 验收轮的两条真人裁决)给合成 `legacy-<sha8>` id 并按 seq 隐式
  串链 —— 那是 v1 当时的语义,如实标注,不改写字节。链断了(只可能是手编账本)
  显式标冲突并阻断新裁决,不替人猜。
- **bundle 要么全量自包含,要么不打。** "整批派生物 + 只收被裁决文档的上游证据"
  是假自包含:收包人看到结论却验不了来源。缺任一上游证据即阻断。
- **panel 是投影,裁决是权威。** adjudicate 先落盘 fsync 再重渲;渲染失败返回
  `decision_recorded=true, panel_refreshed=false`,`render --run` 随时可重建。

## 测试对照(复核者要求的八类)

| 要求 | 测试 |
|---|---|
| 非空 run 不被覆盖,旧字节完全不变 | `test_run_immutability.py::test_nonempty_out_dir_is_refused_and_untouched` |
| 新输入产生新 run | `test_fingerprint_changes_with_input` + `test_allocate_replay_and_new_run` |
| decision 的 snapshot/claim/doc/field 错配全拒 | `test_adjudicate.py::TestValidation` 七条 |
| supersession 投影确定 | `test_review.py::test_tip_follows_supersession_chain_not_row_order`(乱序输入同投影) |
| panel 刷新失败不丢 decision | `test_render_failure_does_not_rollback_decision` |
| bundle 缺任一上游证据即阻断 | `test_missing_upstream_evidence_blocks` |
| bundle 任一字节被改,verify 失败 | `TestVerify` 四条(含"改了工件又同步改 MANIFEST"被快照重算抓住) |
| clean clone 无 dws-derisk,产品路径仍能跑 | `scripts/fresh_venv_check.sh`(clone → venv → install → doctor → E2E → pytest) |

## 边界(这轮不做什么)

- 不做 Web 服务 —— H1(Judge-facing Review Workbench)才是它,见复核者第六节。
- 不做 blind usability 复测 —— 仍欠,录视频前做。
- 不动 freeze/gates/matrix/fields 的语义 —— 回归由对拍与 byte-compare 套件看守。
