"""The held-out execution driver — docs/HELDOUT.md in runnable form.

Discipline:
- The document list is deterministic and reproducible, and is **written to disk
  before any call** (pre-registration: answers precede scoring).
- Keys come only from `DWS_API_KEYS` (comma separated) or
  `~/.config/invoiceloop/heldout.keys`, and are never written into the repository
  or the evidence archive.
- Storage discipline matches dws-derisk extract.py: raw response first,
  interpretation second; a 4xx is evidence too.
- Resumable: a (doc, mode) already stored with status 200 is skipped.
- Budget breaker: usage cost accumulates from each response, and the run stops on
  crossing the line (default 6000).
- On an exhausted balance (401/402/403) it rotates to the next key; 429 backs off
  and retries.

The workspace is self-contained: `raw/` for new responses plus a `data` symlink to
the calibration archive. Point `INVOICELOOP_DWS_DERISK` at the workspace and the
pipeline runs unchanged.
"""

from __future__ import annotations

import json
import os
import sys
import time
from functools import lru_cache
from pathlib import Path

from .ocr import derisk_root

HELDOUT_N = 100
POOL_MIN_FIELDS = 4  # 与 run_batch.sample 同门槛:标注够多才值得一次调用
KEY_FILE = Path("~/.config/invoiceloop/heldout.keys").expanduser()


def _derisk_imports():
    """校准档案的 run_batch / schema / extract(只读复用,不搬)。"""
    sys.path.insert(0, str(derisk_root()))
    import run_batch  # type: ignore
    import schema  # type: ignore
    import extract  # type: ignore
    return run_batch, schema, extract


def calibration_ids() -> set[str]:
    run_batch, _, _ = _derisk_imports()
    return {p.stem for p in run_batch.sample(160)}


@lru_cache(maxsize=1)
def heldout_pool() -> tuple[str, ...]:
    """有 ≥4 个记分字段标注、不在校准 160 里的文档,排序固定。

    全量扫描 5,680 份标注,进程内缓存一次。
    """
    root = derisk_root()
    ann = root / "data" / "docile" / "annotations"
    pdfs = root / "data" / "docile" / "pdfs"
    wanted = {
        "document_id", "date_issue", "date_due", "vendor_name", "vendor_tax_id",
        "customer_billing_name", "amount_total_net", "amount_total_tax",
        "amount_total_gross", "amount_due",
    }
    calibration = calibration_ids()
    pool = []
    for path in sorted(ann.glob("*.json")):
        if path.stem in calibration or not (pdfs / f"{path.stem}.pdf").exists():
            continue
        payload = json.loads(path.read_text())
        present = {x.get("fieldtype") for x in payload.get("field_extractions") or []}
        if len(present & wanted) >= POOL_MIN_FIELDS:
            pool.append(path.stem)
    return tuple(pool)


def heldout_list(n: int = HELDOUT_N) -> list[str]:
    """等距抽样:步长 = pool/n,索引 int(i*step),确定性。"""
    pool = heldout_pool()
    if len(pool) < n:
        raise RuntimeError(f"留出池只有 {len(pool)} 份,不足 {n}")
    step = len(pool) / n
    return [pool[int(i * step)] for i in range(n)]


def prepare_workspace(workspace: Path) -> Path:
    workspace = Path(workspace)
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    link = workspace / "data"
    if not link.exists():
        link.symlink_to(derisk_root() / "data")
    return workspace


def cmd_plan(workspace: Path, n: int = HELDOUT_N) -> list[str]:
    """生成名单并落盘 —— 这一步先于任何 API 调用,落盘即预注册。"""
    workspace = prepare_workspace(workspace)
    ids = heldout_list(n)
    payload = {
        "n": n,
        "pool_size": len(heldout_pool()),
        "pool_min_fields": POOL_MIN_FIELDS,
        "sampling": "sorted pool, equidistant, idx=int(i*pool/n)",
        "doc_ids": ids,
    }
    (workspace / "doc_list.json").write_text(
        json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"pool={payload['pool_size']}  held-out n={n}")
    print(f"名单已落盘:{workspace / 'doc_list.json'} —— 先提交,再调用")
    return ids


# ------------------------------------------------------------------ SEALED

#: 抽样 PRNG 语境。复算旧批必须传当时的 context;
#: 每一批换一个,避免与前几批撞同一随机流。
SEALED_CONTEXTS = {
    "sealed1-v1": "invoiceloop-sealed1-v1",
    "sealed2-v1": "invoiceloop-sealed2-v1",
    "sealed3-v1": "invoiceloop-sealed3-v1",
    "sealed4-v1": "invoiceloop-sealed4-v1",
}
DEFAULT_SEALED_CONTEXT = "sealed4-v1"


def sealed_pool() -> tuple[str, ...]:
    """封箱合格池:heldout_pool 再减 development_exposure_manifest
    全量(高级裁决二:排除一切开发期暴露,不只是两份正式名单)。"""
    manifest_path = (Path(__file__).resolve().parent.parent
                     / "docs" / "development_exposure_manifest.json")
    exposed = {e["doc_id"] for e in json.loads(
        manifest_path.read_text(encoding="utf-8"))["doc_ids"]}
    return tuple(d for d in heldout_pool() if d not in exposed)


