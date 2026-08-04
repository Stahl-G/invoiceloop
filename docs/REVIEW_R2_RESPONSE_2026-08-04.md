# 第二轮双评审的应答(2026-08-04)

两份评审同日到达,评的都是 65/100 修复批之后的 HEAD:

- **复审(65 → 81/100)**:修复声明抽查 10/10 属实;新发现集中在「修复引入的缺陷」。
- **十二路新评(82/100)**:红队 6 类全过,但抓出一个 P0(--crops 崩批)与一批 P1。

两份的代码面发现合并去重后本轮全部落地,每条带回归测试(259 条全绿,
另做评委机模拟:`export INVOICELOOP_CORPUS` 后 240 条产品测试同样全绿)。

## 本轮修复

| 评审项 | 出处 | 修复 |
|---|---|---|
| `run --crops` 遇坏 PDF 整批崩溃(workbench 上传同路) | 82 评 P0-3,两路红队复现 | `render_pages`/`render_crop` 坏文件返回空(兑现 docstring 既有承诺),pipeline 记 `pages_unavailable` 事件不静默;加 RENDER_TIMEOUT |
| C3 日期门对 MM/DD/YYYY 双向失效 | 82 评 P1-2 | 反序元组比较改为显式格式判定(ISO/day-first/month-first),歧义对由同文档无歧义日期定调,定不了回退 day-first(预注册行为不漂移);7 个新测试含误报+漏报双向 |
| verify 三条 traceback 逃逸(快照/账本 CRC、zlib.error) | 81 评 P1-3 | 深层读取全部转结构化失败;MANIFEST 畸形行同收 |
| CLI 错误包装半落地(RunExistsError 等 5 类裸 traceback) | 双评 P1-2/P1-4 | main() 改 catch Exception(SystemExit/KeyboardInterrupt 非其子类,自然穿透) |
| workbench 读图建议层给冻结拒绝值递「采用」按钮 | 82 评 P1-5(D 维度扣分) | 建议值与该行冻结拒绝集做同规则归一化比对:命中 → 照常展示+标注「同值冻结时被拒」+**不给按钮**;自家钉死契约测试里的 total_net=10.00 正是这个案例,契约测试已改钉新语义 |
| `.PDF` 大写扩展名静默丢单 | 82 评 P1-6 | discover 改 suffix.lower() 比较(宪章四自家失守处) |
| 合法 JSON 非对象([1,2,3])崩批;畸形 TSV 行 IndexError | 82 评 P1-7 | register_artifacts 与 ingest resume 加 isinstance 守卫;load_vision_answers 跳过畸形行 |
| ingest 摘要谎报:非 200 计入 extracted(拿错 key「全部成功」) | 82 评 P1-8 | extracted 只计 200;非 200 存盘照留(被拒证据属分母)但进 extract_failed |
| `INVOICELOOP_CORPUS` 遮蔽 fixture(评委 export 后 29 测试变红) | 81 评 P1-1 | conftest 新增 `pin_corpus` 双设主变量+别名,8 个测试文件统一换用;**同款产品侧两处一并修**:make_server 与 build_audit_bundle 原来也只设别名 |
| layers.binding 零裁决包报 true(真空理) | 81 评 P2 | 无裁决记 None + note,与 snapshot 层诚实标记一致 |
| pipeline mkdir 守卫线程级 TOCTOU | 81 评 P2 | O_EXCL 占坑 run_manifest.json:输家拿 RunExistsError,不再 FileExistsError 裸奔或交错写半成品(并发测试钉死) |
| decided_at 无格式校验(「下礼拜吧」可入账) | 82 评 P2 | ISO 8601 解析校验,垃圾时间拒入账 |
| 裁决 append 跨进程无锁(仅 threading.Lock) | 82 评 P2 | adjudication_ledger.lock  flock 跨进程临界区(Windows 退化有说明) |
| subprocess 无超时(poppler/tesseract) | 82 评 P2 | ocr_ingest 与 evidence 渲染统一超时常量 |
| doctor 不查 pdfinfo | 82 评 P2 | 已加(裁剪坐标换算的页尺寸来源) |
| README 安装节缺 venv 指引(PEP 668 双连撞) | 82 评 P1-1 | 加 venv 两行 |

## 诚实文档批(宪章:自家文档先达标)

- **README「改一个字节就失败」是夸大的** —— 协同伪造(工件+MANIFEST+快照+账本
  全重写)实测会过,这是钉边测试早已声明的信任边界。README 改为「单点篡改必被
  对应层抓住;真实性锚在带外 sha256」。**上轮应答文档声称此句已改,实际未改 ——
  那是应答失实,本轮真的改了,并在此留痕。**
- **ARCHITECTURE 66%/70% 同案两数** —— 以钉边回归为准统一为 70%(118/168,
  test_binding_regression.py 逐行钉死;DEMO.md 的 111(66%) 是片段级规则变体的口径,
  不是本系统 shipped 的文档级规则)。
- **ARCHITECTURE §5.3「输入签名对不上则拒绝执行」** —— 门禁本身并不重验签名;
  实际保护在裁决追加的快照一致性检查与 bundle verify。说辞已对齐实现。
- `.qoder/`(IDE 产物)与 `.DS_Store` 移出 git 跟踪并入 gitignore。

## 核查后否证的评审项(不修,留证据)

- **「H6 校准分母 1604→1305 静默漂移」**(82 评 P2):全仓检索,1305 不存在于
  任何文件;1604 唯一出现于 docs/HELDOUT.md(247/1604=15.4%,算式自洽)。
  无漂移可修。评审也会错 —— 按宪章,核查不了的断言不进修复清单。

## 评估过、暂不做的(说明理由)

- **fixture 携带 OCR 子集让钉边回归在 clean clone 可跑**(82 评 P1-11):
  方向认可,但 454 行钉边回归依赖 DocILE 词级 OCR 原文,体量与许可都要核;
  赛后以「最小可公开子集」单独立项,不赶在提交前塞大文件。
- **跨进程 append 的锁文件进不进快照**:不进 —— 锁文件不是工件(与
  event_log 同理),快照成分保持稳定。
- C1 失败行的绿徽章信号混合(82 评 P2):finding≠verdict 是设计哲学,
  panel 已有 finding 层;视频口播讲清,不改渲染。

## 仍是提交侧作业(代码面帮不上的)

视频、英文 pitch + Nutrient 点名、说法层(给谁/监管楔子/竞品对位)、
合规披露(pre-period tag + DISCLOSURE 文件 + 开赛书面问询)、公开前历史清理
(author 邮箱与私有路径)。与上轮清单一致,优先级不变。
