#!/bin/sh
# Cloud Run / Docker 入口:镜像内烤好的 demo workspace → 绑 0.0.0.0:$PORT
#
# 没有 GCS 拉取这一步。演示 workspace 在 `docker build` 时就 `invoiceloop demo`
# 烤进镜像了,运行期不需要取任何外部数据 —— 于是也就没有「拉取失败了怎么办」
# 这个问题。上一版是 `... || true`:认证失败、SDK 缺失、包损坏全被吞掉,
# 然后静默拿 demo 数据顶替真数据。那正是这个项目存在的目的所要防的事。
set -eu

WS="${INVOICELOOP_WORKSPACE:-/data/demo-ws}"
PORT="${PORT:-8080}"

if [ ! -f "${WS}/runs/current.json" ]; then
  echo "cloud_entrypoint: baking demo workspace at ${WS}"
  # demo 要求目录不存在或为空
  if [ -d "$WS" ] && [ -n "$(ls -A "$WS" 2>/dev/null || true)" ]; then
    echo "cloud_entrypoint: ${WS} 非空且无 current.json —— 拒绝覆盖" >&2
    exit 1
  fi
  python3 -m invoiceloop demo --out "$WS"
fi

EXTRA_HOSTS=""
if [ -n "${INVOICELOOP_ALLOWED_HOSTS:-}" ]; then
  # shell 拆成多次 --allowed-host
  OLD_IFS=$IFS
  IFS=,
  for h in $INVOICELOOP_ALLOWED_HOSTS; do
    h=$(echo "$h" | tr -d ' ')
    [ -n "$h" ] || continue
    EXTRA_HOSTS="$EXTRA_HOSTS --allowed-host $h"
  done
  IFS=$OLD_IFS
fi

# 默认允许 Cloud Run 后缀;可用环境变量覆盖/追加
# 只读:裁决账本是人的证词,公开实例不许写(INVOICELOOP_READ_ONLY=0 可关,
# 但那只在私有鉴权部署下才成立)
# 写成 if 而不是 `[ ... ] && VAR=`:后者在默认路径(条件为假)下让整条语句
# 返回 1。实测 dash/bash 都不会因此退出(POSIX 的 -e 豁免 AND-OR 列表的
# 非末位命令),但读的人得先想一遍才敢确定 —— if 不用想。
READ_ONLY="--read-only"
if [ "${INVOICELOOP_READ_ONLY:-1}" = "0" ]; then
  READ_ONLY=""
fi

exec python3 -m invoiceloop workbench \
  --workspace "$WS" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --allowed-host .run.app \
  $READ_ONLY \
  $EXTRA_HOSTS
