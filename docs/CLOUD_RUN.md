# Cloud Run 部署(参赛 Google Cloud 服务)

本路径**不依赖** Gemini / ADK。Antigravity 的 agents 接线与这里零重叠。

## 解决什么

| 强制项 | 本路径给出的证据 |
|---|---|
| Google Cloud 服务 | Cloud Run 托管 URL |
| 可演示的在线工作台 | 镜像内预置 `demo` workspace,冷启动即可开队列 |
| 可选持久化 | `GCS_WORKSPACE_URI=gs://…` 拉/推 `workspace.tar.gz` |

## 本地验镜像

```bash
docker build -t invoiceloop:local .
docker run --rm -p 8080:8080 invoiceloop:local
curl -fsS http://127.0.0.1:8080/healthz
# 浏览器打开 http://127.0.0.1:8080/queue
```

## 部署

```bash
# 一次
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

./scripts/deploy_cloud_run.sh
# 或
PROJECT=… REGION=asia-southeast1 ./scripts/deploy_cloud_run.sh
```

输出一行 `https://….run.app` —— 录视频时打开即 Cloud 证明镜头。

## 工作台绑定

- 默认 CLI:`--host 127.0.0.1`(评委本机 loopback,不变)
- 容器入口:`--host 0.0.0.0 --port $PORT`,并默认 `--allowed-host .run.app`
- 探针:`GET /healthz`(先于 Host 闸,不跑 `doctor`)

## GCS(可选)

```bash
pip install '.[cloud]'
python3 -m invoiceloop cloud push --uri gs://BUCKET/invoiceloop --src /path/to/ws
GCS_WORKSPACE_URI=gs://BUCKET/invoiceloop ./scripts/deploy_cloud_run.sh
```

入口在启动时 `cloud pull`;缺对象则回退镜像内 demo。缺 SDK 时 pull/push **显式失败**,不装哑巴成功。

## 与 Dockerfile 旧稿的差别

评委/返工清单里批过的三处,本文件对应修复:

1. **demo-ws 进镜像** —— `RUN python3 -m invoiceloop demo --out /data/demo-ws`
2. **尊重 `PORT`** —— 入口读 Cloud Run 注入的 `PORT`(默认 8080)
3. **healthcheck 不依赖校准档案** —— `curl /healthz`,不跑 `doctor`
