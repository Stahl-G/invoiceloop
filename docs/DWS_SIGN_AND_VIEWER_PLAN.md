# DWS 签名封缄 + Viewer 并存:实施方案(2026-08-06)

来源:官方文档实拉(非记忆),日期见各页 `last_updated`。

- 签名:`https://www.nutrient.io/guides/dws-processor/tools-and-api/pdf-digital-signature-api.md`(2026-07-06)
- Viewer(app-provided 模式):`https://www.nutrient.io/guides/dws-viewer/developer-guides/open-client-provided-documents.md`(2026-06-10)

两件事互不依赖,可分别落地。**签名优先。**

---

## 一、数字签名封缄(优先)

### 1.1 现状缺口(项目自己承认的)

`adjudicate.py:430` 的 verify notes 原文:「包的真实性锚在带外公布的本包
sha256 —— verify 不是自己的信任根」。四层校验证明的是**包自内洽**:
成员哈希对得上、快照可重算、裁决绑定一致。但 `MANIFEST.sha256` 在包**里面**,
攻击者改完成员再重算 MANIFEST 即可自洽。**整条链唯一的非密码学锚点就在这。**

### 1.2 端点(实测文档,未跑通)

```
POST https://api.nutrient.io/sign
Authorization: Bearer $NUTRIENT_API_KEY
-F file=@attestation.pdf
-F 'data={"signatureType":"cades","cadesLevel":"b-lt"};type=application/json'
→ 返回已签名 PDF
```

省略 `appearance` / `position` / `formFieldName` = **不可见签名**,仍是密码学
签名。`cades b-lt` = 长期验证档:嵌入吊销信息 + 可信时间戳 —— 正是审计包要的。

### 1.3 设计:加一层外封,不动确定性工件

**关键约束**:attestation 不能进 `MANIFEST.sha256` —— 它证明的就是那份
manifest,自我包含会成环。所以做成**外封**,不是成员。

拆成两个命令,`bundle` 保持离线确定性不变:

| 命令 | 行为 |
|---|---|
| `bundle --run R` | **完全不改**。仍是离线、零网络、同输入同字节 |
| `seal --run R`(新) | 读 `audit_bundle.zip` → 造 attestation → 调 `/sign` → 写 `audit_bundle.sealed.zip` |

`seal` 的三步:

1. `manifest_sha256 = sha256(zip 内 MANIFEST.sha256 的字节)` —— 它传递覆盖每个成员;
2. `attestation.json`(canonical JSON,确定性,**不含我方时间戳** ——
   时间由签名的可信时间戳提供,我方不自报时间):
   ```json
   {
     "attests": "audit_bundle",
     "manifest_sha256": "…",
     "review_snapshot_id": "…",
     "run_dir_name": "run-0001",
     "n_docs": 3,
     "invoiceloop_version": "…",
     "signature_profile": "cades/b-lt"
   }
   ```
3. 把 attestation.json 渲染成**一页极简 PDF**(手写 PDF 语法,~30 行,零新依赖,
   确定性)→ POST `/sign` → 得 `attestation.signed.pdf`;
   sealed zip = 原 zip 全部成员 + `attestation.json` + `attestation.signed.pdf`,
   **MANIFEST 一个字节不动**。

> 备选:用 Processor 的 Markdown-to-PDF 造 attestation PDF(多一次 DWS 深度使用),
> 但会让 `seal` 多依赖一个端点。建议先手写 PDF,把网络面收到只有 `/sign` 一处。

### 1.4 verify 第五层

