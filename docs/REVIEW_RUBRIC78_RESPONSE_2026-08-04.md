# Rubric 评审(78/100,证据约束型评委)的应答(2026-08-04)

这份评审用用户预冻结的 rubric v0.1 评 commit e8aa56d,结论 78/100:
「架构思想有获奖差异化,但产品价值和量化效果没追上架构复杂度」。
红队实测全部属实(医生/demo/裁决/bundle/篡改),无争议项。

## 本轮修复

| 评审项 | 修复 | 提交 |
|---|---|---|
| P1 缺 raw DWS / 简单阈值 / InvoiceLoop 三方比较(rubric E 项最大缺口) | `scripts/baseline_comparison.py` + `docs/BASELINE_COMPARISON.md`:TIER1 上 raw DWS 静默错误 29.97% → 双模式一致 14.95% → InvoiceLoop 8.88%;文档静默失败 54.5% → 31.5% → 21.1%;偏差路由召回 82.6%。三点构成单调风险—覆盖曲线,分诊在风险端显著优于简单基线。同屏写明:探索性非预注册、产品不自动放行、残余不是零;度量数学 4 条测试钉死 | 本轮 |
| P3 demo 在评委机 1 failed(OCR-blocked 展品写死) | 根因:046e0c49 是否被 pdftotext 抽出文字层取决于 poppler 构建。改为钉「受阻必显式」不变量(事件+阻断 finding 成对),不钉「某份文档必须受阻」;demo note 按实测生成 | b98a0ae |
| P4 版本绑定不全 | run_manifest 记 `code_revision`(git commit,非 git 环境如实 null);读图 answers6.*.tsv 捕获进 run/bundle(并行会话,eb383cc) | b98a0ae + eb383cc |

## 设计待用户点头(P2,+4~6 分)

TIER1 进入运行时策略 + 整单放行/阻断 + 裁决后最终 JSON/CSV 导出。
改分诊口径、引入「整单放行」新概念 —— 与 C8 同级,先设计后实现。

## 用户决策项(不变)

P0 资格书面确认(决定是否参赛的前提)、视频(rubric 给了分镜脚本,
live_dws_demo.sh 可直接录)、pitch 与 heavy-lifting 一句话(评审已起草,
在 Devpost 文案里采用即可)、DocILE 许可核查。

## 评审里我们不同意扣分的一处(留痕,不改)

「六轮实验证明做不到,那条路封死了」被评审读成「提高抽取正确性整体不可能」。
原文语境是「没有单一信号能识别所有错误」——README 与 ARCHITECTURE §9 的
不主张清单都是这个口径。文档措辞已在先前轮次收敛,不再改;视频口播注意即可。
