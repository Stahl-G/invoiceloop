#!/bin/sh
# Cloud Run / Docker 入口:可选从 GCS 拉 workspace → 缺则内嵌 demo → 绑 0.0.0.0:$PORT
set -eu

WS="${INVOICELOOP_WORKSPACE:-/data/demo-ws}"
PORT="${PORT:-8080}"

if [ -n "${GCS_WORKSPACE_URI:-}" ]; then
  echo "cloud_entrypoint: pull ${GCS_WORKSPACE_URI} → ${WS}"
  python3 -m invoiceloop cloud pull --uri "$GCS_WORKSPACE_URI" --dest "$WS" || true
fi

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
exec python3 -m invoiceloop workbench \
  --workspace "$WS" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --allowed-host .run.app \
  $EXTRA_HOSTS
