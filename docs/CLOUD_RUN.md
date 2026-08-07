# Cloud Run 部署

## 它解决什么,以及**不**解决什么

| | |
|---|---|
| ✅ 强制项「Google Cloud 基础设施服务」 | Cloud Run 托管 revision + `.run.app` URL |
| ✅ 评委点得开 | 镜像内烤好 `demo` workspace,冷启动即开队列 |
| ❌ **不是**持久化 | Cloud Run 实例是临时的,文件系统随回收消失 |
| ❌ **不是**真的 HITL | 公开实例只读;真实裁决只在本地可写工作台上进行 |
| ❌ **不让产品变好** | 信任内核是确定性 Python,本地跑得一模一样 |

对外只能说「合成演示部署在 Cloud Run」。**不许说**「系统跑在云上」
或「云端持久化」(宪章六)。

## 公开实例必须只读

工作台有九条写入路由,其中 `POST /decide` 追加的是**人工裁决账本** ——
「某个人看过并判了」的证词。`--allow-unauthenticated` + 可写 =
任何人都能伪造一条人类裁决。

所以容器入口默认加 `--read-only`:全部 POST 返回 403,每一页顶部有横幅
说明。`INVOICELOOP_READ_ONLY=0` 能关,但那**只在私有 IAM 部署下才成立**。

录视频时分两个镜头:HITL 那段拍**本地**可写工作台(真在裁决),
「已部署」那段拍 `.run.app`。两个都诚实。

## 没有 GCS

演示 workspace 在 `docker build` 时就 `invoiceloop demo` 烤进镜像,运行期
不取任何外部数据。上一版有一条可选的 GCS 拉取,已整个删除:

- `python3 -m invoiceloop cloud pull … || true` —— 认证失败、SDK 缺失、
  包损坏全被吞掉,然后**静默拿 demo 数据顶替真数据**。这正是这个项目
  存在的目的所要防的事(宪章四)。
- `tar.extractall(dest)` 无成员校验 —— 路径穿越。
- 文档说的「持久化」不成立:入口只 pull 不 push,写入永远不会被保存。

删掉这条路径,三个问题同时消失,少一个服务、少一个失败面。

## 本地验镜像

```bash
docker build -t invoiceloop:local .
docker run --rm -p 8080:8080 invoiceloop:local
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8080/decide  # 期望 403
```

## 部署

```bash
# 一次性(需要项目已开计费)
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

./scripts/deploy_cloud_run.sh
# 或 PROJECT=… REGION=… SERVICE=… ./scripts/deploy_cloud_run.sh
```

脚本固定带 `INVOICELOOP_READ_ONLY=1`。`--allow-unauthenticated` 只有在这个
前提下才是安全的。

## 绑定与探针

- 本地 CLI 默认 `--host 127.0.0.1`(loopback,不变)
- 容器入口 `--host 0.0.0.0 --port $PORT`,默认 `--allowed-host .run.app`
- 探针 `GET /healthz` 先于 Host 闸,且不跑 `doctor`(它会查研究语料)
- **Host 后缀白名单不是鉴权** —— 它只挡 DNS rebinding,别当访问控制用

## 取证

部署后要留下:project / service / revision / image digest / URL / 时间戳 /
远端 smoke 输出 / 控制台截图,放 `docs/evidence/cloud_run_<date>/`。
**拿到这些之前,任何地方都不许写「Google Cloud 强制项已满足」。**
