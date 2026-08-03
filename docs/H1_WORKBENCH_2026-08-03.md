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
