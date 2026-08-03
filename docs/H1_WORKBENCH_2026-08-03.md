# H1 复核工作台(2026-08-03)

H0 完整性地基之后,复核者钦定的下一单元:评委面向的复核工作台 ——
本地 loopback Web 应用,把「上传 → 抽取 → 复核队列 → 裁决 → 交付报告 →
bundle/verify」做成 2–4 分钟走得完的端到端体验。用户补充的硬需求:
**人工审核环节在网页上直接输入问题**(按钮 + 输入框,不是只能看)。

## 形态决定(钉死)

- **stdlib http.server,零新增依赖。** 不加 Flask/FastAPI —— pyproject 运行时
  仍只有 requests;评委 clean clone 后 `pip install .` 即可,不多装任何东西。
- **仅 127.0.0.1 loopback。** 不提供 host 参数;要给别人看就走 audit bundle,
  不把这个服务放上网络。
- **server-rendered HTML + 渐进增强 JS。** 无 JS 时除浏览器上传/校验外全部可用;
  文件上传回落到输入契约(把 PDF 放进 `workspace/input/pdfs/`)。
- **人只写裁决,且只能写裁决。** `/decide` 透传 `adjudicate.append_adjudication`
  的同一套校验(快照一致性、三元一致、决策语义、supersession),工作台不开后门。
- **decided_at 由服务器在点击时盖章。** 点击就是人给出时间的动作;裁决是人的
  输入,不是重算工件,run 工件的确定性不受影响。
- **视觉纪律借 briefloop-prototypes**(Visual System v1):DWS/模型值 = 紫
  (advisory,永不绿),人工确认 = 蓝,确定性通过 = 绿,阻断 = 红,不可用 = 灰。

## 构建方式(子代理分工)

- 测试代理:按钉死的路由/表单契约写 15 条契约测试(`tests/test_workbench.py`),
  测试先行,服务器尚不存在时收集不炸。
- 视觉代理:按钉死的 65 个选择器契约写 `invoiceloop/workbench_style.py`,
  token 层借 prototype,语义色纪律守住(人工确认全蓝,绿只给确定性通过)。
- 主会话内联:服务器本体(`invoiceloop/workbench.py`,路由 + 动作 + 页面),
  零文件重叠。
- 对抗复核 workflow:三维度(安全与宪章 / 裁决接线正确性 / 契约漂移)
  独立发现 + 逐条反驳式验证(结果见下节)。

## 集成时自查抓到并修掉的

1. `/verify` 的 form 用了 `enctype="application/octet-stream"` —— 浏览器根本不会
   带文件内容(Python 3.14 没有 cgi,不糊 multipart;改为 fetch 原始字节,与
   上传同一路径,no-JS 回落到 CLI `verify`)。
2. `/decide` 重定向丢了表单里的语言(中文页面提交完跳回英文页)。
3. `snapshot.build_input_manifest`:一个读图文件都不存在时(workspace 永远如此),
   `--vision/--no-vision` 产出两个不同指纹,重放在 CLI 与工作台之间失灵 ——
   归一为 None(视野文件存在时才进指纹)。
4. rationale/adjudicator 空串绕开 HTML required 直接 POST 会入账 —— 服务器侧补校验。
5. adjudicator cookie 写时 quote 读时不 unquote(中文名回显变百分号)。

## 冒烟(真实 PDF + 真实 OCR + crops)

全部页面 200,根路径 303 → /queue;POST /decide(correct,中文理由)→ 303 →
队列行出现「当前裁决 HD-0001 … 提交将取代它」,交付报告 1/10 + 修正清单;
证据裁剪图经 /files 正常出图。15 条契约测试 + 全量 184 条全绿。

## 已知边界(记录,不修)

- 同名 PDF 重传不会重新 OCR/重抽(断点续跑纪律);要重抽先删 ocr/ raw 对应文件
  (上传页有提示)。
- crop 渲染失败(损坏 PDF + render_crops)会让 /ingest 500 —— 阻断不藏,页面给
  traceback;CLI 同样行为。
- 裁决并发的最后防线是 append 的 supersession 校验:两个标签页同时裁决同一槽,
  第二个提交 400(过期 supersedes),不静默覆盖。
- i18n 是 chrome 级双语(按钮/标签),证据内容(OCR、理由)保持原文。

