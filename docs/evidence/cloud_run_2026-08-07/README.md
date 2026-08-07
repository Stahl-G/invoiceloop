# Cloud Run 部署取证(2026-08-07)

| | |
|---|---|
| Project | `airy-decorator-361514` |
| Region | `asia-southeast1` |
| Service | `invoiceloop` |
| Revision | `invoiceloop-00002-tnk` |
| Image | `…/cloud-run-source-deploy/invoiceloop@sha256:343761e2…c72b1bdc` |
| URL | https://invoiceloop-478275522139.asia-southeast1.run.app |
| 别名 URL | https://invoiceloop-h6ff2yrz2a-as.a.run.app |
| 首次部署 | 2026-08-07T11:17:51Z |
| Smoke | 2026-08-07T11:32:42Z |

构建走 Cloud Build(`gcloud run deploy --source .`),镜像进 Artifact Registry。

## 文件

| 文件 | 内容 |
|---|---|
| `deployment.json` | project / revision / image digest / env / ingress |
| `iam_policy.json` | `allUsers` → `roles/run.invoker` |
| `remote_smoke.txt` | 远端探针 / 读路径 / 九条写路径的实测状态码 |

## 安全姿态

`allUsers` 可调用 —— **这只有在只读的前提下成立**。
`INVOICELOOP_READ_ONLY=1` 在 revision 的 env 里(见 `deployment.json`),
远端实测九条写入路由全部 403(见 `remote_smoke.txt`),页面顶部有横幅说明。

裁决账本是「某个人看过并判了」的证词。公网可写等于允许伪造,所以公开实例
一个字节都不许写。真实 HITL 只在本地可写运行的工作台上进行。

## 一个平台行为,记下来

**`/healthz` 在 Cloud Run 外网侧不可用。** Google 前端在请求到达 Cloud Run
之前就把它吞掉,回自己的 404 页(响应头里没有 `server: Google Frontend`,
容器访问日志里也看不到这条请求)。同一部署下 `/healthzz` `/_health`
`/livez` `/nope` 全部进到应用里由我们 404 —— 所以不是路由问题,是这个
路径被平台占了。

对外探针因此改挂 `/_health`。容器内 `HEALTHCHECK` 打 `127.0.0.1`,不经过
前端,`/healthz` 照常有效,两条都留着。

## 这份取证证明了什么,以及**没有**证明什么

**证明了:** 强制项「Google Cloud 基础设施服务」有实物 —— 有 revision、
有 image digest、有可访问 URL、有远端 smoke。

**没有证明:**
- 不是持久化。Cloud Run 实例临时,文件系统随回收消失。
- 不是真的 HITL。只读实例上没有人能裁决任何东西。
- 不让产品变好。信任内核是确定性 Python,本地跑得一模一样。

对外只能说「合成演示部署在 Cloud Run」。

## 复算

```bash
gcloud run services describe invoiceloop \
  --project=airy-decorator-361514 --region=asia-southeast1
curl -fsS https://invoiceloop-478275522139.asia-southeast1.run.app/_health
curl -o /dev/null -w '%{http_code}\n' -X POST \
  https://invoiceloop-478275522139.asia-southeast1.run.app/decide   # 期望 403
```
