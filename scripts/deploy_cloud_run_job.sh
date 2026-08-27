#!/usr/bin/env bash
# 部署并执行 Arm U 的 Cloud Run Job(与公开只读工作台同一镜像、不同入口)。
#
# 前置:gcloud auth login + application-default、已选计费项目
# 用法:
#   ./scripts/deploy_cloud_run_job.sh
#   PROJECT=… REGION=… BUCKET=… JOB=invoiceloop-unattended ./scripts/deploy_cloud_run_job.sh
# 产物:一次 Job 执行 + GCS 工件 + 本地 docs/evidence/cloud_run_job_<date>/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${REGION:-asia-southeast1}"
JOB="${JOB:-invoiceloop-unattended}"
BUCKET="${BUCKET:-invoiceloop-${PROJECT}-arm-u}"

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "需要 PROJECT=… 或 gcloud config set project" >&2
  exit 1
fi
echo "job: project=${PROJECT} region=${REGION} job=${JOB} bucket=${BUCKET}"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com storage.googleapis.com \
  aiplatform.googleapis.com --project="${PROJECT}" --quiet

# 桶(已存在则跳过)+ Job SA 的写权 + Vertex 调用权
if ! gcloud storage buckets describe "gs://${BUCKET}" --project="${PROJECT}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET}" --project="${PROJECT}" --location="${REGION}"
fi
SA="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA}" --role="roles/storage.objectAdmin" --quiet >/dev/null
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA}" --role="roles/aiplatform.user" \
  --condition=None --quiet >/dev/null || \
  echo "warn: aiplatform.user 授予失败 —— 若 SA 已有权限可忽略,否则 Job 内模型调用会 403" >&2

# Job 与公开服务同镜像、不同命令;IAM 私有(不带 --allow-unauthenticated,Job 本就无 URL)
if gcloud run jobs describe "${JOB}" --project="${PROJECT}" --region="${REGION}" >/dev/null 2>&1; then
  gcloud run jobs update "${JOB}" --project="${PROJECT}" --region="${REGION}" \
    --source="${ROOT}" --command=bash --args=scripts/run_unattended_job.sh \
    --memory=2Gi --cpu=1 --task-timeout=30m \
    --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=global,BUCKET=${BUCKET}" \
    --quiet
else
  gcloud run jobs create "${JOB}" --project="${PROJECT}" --region="${REGION}" \
    --source="${ROOT}" --command=bash --args=scripts/run_unattended_job.sh \
    --memory=2Gi --cpu=1 --task-timeout=30m \
    --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=global,BUCKET=${BUCKET}" \
    --quiet
fi

echo "job: execute and wait"
gcloud run jobs execute "${JOB}" --project="${PROJECT}" --region="${REGION}" --wait --quiet

EV="docs/evidence/cloud_run_job_$(date -u +%Y-%m-%d)"
mkdir -p "${EV}"
gcloud run jobs describe "${JOB}" --project="${PROJECT}" --region="${REGION}" \
  --format=json > "${EV}/job.json"
EXEC="$(gcloud run jobs executions list --project="${PROJECT}" --region="${REGION}" --limit=1 --format='value(metadata.name)')"
gcloud run jobs executions describe "${EXEC}" --project="${PROJECT}" --region="${REGION}" \
  --format=json > "${EV}/execution.json"
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=${JOB}" \
  --project="${PROJECT}" --limit=200 --format='value(textPayload)' > "${EV}/execution_log.txt" || true
gcloud storage ls "gs://${BUCKET}/arm-u-runs/**" > "${EV}/gcs_listing.txt" || true

echo "job: evidence under ${EV}/ —— 核对 execution.json 的 succeeded 条数与 gcs_listing 的工件"