## 对抗复核结果

24 个代理(3 维度发现 + 逐条反驳式验证,909k token):12 个发现提交,
验证后 **17 项确认**(含两维度重复报告同一问题),全部修复并各带测试:

| # | 严重度 | 发现 → 修复 |
|---|---|---|
| 1 | critical | 写操作端点无 Host/Origin 校验:跨站表单可烧 DWS credits、伪造裁决进 append-only 账本;DNS rebinding 可读全部 → Host 白名单 + POST Origin 检查(403) |
| 2 | critical | 长驻进程 OCR lru_cache 永不清:换新 OCR 后用旧缓存绑定,清单记新 sha → ingest 后显式清两个缓存 |
| 3 | major | /decide 无锁竞态:并发写出重复 decision_id(实测 261/300)且 verify 查不出 → append 临界区持锁 + verify 查 decision_id 唯一性 |
| 4 | major | 同名不同内容 PDF 覆盖后旧 OCR/raw 不失效:新页面图配旧证据,门禁全绿 → 内容变化自动失效下游证据,响应列出 invalidated |
| 5 | major | cmd_ingest 的 SystemExit 穿透所有异常处理:空 workspace 点处理 = 掐连接 → 转 400 页 |
| 6 | major | ingest 摘要丢弃:部分文档失败时悄悄少文档 → 失败文档与原因显式列页 |
| 7 | major | `.wb-crop img` 选择器永不匹配(class 在 img 上):证据图按原始分辨率撑破版式 → 合并为 `.wb-crop` |
| 8 | major | 无 JS 时 correct 提交不出修正值(input 恒 disabled)→ HTML 不带 disabled,JS 加载后按选择禁用,语义服务器守 |
| 9 | major | 两步确认武装态不换档:armed 后改选决策,确认文案说谎 → radio change 解除武装 |
| 10 | minor | 404 页未转义请求路径(全应用唯一未转义反射面)→ 转义 |
| 11 | minor | 非 zip 上传 /verify → 500 整页 traceback → verify_bundle 内置 BadZipFile 失败分支(CLI 同收益) |
| 12 | minor | `.wb-topbar-inner` 无规则:顶栏布局塌 → 补规则 |
| 13 | minor | report 完成度测试恒真(断言支永远成立)→ 改精确计数断言 |
| 14 | minor | 队列页 rationale XSS 测试守的是无输出区域 → rationale 渲染进当前裁决提示(转义),测试同时断言转义后存在 |

被反驳不成立的(记录,不改):缺失 run 域的手工构造 POST(loopback 单用户无触发路径)、
handler 实例跨请求残留(HTTP/1.0 无 keep-alive)、三个 class 无样式(无契约可漂)、
/ingest 双代竞争(pipeline 的 mkdir(exist_ok=False)已守)。

顺手带出的一个复核未报的洞:损坏 PDF 让 pdftotext/pdftoppm 抛
CalledProcessError 炸穿 ingest —— 现在统一退到 OcrUnavailable 阻断(宪章四)。

## 用户实测(2026-08-03 晚,warm subject,15 条真人裁决)

4 份真实发票(3 正常 + 1 OCR 受阻的退化扫描件),40 槽。用户独立完成
15 条裁决(8 correct / 6 abstain / 1 accept,含 Harry Huge 缺值补录),
全部良构(快照绑定、无冲突、无改判)。bundle 54 成员,verify 三层全过。

实测抓出三个真虫(均已修复 + 回归测试):

1. **OCR 受阻文档没有整页图** —— `render_pages` 被关在 OCR 正常的分支里,
   受阻文档每行都「没有原图」,复核直接断粮(用户原话,HD-0015)。
   整页渲染不依赖 OCR/响应,提前到所有有 PDF 的文档。
2. **上传 tab 链接拼成 `/upload&lang=zh`** —— 按有无 query string 选 `?`/`&`,
   拼错就是 404;「无法返回」是 404/消息页没有导航 —— 导航现在永远指向
   一个真实存在的 run。
3. 快捷问题标签拼接产生「;;」(cosmetic)—— 拼接前先剥尾部 `;` 与空白。

另:这份 15 条裁决的 run 已打成 bundle 收档;受阻文档的整页图要新的
run 代才有(旧 run 不可变,历史不动)。

