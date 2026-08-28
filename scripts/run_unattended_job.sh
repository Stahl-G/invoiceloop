#!/usr/bin/env bash
# Arm U 的 Cloud Run Job 入口:demo 工作区 → 清账本 → 无人值守臂 → 上传 GCS。
#
# 与公开 .run.app 工作台的根本区别:这里是 IAM 私有的 Job,没有 HTTP 面;
# 跑完即回收,所以工件必须在进程结束前上传 —— 上传失败 = 退出码 1(阻断,
# 不许假装成功)。批准是否发生由策略与 approver 决定,与本脚本的退出码无关:
# 退出码 0 的含义是「这一趟完整跑完且证据已落桶」,不是「单据被放行」。
#
# 环境变量(由 deploy_cloud_run_job.sh 注入):
#   GOOGLE_CLOUD_PROJECT  GCP 项目(Job SA 的 Vertex 调用归属)
#   GOOGLE_CLOUD_LOCATION Vertex 位置(global)
#   BUCKET                工件桶(gs://…);必须设置 —— 不上传的 Job 违反本臂纪律
set -euo pipefail

WS=/data/job-ws
RUN_DIR="${WS}/runs/run-0001"

if [[ -z "${BUCKET:-}" || -z "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
  echo "fatal: BUCKET and GOOGLE_CLOUD_PROJECT must be injected by the Job environment" >&2
  exit 1
fi

echo "== job: build fresh demo workspace (zero API) =="
rm -rf "${WS}"
python3 -m invoiceloop demo --out "${WS}"

echo "== job: reset ledgers to a clean review state =="
: > "${RUN_DIR}/adjudication_ledger.jsonl"
: > "${RUN_DIR}/approve_ledger.jsonl"

echo "== job: run the unattended arm =="
# decided_at 由作业注入(触发即操作)—— 工件不读墙钟
DECIDED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
set +e
python3 -m invoiceloop unattended \
  --run "${RUN_DIR}" \
  --decided-at "${DECIDED_AT}"
UNATTENDED_RC=$?
set -e

echo "== job: upload artifacts to ${BUCKET} =="
# google-cloud-storage 不在镜像依赖里;用 ADC token + JSON API 直传(仅标准库+requests)
# 上传根是**整个工作区**而不只是 run 目录:agent_calls(模型调用录音,
# 零 API 重放的依据)、input/pdfs(源单据)、raw(DWS 存盘响应)、ocr
# 都在工作区层 —— 只传 run 目录会让 artifact_registry.json 指向桶里
# 不存在的文件,一份断链的证据清单比不上传更糟。
python3 - "${WS}" "${BUCKET}" "${UNATTENDED_RC}" <<'PYEOF'
import json, sys, time
from pathlib import Path
import requests

ws, bucket = Path(sys.argv[1]), sys.argv[2].removeprefix("gs://")
unattended_rc = int(sys.argv[3])
# Cloud Run 的 SA token 从元数据服务器来;本地 docker 验证时可 GOOGLE_OAUTH_ACCESS_TOKEN 注入
token = None
try:
    r = requests.get(
        "http://metadata.google.internal/computeMetadata/v1/instance/"
        "service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"}, timeout=5)
    r.raise_for_status()
    token = r.json()["access_token"]
except Exception:
    pass
import os
token = token or os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
if not token:
    raise SystemExit("fatal: no ADC token — artifacts cannot reach the bucket; blocking (see script header)")

stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
prefix = f"arm-u-runs/{stamp}"
uploaded = []
for path in sorted(ws.rglob("*")):
    rel = path.relative_to(ws).as_posix()
    if not path.is_file():
        continue
    # 渲染图体积大且可从 PDF 重建;锁文件与字节码不是证据 —— 都不上传
    if any(part in ("pages", "crops", "__pycache__") for part in Path(rel).parts) \
            or rel.endswith(".lock"):
        continue
    obj = f"{prefix}/{rel}"
    url = (f"https://storage.googleapis.com/upload/storage/v1/b/"
           f"{bucket}/o?uploadType=media&name={obj}")
    resp = requests.post(
        url, data=path.read_bytes(), timeout=120,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/octet-stream"})
    if resp.status_code not in (200, 201):
        raise SystemExit(f"fatal: upload failed for {obj}: {resp.status_code} {resp.text[:200]}")
    uploaded.append(obj)
print(json.dumps({"bucket": bucket, "prefix": prefix, "files": len(uploaded),
                  "unattended_rc": int(sys.argv[3]) if len(sys.argv) > 3 else None},
                 ensure_ascii=False))
PYEOF

if [[ ${UNATTENDED_RC} -ne 0 ]]; then
  echo "unattended arm failed (rc=${UNATTENDED_RC}); artifacts uploaded above" >&2
  exit "${UNATTENDED_RC}"
fi
echo "== job: done (run complete and evidenced; approvals are the policy's call) =="
