# 65/100 评审的应答(2026-08-04)

外部 10 路评审(静态/复现 3 + 代码/信任层 4 + 红队实测 3)给 InvoiceLoop
打出 65/100:「及格但平庸,修完 P0 可进冲奖档(83–87)」。
本文件是逐条应答 —— 已修、已在前序提交修过、用户决策项,三类分开。

## 它评的是旧 HEAD:前序提交已修

| 评审项 | 早已修于 |
|---|---|
| P0-2 README 主 demo 干净环境跑不通 | `demo` 命令 + 内嵌语料(eb98143),fresh_venv_check 含 demo 段且全过 |
| P0-4 脏 PDF 崩掉整个 ingest 批次 | ocr_ingest 子进程失败统一退 OcrUnavailable + 回归测试(22e5c43) |
| P1 抽取失败文档隐身(ingest 摘要丢弃) | workbench ingest 失败文档与原因显式列页(22e5c43 #6) |
| P1 24% 测试评委机全 skip | 评审口径即设计:研究测试守卫 corpus_available(),fresh-venv 175 过 41 跳,产品路径不受影响(ade37f5) |

## 本轮修复(776ded5,各带回归测试)

| 评审项 | 修复 |
|---|---|
| P1 损坏存盘响应 crash 整批 | `register_artifacts` 标 corrupt 记 sha,`_load` 返回 None → extraction_present 阻断;run 照完 |
| P1 静默丢单(run 文档集=raw) | 文档集 = input/pdfs ∪ raw(CLI/workspace/workbench/demo 三处);缺 raw 由 extraction_present 记阻断 |
| P2 doc_blocked 只进 event_log | `independent_ocr` 文档级阻断发现进 gate_report.findings |
| P1 panel 页脚打印自报哈希不重算 | 页脚重算账本 sha 并比对,不符显式 ⚠;另加「渲染时裁决 N 条」staleness 行 |
| P2 verify 不报告深度 / CRC 裸 traceback | verify 返回 layers(members/snapshot/binding)+ notes:v1 包明说只有成员级;三层全过也必须声明「真实性锚在带外哈希」;CRC 损坏为结构化失败 |
| P0-3 协同篡改无外部锚 | 不修代码修说法:新增钉边测试「全一致伪造会过」(test_fully_consistent_forgery_passes_and_that_is_the_boundary),README/verify notes 把防篡改收敛为「单点篡改可检出,锚在带外 sha256」 |
| P2 CLI 裸 traceback | main() 包 SystemExit:「错误:<一句话>」 |
| P2 恒真断言 / M2 脚手架 skip | 删 `or True`;binding 回归 import 失败应变红 |
| P1 TESTING_RESULTS 裁决数与实物不符 | 文档 3→2(与账本实物一致) |
| P1 提交物缺口(部分) | LICENSE(MIT)、.env.example、README 研究测试说明、ARCHITECTURE 无墙钟取舍说明 |

## v2 实物再生成(P0-3 的主体修复)

runs/demo 是 H0 之前的 v1 run(无 review_snapshot、panel 无裁决投影、
bundle 只有成员级校验)。用当前代码重生成 runs/demo-v2(160 份校准存盘,
零 API):全 v2 工件 + 重打 bundle + verify 三层。旧 runs/demo 保留原样
(run 不可变),两条 2026-08-02 的真人裁决留在它自己的账本里 ——
它们的快照与 v2 不同(门禁加了 independent_ocr 发现),搬进 v2 会是
orphan,不如实。

## 用户决策项(评审也标了「离线核不了」)

1. **代码新鲜度(取消资格级)**:29+ 提交全部早于 8/17 开赛。应对是
   披露 + 增量,不是 rebase(造假且可查)。开赛时按 Devpost Rules 写
   既有项目披露;书面问询主办方留证。H1 之后的实质功能恰好在赛期内
   可继续(workbench 是 8/3 建的,赛期里做盲测复测与视频)。
2. **公开 repo 与历史清理**:runs/ 历史工件、.DS_Store、author 邮箱、
   私有绝对路径 —— 推送前一次性清理;建议新仓库只带干净历史,不改日期。
3. **视频 + blind 复测**:素材齐(21,900 拒对、Harry Huge 补录、
   046e0c49 互换事件、verify 篡改对照);录前用 TESTING_FACILITATOR.md
   做一次不知情被试复测。
4. **Nutrient 一句话**:README 已是赞助商中立口径(「没有任何单一信号
   能识别所有错误 → 组合层」),Devpost 文案照此,别写成「DWS 不可靠」。
5. **F 维度三句话**:细分客户(被审计/被监管的发票处理团队)、切入点
   (审计交付物而非抽取器)、大厂不做理由(信任层不是抽取卖点,卖不出 license)。

## 红队通过项(评审记分,不动)

模糊扫描件全阻断、缺字段不编造、prompt injection 无消费者、改后再改回
supersession 链完整、1 字节篡改 verify 即失败、超大 PDF/无 poppler/无 key
优雅降级 —— 与实现一致,无动作。

## 评审提的新能力( backlog,不是 bug)

- 跨文档查重(同号不同内容零检出)—— 「跨单核验」卖点,赛后做。
- 明细行级对账(字段集无明细)—— demo 叙事避开「异常检测」话术即可。
- net+vat≠gross non-blocking —— 设计哲学(finding 不是 verdict),视频口播。
