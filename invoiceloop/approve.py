"""Document-level approval: the one act a machine may never perform.

2026-08-09.  Slot-level adjudication answers *is this value trustworthy*, and a
routing policy is allowed to answer it on a person's behalf because a wrong
auto-accept is caught by QA sampling.  Whether an invoice may be posted to the
ledger is a different question, and nothing in the deterministic pipeline is
entitled to answer it: the best status automation can reach is
``ready_for_approval``.

在此之前 `deliverable.json` 里 `released` 是**机器可达**的 —— 十个槽全被
策略放行的文档从来没人看过一眼,一样会走到 released,而 README 把它写成
「downstream AP/ERP can post it」。那等于让路由策略的松紧决定记账授权的松紧。
Northstar 评审点的就是这一处,它是对的。

本模块只做一件事:把一条署名批准追加进 `approve_ledger.jsonl`,并绑死批准
**当时**的文档摘要。摘要变了(值被改、槽被重裁)批准自动失效,人得重批 ——
否则「批准」会退化成一次性通行证,批完再改值,改动就搭着上一次签名出门。

纪律与裁决账本一致:只追加不覆写、进程内锁 + flock、fsync、时间由调用方
注入(工件不读墙钟)。失效的批准**留在账本里**:谁在什么内容上批过字是
审计轨迹,不是可以清理的垃圾。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover —— 非 POSIX 平台退化为进程内锁
    fcntl = None

from .snapshot import load_or_derive_snapshot

_APPEND_LOCK = threading.Lock()

#: 批准账本文件名。它是 run 工件,与裁决账本并列,不进 review_snapshot ——
#: 快照钉的是**被复核的证据**,批准是证据之后发生的事。
LEDGER_NAME = "approve_ledger.jsonl"

#: 可以批准的文档状态。pending / blocked 不许批:前者还有槽没处置,
#: 后者的完整性已经破了(宪章四:没查过不等于通过)。
APPROVABLE = ("ready_for_approval", "ready_for_approval_with_caveats")


def document_digest(doc_entry: dict) -> str:
    """批准绑定的内容摘要:该文档每个槽的 (值, 状态, 来源)。

    只取这三样是刻意的 —— 它们正好是「这张单要入账的东西」。文档级
    caveats 也进摘要:机检没跑完这件事若在批准后才出现,旧批准同样应失效。
    """
    payload = {
        "fields": {
            name: [entry.get("value"), entry.get("status"), entry.get("source")]
            for name, entry in sorted((doc_entry.get("fields") or {}).items())
        },
        "release_caveats": sorted(doc_entry.get("release_caveats") or []),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_approvals(run_dir: Path) -> list[dict]:
    """全部批准事件,按追加顺序。文件不存在 → 空列表。"""
    path = Path(run_dir) / LEDGER_NAME
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def latest_by_doc(run_dir: Path) -> dict[str, dict]:
    """每份文档最后一条批准。**不判断是否仍然有效** —— 那要拿当下的
    deliverable 摘要比,是 deliver 的事,不是账本的事。"""
    out: dict[str, dict] = {}
    for entry in load_approvals(run_dir):
        out[entry["doc_id"]] = entry
    return out


def append_approval(
    run_dir: Path,
    *,
    doc_id: str,
    approved_by: str,
    rationale: str,
    approved_at: str,
) -> dict:
    """追加一条文档级批准并 fsync。校验失败 → ValueError,一行都不写。"""
    from .deliver import build_deliverable

    run_dir = Path(run_dir)
    if not (approved_by and str(approved_by).strip()):
        raise ValueError(
            "approved_by 不能为空 —— 批准是署名行为,系统不替人签字")
    if not (rationale and str(rationale).strip()):
        raise ValueError(
            "rationale 不能为空 —— 批准理由是审计轨迹的一部分,"
            "「看过了」也要自己写下来")
    if not (approved_at and str(approved_at).strip()):
        raise ValueError("approved_at 不能为空 —— 时间由人给出,不由系统代填")
    approved_by = str(approved_by).strip()
    rationale = str(rationale).strip()
    approved_at = str(approved_at).strip()

    from datetime import datetime

    try:
        datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"approved_at {approved_at!r} 不是 ISO 8601 时间 —— "
            f"账本里的时间必须可机读") from None

    manifest = json.loads(
        (run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    if doc_id not in set(manifest.get("docs", [])):
        raise ValueError(
            f"doc {doc_id!r} 不在本次 run 的文档集合里 —— 批准必须指向 run 内文档")

    deliverable = build_deliverable(run_dir)
    doc_entry = deliverable["docs"].get(doc_id)
    if doc_entry is None:
        raise ValueError(f"doc {doc_id!r} 不在本次交付投影里")
    status = doc_entry["status"]
    if status.startswith("approved_for_export"):
        # 已批准且未失效 —— 再批一次没有新信息,但也不是错误;
        # 让调用方决定,这里如实拒绝重复写入。
        raise ValueError(f"doc {doc_id!r} 已经是 {status},内容未变,无需重批")
    if status not in APPROVABLE:
        if status == "blocked":
            raise ValueError(
                f"doc {doc_id!r} 是 blocked —— 完整性已经破了,"
                f"先查清再谈批准;系统不接受在 blocked 单据上签字")
        raise ValueError(
            f"doc {doc_id!r} 还有槽没处置(status={status})—— "
            f"先把人工队列走完再批准整单")

    snapshot_id = load_or_derive_snapshot(run_dir)["review_snapshot_id"]
    # 与 append_adjudication 同一道闸:批准要绑在**没被动过**的证据上。
    # 少了它,run 之后改一份工件再批准,签名就落在一个名存实亡的快照上了。
    if (run_dir / "review_snapshot.json").exists():
        from .snapshot import compute_review_snapshot

        current = compute_review_snapshot(run_dir)["review_snapshot_id"]
        if current != snapshot_id:
            raise ValueError(
                "run 目录内工件与 review_snapshot.json 不符 —— 有工件在 run "
                "之后被改动过。先比对 components 查清哪份被动了,再批准;"
                "系统不在被动过的证据上记批准")
    digest = document_digest(doc_entry)

    with _APPEND_LOCK:
        lock_fh = (run_dir / "approve_ledger.lock").open("a+")
        try:
            if fcntl is not None:
                fcntl.flock(lock_fh, fcntl.LOCK_EX)
            seq = len(load_approvals(run_dir)) + 1
            entry = {
                "seq": seq,
                "approval_id": f"AP-{seq:04d}",
                "review_snapshot_id": snapshot_id,
                "doc_id": doc_id,
                "document_digest": digest,
                "status_at_approval": status,
                "release_caveats": sorted(
                    doc_entry.get("release_caveats") or []),
                # 这次署名替多少条策略处置背书 —— 写进账本,事后查得出
                # 「批的时候他知不知道有两个关键字段没人看过」
                "policy_disposed_fields": sorted(
                    doc_entry.get("policy_disposed_fields") or []),
                "tier1_policy_disposed_fields": sorted(
                    doc_entry.get("tier1_policy_disposed_fields") or []),
                "approved_by": approved_by,
                "rationale": rationale,
                "approved_at": approved_at,
            }
            with (run_dir / LEDGER_NAME).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return entry
        finally:
            if fcntl is not None:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
            lock_fh.close()