`verify_bundle` 的 `layers` 加 `"signature"`,沿用现有三态(True/False/**None**):

- 无 `attestation.signed.pdf` → `None`,notes 记「未封缄包」(与 v1 包无快照层同款处置);
- 有:
  1. 重算 `sha256(MANIFEST.sha256)`,比对 `attestation.json.manifest_sha256`;
  2. 比对 `attestation.json` 的字节与签名 PDF 内嵌内容一致;
  3. 密码学验签(CAdES 链 + 时间戳)。
- 验签需要 `cryptography` / `asn1crypto` —— **做成可选依赖**
  `pip install "invoiceloop[seal]"`。缺依赖时 `signature: None` +
  notes「签名存在但本机无验签依赖,未验证」。
  **按宪章四:记录缺口,不静默判过。**

这样离线四层的故事完全不破,新增的第五层是纯增量。

### 1.5 必须同时写进去的限定(宪章六)

DWS 用**它自己的证书**签。签名证明的是:

> 这份 attestation 在时间 T 经过 DWS 签名,且此后未被改动。

它**不证明**「这个包是 InvoiceLoop 出的」—— 除非自带证书。所以 verify 的
notes 应改成精确的说法,**不能改成「现在有信任根了」**:

> 第五层通过 = manifest 摘要被一份带可信时间戳的 DWS 签名固定;
> 签发主体是 DWS,不是本项目 —— 「谁造的包」仍需带外身份。

这条如果写飘了,失分比这个功能挣的多。

### 1.6 改动清单与工作量

| 文件 | 改动 |
|---|---|
| `invoiceloop/seal.py`(新) | attestation 构造 + 极简 PDF writer + `/sign` 客户端(key 只从 `NUTRIENT_API_KEY` 环境读,与 `dws_client.py:39-41` 同纪律) |
| `invoiceloop/adjudicate.py` | `verify_bundle` 加 `signature` 层;notes 按 §1.5 改写 |
| `invoiceloop/__main__.py` | `seal` 子命令 |
| `tests/test_seal.py`(新) | 封缄后四→五层全过;改 MANIFEST → signature false;改成员 → members false;无 attestation → None;无验签依赖 → None + note |
| `pyproject.toml` | `[seal]` extra |

约 150 行 + 测试,**半天**。需要真 key 跑一次端到端(信用额度消耗未核实)。

---

## 二、DWS Viewer 并存(次优先)

### 2.1 一个之前没算到的事实:隐私顾虑不成立

Viewer 有两种文档路径,官方原文:

> **App-provided documents** — Keep documents in your app or browser. Your app
> passes a file, URL, Blob, or ArrayBuffer directly to Web SDK, while DWS Viewer
> API authorizes and meters the viewer session.
> …In this app-provided flow, the document isn't uploaded to DWS.

也就是说**发票 PDF 不出浏览器**,DWS 只发一个会话 jwt。C 项「全部本机处理」
的隐私叙事不受损 —— 只需如实写「Viewer 会话向 DWS 认证,文档不上传」。

### 2.2 集成形状

后端(workbench 加一个路由):

```
POST https://api.nutrient.io/viewer/sessions
Authorization: Bearer $NUTRIENT_DWS_VIEWER_API_KEY
body: {}            # 省略 allowed_documents = app-provided 模式
→ {"jwt": "…"}
```

前端(裁决页):

```js
await NutrientViewer.load({
  container: "#viewer",
  session: "<jwt>",
  document: "/files/<run>/pages/<doc>.pdf",   // workbench 已有的本地路由
});   // 省略 licenseKey —— 会话即授权
```

### 2.3 纪律:必须是可选面,默认不变

- **默认仍是自建面板**(整页渲染 + bbox overlay + 门禁 chip + 快路)——
  那是 F 项 13 分的实体,不能被换掉;
- Viewer 是裁决页上的一个切换按钮,`NUTRIENT_DWS_VIEWER_API_KEY`
  未设置 / 无网络 → 按钮不出现,页面行为与今天逐字节一致;
- **`demo` 路径零 API 的性质必须保住** —— 这是评委在自己机器上能跑通的前提。

### 2.4 老实说的成本

- 每次加载消耗一个 viewer session(有月度配额);
- 需要引入 Web SDK 的 JS 资源(CDN 或 vendored)—— workbench 目前是纯 stdlib
  + 无外部资源,这会破坏离线性,**所以只能挂在开关后面**;
- 官方明写:会话必须由后端创建,加载后不刷新,`setSession()` 在
  app-provided 模式下不支持;
- 功能上 Viewer 给的是标注/表单/协作,InvoiceLoop 并不需要;**真实收益是
  多页文档的渲染与缩放体验,加上出题方点名的那面子。**

### 2.5 改动清单与工作量

| 文件 | 改动 |
|---|---|
| `invoiceloop/workbench.py` | `POST /viewer-session` 路由(沿用现有 Host 白名单 + Origin 校验);裁决页加切换按钮与容器 div |
| `invoiceloop/workbench_style.py` | viewer 容器样式 |
| `tests/test_workbench.py` | 无 key 时按钮不渲染、页面与今天等价;有 key 时路由存在且不泄漏 key 到前端 |

约 100 行,**半天**。风险集中在「别把离线 demo 弄坏」。

---

## 三、顺序与验收

1. **先签名**:补的是自己承认的缺口,密码学升级,与 brief 两次点名的
   "digitally sign the result so its authenticity is provable" 直接对上;
2. **再 Viewer**:优化面 + 出题方偏好,默认路径零变化;
3. 两者都要一次真 key 端到端,并把限定(§1.5、§2.3)与功能同屏写进 README。

**验收判据**(先写后做):

- 封缄包在**断网**机器上 `verify` 出五层,单字节篡改 MANIFEST → `signature: false`;
- 缺可选依赖时 `signature: None` 且 notes 说明未验证,**不得报 true**;
- `NUTRIENT_DWS_VIEWER_API_KEY` 未设置时,裁决页 HTML 与本次改动前**逐字节相同**;
- `demo` 全流程仍零 API、零外部资源。
