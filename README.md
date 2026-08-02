# InvoiceLoop

**发票抽取的支持关系,不是发票抽取的正确性。**

每个抽出的字段带一条可机械验证的支持关系:它绑定到页面上哪块区域、
那块区域的独立 OCR 说了什么、旁边印的标签是什么、六个确定性门禁各自的裁决、
以及在哪里说不准。

## 它不做什么

不承诺抽得准。`~/Developer/dws-derisk/` 的六轮预注册实验证明:在 DWS 上,
抽错的时候没有可用手段知道它抽错了 —— 包括厂商置信度、算术校验、双模式分歧、
独立 OCR 引用校验,以及五个前沿模型的读图。

InvoiceLoop 不试图推翻这个结论。它换一个交付物:**支持矩阵**,不是判决。

## 为什么是发票

商业简报的支持关系是语义的,验不了。发票的支持关系是**几何的** ——
bbox 与页面区域的关系,可以用独立 OCR 逐词验证。

## 血统

BriefLoop 架构参考 v0.6.1 §3.6 支持充分性栈。该栈在 BriefLoop 中被标为实验性,
语义门禁 §8.4 明写"尚未交付"。InvoiceLoop 在一个支持关系可机械验证的域里实现它。

## 状态

M0–M4 全部落地,且已经过一轮完整验证(2026-08-02,
**总录:`docs/VERIFICATION_2026-08-02.md`**):

- **留出集实验**:100 份未参与设计的文档,H1–H6 预注册判据全过
  (分诊 lift 3.04× > 1.5 线)—— 分诊优于随机不再是校准集轶事,§8 限定一退役
- **人类验收**:GOAL.md 证伪终点五任务通过(warm 版),抓出并修复一个
  真实呈现缺陷;两条真人裁决入账,首个 audit bundle 打出
- **测试 116 条全绿**:第六轮错位事故 454 行回归、对拍 dws-derisk 的搬运保真、
  跨进程确定性 byte-compare、分诊集中度实测(本投影 4.10×,复现校准 4.2×)

```bash
# 全流程:extract → freeze → gates → matrix → panel(零 API,只读存盘证据)
python3 -m invoiceloop run --out runs/demo --crops

# 输入契约(§12):自己的发票 —— PDF 丢进 workspace/input/pdfs/
python3 -m invoiceloop ingest --workspace ws/    # 本地独立 OCR + DWS 抽取(需 DWS_API_KEY)
python3 -m invoiceloop run --workspace ws/ --crops   # 产出在 ws/output,panel 标注「不在校准集内」

# 人工裁决(append-only,不改冻结输入)与交付(含逐文件 sha256 清单)
python3 -m invoiceloop adjudicate --run runs/demo --doc <doc_id> --field total_gross \
  --claim-id FC-0042 --decision accept --rationale "证据齐" \
  --adjudicator <名字> --decided-at 2026-08-02T10:00:00
python3 -m invoiceloop bundle --run runs/demo

# 留出集(docs/HELDOUT.md;要花 DWS credits,判据已冻结)
python3 -m invoiceloop heldout plan --workspace runs/heldout-workspace
python3 -m invoiceloop heldout extract --workspace runs/heldout-workspace --budget 6000

# 测试
python3 -m pytest tests/
```

打开 `runs/demo/support_panel.html` —— 静态、离线、无需服务。
复核队列按支持强度升序:队首就是系统明确表示自己不知道的地方;
被拒的行带「DWS 指向这里」的裁剪图与独立 OCR,无引用区的行带整页图。

文档:`ARCHITECTURE.md`(设计契约)/ `GOAL.md`(冲突时优化什么)/
`docs/VERIFICATION_2026-08-02.md`(验证轮总录)/ `docs/HELDOUT.md`(留出集协议与结果)/
`docs/TESTING.md` + `docs/TESTING_FACILITATOR.md`(人类验收协议与主持包)。

校准语料与六轮实验证据:`~/Developer/dws-derisk/`(`REPORT.md` / `THRESHOLDS.md`)。
本仓库引用的每个数字都可从该仓库零 API 重算。
