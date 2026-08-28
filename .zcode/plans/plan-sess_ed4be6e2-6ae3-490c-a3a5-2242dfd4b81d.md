# 评委路径英文化 + P1 两修 + 全量 docs 翻译

两个 PR:代码 PR(P0/P1/DWS 可见性)先行,docs 翻译 PR 随后分批推进。

## PR 1 — 代码:产品表面英文 + P1 两修 + DWS 可见性(分支 pr/judge-surface-en)

### 1. P1-1:unattended 退出码(先修,十行内)
- `invoiceloop/agents/unattended.py` 加纯函数 `failed(report) -> bool`:True 当且仅当 `drive_fatal` / `gate_error` / `deliverable_error` / `clerk_failures` / `clerk_binding_failures` / `critic_failures` / `critic_binding_failures` / `approver_failures` 任一非空。**`approval_refusals` 不算失败**(策略拒绝是正常业务结果)。
- `__main__.py` unattended 分支打印完 summary 后:`raise SystemExit(1 if failed(report) else 0)`(仿 verify 的先例 `__main__.py:351`)。
- 测试:`tests/test_unattended_pipeline.py` 加谓词单测(refusals≠失败、任一 failures=失败)。

### 2. P1-2:Job 上传根改为工作区
- `scripts/run_unattended_job.sh` 上传块:`rglob` 根从 RUN_DIR 改为 `${WS}`;保留 `pages/`、`crops/` 排除(可重建),新增排除 `*.lock` 与 `__pycache__`。agent_calls(≈16M 录音)、input/pdfs、raw、ocr(合计 <1M)全部进桶,`artifact_registry.json` 不再指向断链。

### 3. P0:产品表面英文化(评委默认路径零中文)
默认语言已是 en(`workbench.py:3272` 缺省 `"en"`),做的是补洞,不是重建:

**a) workbench.py(~50 条硬编码中文)**
- POST 错误路径全部搬进 `_T` 双语表(en+zh 各加键):Host/CSRF 拒绝(:3311-3329)、/decide 校验(:3486-3522)、上传校验(:3600-3605 等)、improve POST 错误(:3707-3916)、review-scope 错误(:1278-1289);`、` 连接符按语言切 `", "`;CLI 启动 banner(:4022-4028)与 advisory-unavailable stderr 文案(:545-550)改英文。
- 语言切换标签保持现状(目标语言名用目标语言写是标准做法)。

**b) __main__.py(~86 条)**
- 77 条 argparse help、3 条 parser.error、printed JSON 里的 note(hint/note 共 5 处)全部英译;`错误:{exc}` 包装器 → `error: {exc}`。代码注释不动(范围控制)。

**c) 深层 raise(评委经 workbench/CLI 可见,29 条)**
- `pipeline.py` RunExistsError×2 + domain_scope、`ocr.py` OcrUnavailable×2、`adjudicate.py` 24 条 ValueError 全部英译(workbench `_decide_error` 目前把原文透传给表单——译后评委看到英文)。
- 同步更新断言这些中文消息的测试:test_adjudicate.py(16 处)、test_freeze/test_e2e 等的 match= 模式。

**d) demo.py / doctor.py / panel.py / scripts**
- demo 的 SystemExit+两条 note、doctor 全部 16 条、panel.py 2 条、5 个脚本的 15 条 echo/fatal 英译。

**e) 测试面**
- test_workbench.py:错误路径断言改英文(如 :254 断言 /decide 400 含 CJK → 改断言英文消息);zh 表驱动的既有断言保持(双语表仍在)。预计触碰 ~6-8 个测试文件。

### 4. demo 加 DWS 可见输出(API World 硬规则)
- demo 输出加一段 "DWS extraction layer"(英文):从 `samples/raw/` 存盘响应里取一个具名字段,展示 value + bbox + page grounding 原文,并指明它在链路中的位置(抽取层→本仓库的证据/复核/批准层)。零 API、零新增依赖。

### 验证
- 全套件 pytest 绿;评委三命令冒烟(`demo`/`workbench`/`pytest`)+ `--help`,默认路径屏幕零 CJK(用 CJK 正则扫输出断言)。
- 开 PR → subagent 审查(同上轮流程)→ 修复 → 合并。

## PR 2 — docs:全部 77 份中文文档英文化(分支 pr/docs-en,分批提交)

- **批次 1(评委引用的 4 份,原地译)**:CLOUD_RUN.md(剩 14 行)、ARM_UNATTENDED.md、QUALIFICATION_NARROW_V2_RESULTS_2026-08-23.md、QUALIFICATION_NARROW_CONTAMINATION_2026-08-23.md。
- **批次 2(哈希钉死的协议,英文伴生文件)**:QUALIFICATION_NARROW_V2_PROTOCOL_2026-08-23.md 等被 run identity / decision.json 钉 sha 的文件**原件一字不动**,新增 `<name>.en.md`,文件头声明 `English translation of <file>, source sha256: <digest>`。先 grep 全部 run_identity/decision/manifest 确定钉死名单。
- **批次 3-6(其余 ~70 份,原地分批译)**:按 SEALED*/HITL*/DOCTYPE*/IMPROVE*/REVIEW* 等类别分批;docs/evidence/ 的 MANIFEST 副本与 doc-list JSON 一律不动(哈希钉死);docs/README.md 加一段翻译事件说明(2026-08-28 全量英译,中文原件在 git 历史)。
- 数字与术语对照冻结口径(4.2×/10.5%/CI 等)逐份核对,不重算不改写。

## 待办(本轮不做,记录在案)
- BriefLink 仓库预设清理(另一仓库,待你给出具体要换的内容)。
- README:你手写中文后我译;或我出英文初稿你改。
- 视频脚本(现在素材齐:P0 表面 + DWS 可见段 + Arm U 云端批准)。

## 时间
PR 1 一个工作单元内完成(代码量集中但机械);PR 2 分批,批次 1+2 随 PR 1 之后立即做,批次 3-6 视提交截止前时间推进、每批独立可交付。