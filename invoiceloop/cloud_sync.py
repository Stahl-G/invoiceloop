"""可选 GCS 工作区同步 —— Cloud Run 持久化 demo/workspace(零强制依赖)。

缺 `google-cloud-storage` 时命令明确失败,不静默跳过(宪章四)。
用法见 `docs/CLOUD_RUN.md`。
"""

from __future__ import annotations

import json
import tarfile
import tempfile
from pathlib import Path


def _client():
    try:
        from google.cloud import storage  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "缺 google-cloud-storage —— pip install 'invoiceloop[cloud]'"
        ) from exc
    return storage.Client()


def _parse_gs(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise SystemExit(f"需要 gs://bucket/prefix,得到 {uri!r}")
    rest = uri[len("gs://"):]
    bucket, _, prefix = rest.partition("/")
    if not bucket:
        raise SystemExit(f"GCS URI 缺 bucket:{uri!r}")
    return bucket, prefix.rstrip("/")


def pull(uri: str, dest: Path) -> dict:
    """从 `gs://bucket/prefix/workspace.tar.gz` 解开到 dest。"""
    bucket_name, prefix = _parse_gs(uri)
    blob_name = f"{prefix}/workspace.tar.gz" if prefix else "workspace.tar.gz"
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    client = _client()
    blob = client.bucket(bucket_name).blob(blob_name)
    if not blob.exists():
        return {"ok": False, "reason": "missing", "uri": f"gs://{bucket_name}/{blob_name}"}
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp:
        blob.download_to_filename(tmp.name)
        with tarfile.open(tmp.name, "r:gz") as tar:
            tar.extractall(dest)
    return {"ok": True, "uri": f"gs://{bucket_name}/{blob_name}", "dest": str(dest)}


def push(uri: str, src: Path) -> dict:
    """把 src 打成 tar.gz 推到 `gs://bucket/prefix/workspace.tar.gz`。"""
    bucket_name, prefix = _parse_gs(uri)
    blob_name = f"{prefix}/workspace.tar.gz" if prefix else "workspace.tar.gz"
    src = Path(src)
    if not src.is_dir():
        raise SystemExit(f"workspace 不存在:{src}")
    client = _client()
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp:
        with tarfile.open(tmp.name, "w:gz") as tar:
            tar.add(src, arcname=".")
        blob = client.bucket(bucket_name).blob(blob_name)
        blob.upload_from_filename(tmp.name)
    return {"ok": True, "uri": f"gs://{bucket_name}/{blob_name}", "src": str(src)}


def cmd_cloud(args) -> int:
    if args.cloud_command == "pull":
        print(json.dumps(pull(args.uri, args.dest), ensure_ascii=False, indent=1))
        return 0
    if args.cloud_command == "push":
        print(json.dumps(push(args.uri, args.src), ensure_ascii=False, indent=1))
        return 0
    raise SystemExit(f"未知 cloud 子命令:{args.cloud_command}")