## 读图门的实测回答(2026-08-03,046e0c49 角色互换事件)

用户问「读图为什么没开、开了会怎样」。答案分两层:

**为什么默认没开**:读图作答是 dws-derisk 第六轮的研究产物(整页渲染 →
三个前沿模型作答 → answers6 tsv),从未移植成 ingest 的活的步骤;
workspace 没有 vision/ 目录,读图门如实报「未测」而不是跳过。

**开了会怎样(在同一 workspace 上实测)**:把校准档案的 answers6 tsv
拷进 ws/vision/ 起新 run 代(run-0003)。4 份文档里只有 046e0c49
(正是 OCR 受阻、其他机械信号全灭的那份扫描件)有读图作答;它的
10 个槽里 8 个 DWS 没返回值(读图门按设计报未测),但有值的 2 个槽
**全部触发 warning —— 而且恰好是 DWS 把买卖双方抽反了的两个字段**:

| 字段 | DWS understand | DWS agentic | 读图 A/B/C(一致) | 用户裁决(独立做出) |
|---|---|---|---|---|
| buyer_name | Cumulus-Muskegon - WVIB-FM(错) | SHIYA IFA | **SHIYA IFA** | HD-0016 修正 → **SHIYA IFA** |
| seller_name | SHIYA IFA(错) | Cumulus-Muskegon - WVIB-FM | **Cumulus-Muskegon - WVIB-FM** | HD-0020 修正 → **Cumulus-Muskegon - WVIB-FM** |

用户在看不到任何机器信号的情况下(纯看整页图)做出的两个修正,
与读图模型的作答逐字一致;读图门的 warning 指的正是这两个
被抽反的字段。这是「OCR 受阻文档上读图是唯一幸存的机器信号」的
最佳演示。但宪章不动:读图门仍是 warning 不是判决 —— 读图相对 DWS
的独立性过了预注册线(lift 1.29×/1.33× < 1.5,THRESHOLDS §6g),
但读者自身静默错误 8.6–15.8% 远超 1% 线、弃权 59–61%,所以分歧
只是「值得看」而非判决。它印证,它提示,它不裁决。

> 勘误(2026-08-03 晚,保真复核抓出):本节初版写「读图与 DWS 失败模式
> 相关(非独立,lift 2.40×)」是错的 —— 2.40× 是双模式分歧的 lift,
> 读图的独立性判据已通过;warning 的真实理由是读者自身错误率与弃权率。
> 另:表中读者 C(GPT 5.6 SOL)在第六轮因 63.1% 内容出现在别的文档被
> 整体作废,不进任何判定,此处仅作机制演示。

## 读图预填建议层(2026-08-03 晚)

用户提案「需要裁决的默认开读图,读图出问题再交人」的合规版本。
不能要的一半:读图自动裁决 —— 「读图出问题」没有探测器(读图模型自己
就是抽取器,第六轮 118 行错位就是某读者自信地错、零自报)。可以要的一半:
读图默认开,但只建议不裁决 —— 交付不变量守住:每个发出的值要么有机械
支持,要么有一次人类点击。

- **建议层(workbench)**:行内紫色 advisory 块「读图建议:X · n/n 读者一致
  + [采用建议]」。采用只预填表单(accept 或 correct+修正值+理由预设),
  提交与署名仍是人;读者分歧时摊开各值不给采用按钮;全弃权如实显示
  「读图也看不清」。一致性用与双模式门禁同一套 fields.normalise。
  测试钉死:渲染建议后裁决账本仍为空(预填只是表单状态)。
- **vision-ingest**:`python3 -m invoiceloop vision --workspace ws/` ——
  packet 规格由子代理从 vision_eval6.py 逐项抄回(DPI 150 全页、五条纪律
  prompt 逐字、tsv 列序、ABSTAIN 约定、空=弃权);单文档 API 调用
  (纪律 5 本来禁拼图);tag D = Claude Sonnet 5,需 ANTHROPIC_API_KEY,
  缺 key = typed unavailable;断点续跑只追加不重写。
- **answers6 glob 修复**:VISION_READERS 曾是硬编码 ABC 名单 —— 新读者的
  tsv 会被 load_vision_answers 漏读、被输入指纹漏哈希(改了作答旧 run
  照样被重放)。现在按盘上 answers6.*.tsv 全量读、全量哈希。
