#!/usr/bin/env bash
# 把本仓库部署到 Cloud Run(托管 URL = 参赛「Google Cloud 服务」镜头)。
#
# 前置:gcloud auth / 已选 project(需开计费)
#   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
#
# 用法:
#   ./scripts/deploy_cloud_run.sh
#   PROJECT=my-proj REGION=asia-southeast1 SERVICE=invoiceloop ./scripts/deploy_cloud_run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-invoiceloop}"

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "需要 PROJECT=... 或 gcloud config set project" >&2
  exit 1
fi

echo "deploy: project=${PROJECT} region=${REGION} service=${SERVICE}"

# 公开实例只读 —— --allow-unauthenticated 只有在这个前提下才是安全的
ENV_VARS="PYTHONUNBUFFERED=1,INVOICELOOP_READ_ONLY=1"

gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --source="${ROOT}" \
  --allow-unauthenticated \
  --port=8080 \
  --memory=1Gi \
  --cpu=1 \
  --set-env-vars="${ENV_VARS}" \
  --quiet

gcloud run services describe "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --format='value(status.url)'