def sealed_list(seed_hex: str, n: int = HELDOUT_N, *,
                context: str = DEFAULT_SEALED_CONTEXT) -> list[str]:
    """种子随机抽样(高级裁决一):种子来自代码冻结后才存在的外部随机源
    (drand beacon 指定轮次),开发期间名单不可预知。确定性:同种子同名单。"""
    import random

    if context not in SEALED_CONTEXTS:
        raise ValueError(f"未知封箱语境:{context};允许 {sorted(SEALED_CONTEXTS)}")
    pool = sorted(sealed_pool())
    if len(pool) < n:
        raise RuntimeError(f"封箱合格池只有 {len(pool)} 份,不足 {n}")
    prefix = SEALED_CONTEXTS[context]
    return sorted(random.Random(f"{prefix}|{seed_hex}").sample(pool, n))


def cmd_plan_sealed(workspace: Path, *, seed_hex: str, seed_source: str,
                    n: int = HELDOUT_N,
                    context: str = DEFAULT_SEALED_CONTEXT) -> list[str]:
    """封箱名单落盘。seed_source 记录随机源承诺(协议文档 + 轮次)。"""
    workspace = prepare_workspace(workspace)
    ids = sealed_list(seed_hex, n, context=context)
    payload = {
        "n": n,
        "pool_size": len(sealed_pool()),
        "pool_min_fields": POOL_MIN_FIELDS,
        "exclusion": "docs/development_exposure_manifest.json 全量补集",
        "sampling": "seeded random.sample(sorted pool), "
                    f"seed=sha256 语境 {SEALED_CONTEXTS[context]}",
        "context": context,
        "seed": seed_hex,
        "seed_source": seed_source,
        "doc_ids": ids,
    }
    (workspace / "doc_list.json").write_text(
        json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"pool={payload['pool_size']}  sealed n={n}  "
          f"context={context}  seed={seed_hex[:16]}…")
    print(f"名单已落盘:{workspace / 'doc_list.json'} —— 先提交,再调用")
    return ids


def _load_keys() -> list[str]:
    env = os.environ.get("DWS_API_KEYS", "")
    keys = [k.strip() for k in env.split(",") if k.strip()]
    if not keys and KEY_FILE.exists():
        keys = [ln.strip() for ln in KEY_FILE.read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]
    if not keys:
        raise RuntimeError(
            f"没有可用 key:设 DWS_API_KEYS 或写 {KEY_FILE}(0600)")
    return keys


def _cost_of(record: dict) -> float:
    usage = (record.get("body") or {}).get("usage") or {}
    return float((usage.get("data_extraction_credits") or {}).get("cost") or 0.0)


def cmd_extract(workspace: Path, *, budget: float = 6000.0) -> dict:
    """按名单跑 understand + agentic,断点续跑,余额换 key,预算熔断。"""
    workspace = Path(workspace)
    from .adaptive import is_workspace_adaptive

    if is_workspace_adaptive(workspace):
        raise RuntimeError(
            f"{workspace} 存在 adaptive.json —— sealed/heldout 抽取必须双模式全跑,"
            f"删掉 adaptive.json(及 attempts/)后再 extract;"
            f"见 docs/L1_ADAPTIVE_MEASURED_2026-08-06.md"
        )
    doc_ids = json.loads((workspace / "doc_list.json").read_text())["doc_ids"]
    _, derisk_schema, dws_extract = _derisk_imports()
    dws_extract.RAW_DIR = workspace / "raw"  # 新响应进工作区,不污染校准档案
    schema = derisk_schema.extraction_schema()

    keys = _load_keys()
    key_idx = 0
    os.environ["DWS_API_KEY"] = keys[0]
    spent = 0.0
    done = skipped = failed = 0
    failures: list[dict] = []
    pdfs = derisk_root() / "data" / "docile" / "pdfs"

    tasks = [(d, m) for d in doc_ids for m in ("understand", "agentic")]
    for doc_id, mode in tasks:
        target = workspace / "raw" / f"{doc_id}.{mode}.json"
        if target.exists():
            try:
                if json.loads(target.read_text()).get("http_status") == 200:
                    skipped += 1
                    continue
            except json.JSONDecodeError:
                pass  # 损坏的存盘 = 没跑过,重跑
        record = None
        for attempt in range(6):
            try:
                record = dws_extract.extract(
                    pdfs / f"{doc_id}.pdf", schema, doc_id=doc_id, mode=mode)
            except Exception as exc:  # noqa: BLE001 —— 网络/超时,退避重试
                if attempt < 2:
                    time.sleep(10 * (attempt + 1))
                    continue
                failures.append({"doc_id": doc_id, "mode": mode, "error": repr(exc)})
                break
            status = record.get("http_status")
            if status == 200:
                spent += _cost_of(record)
                done += 1
                break
            if status == 429 and attempt < 2:
                time.sleep(20 * (attempt + 1))
                continue
            if status in (401, 402, 403) and key_idx + 1 < len(keys):
                key_idx += 1
                os.environ["DWS_API_KEY"] = keys[key_idx]
                print(f"  key 耗尽/被拒({status}),换第 {key_idx + 1} 把", flush=True)
                continue
            failures.append({"doc_id": doc_id, "mode": mode, "http_status": status})
            break
        if spent > budget:
            print(f"预算熔断:累计 {spent:.0f} > {budget:.0f},已停。"
                  f"续跑只需重发同一命令(断点续跑)", flush=True)
            break
        if done % 20 == 0 and done:
            print(f"  进度 {done + skipped}/{len(tasks)}  spent≈{spent:.0f}", flush=True)

    summary = {"done": done, "skipped": skipped, "failed": len(failures),
               "failures": failures, "spent_estimate": round(spent, 1),
               "keys_used": key_idx + 1}
    (workspace / "extract_summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary
