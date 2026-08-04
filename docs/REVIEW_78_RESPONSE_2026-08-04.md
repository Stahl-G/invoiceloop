# 78.5/100 评审(裁判视角)的应答(2026-08-04,第二轮)

裁判视角总评 78.5/100:「技术上是 85+ 的料,提交上是不及格」。
红队四条攻击(改成员/改裁决/截断 zip/原包)全被拦,与实现一致,无动作。
代码面发现本轮修复(commit f998ad0),提交面发现全部属实且是用户决策项。

## 本轮修复(各带回归测试,271 条全绿)

| 评审项 | 修复 |
|---|---|
| verify 绑定层不重放 review.project():自洽但内部矛盾的 supersession 链能过 | 绑定层现在重放链语义:悬挂/跨槽位/成环 supersedes、同槽多 tip、幽灵 claim_id、decision 语义(correct 必带值、其余禁带)全部转结构化失败;另钉诚实边界:链语义也自洽的伪造照样过(锚在带外 sha256) |
| 注入抵抗是架构事实但无断言 | 三条「无消费者」断言:指令值被冻结绑定拒绝并入账事件;OCR 词层塞 SYSTEM:APPROVE-ALL 后逐字段裁决与干净版完全相等;读图出站 payload 唯一文本块是固定 prompt,doc_id/文档文本零插值 |
| 活 DWS 单发无重试 | extract 对网络错误与 5xx 指数退避重试 2 次;4xx 不重试(被拒是终局答案,存盘纪律);重试耗尽照样抛 → 阻断方向不变 |
| pdfinfo 无超时 / vision TSV 跳过静默 | RENDER_TIMEOUT 统一覆盖;load_vision_answers 加 on_skip 回调,pipeline 记 vision_rows_skipped 事件 |
| panel「集中度 4.2×」无来源(自家诚实文化非要对齐的点) | 改为三口径并列带出处:六轮校准 4.2×(R-D 路由)/ 本投影 4.10×(test_triage_concentration 钉死)/ 留出集 3.04×(HELDOUT.md);CLI help 同句夸大一并修 |
| 无 CI | .github/workflows/ci.yml:干净 ubuntu + poppler → doctor → demo → pytest |
| Demo 零 API,评委看不到 DWS 干活(赛道有效性) | scripts/live_dws_demo.sh:真 DWS ingest → run --crops → workbench → bundle → verify 一条命令,每步打印产物路径,录屏直接用 |

## 红队通过项(不动)

改成员/改裁决/截断 zip 全拦、原包 verify ok、回归套件 58 过 —— 与钉边测试一致。
「v1 包快照/绑定两层为空」是设计(v1 形态如实标注校验深度止于成员级)。

## 用户决策项(与此前清单一致,不代劳)

资格确认邮件(info@devnetwork.com,赛前第一天前)、公开 repo + 历史清洁
(runs blob、author 邮箱、.DS_Store、DocILE 再分发许可核查)、视频
(素材:live_dws_demo.sh + ES-0005 纠错故事 + ocr_blocked 展出 + 篡改对照)、
README 第一屏 pitch 与合规时间线(文案进 README 前用户过目)、不知情被试复测。

## backlog

跨文档查重(C8)—— **已实现**(用户 2026-08-04 点头后):crossdoc.duplicate_groups
按 (卖家, 票号) 分组,同号同卖家内容冲突 / 疑似重复提交两类;non-blocking
finding + 涉案 invoice_number 行 fail → 自动进复核队列;panel 加并排对照一节;
gateinfo 双语一句话;10 条测试钉死语义(含「不同卖家同号放行」「agentic 异值
不许盖过 understand」)。跨 run 查重与模糊匹配按设计不做(说辞写在模块 docstring)。
