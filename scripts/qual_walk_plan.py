#!/usr/bin/env python3
"""从资格集 200 份里抽 20 份行走集(最小哈希,只取工作台真会排队的文档)。

零 API:只读冻结臂 D、input manifest 与 qualification decision。资格结果即使
是 FAIL 也可继续独立的人类问责行走,但名单会把 FAIL 与 promotion denied 原样绑定,
不能让后来的 ADK 结果反向改写自动放行资格。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop.heldout import doc_ids_line_digest  # noqa: E402
from invoiceloop.release_profile import parse_release_profile  # noqa: E402
from invoiceloop.snapshot import _code_revision  # noqa: E402

DEFAULT_ROUND = "qual-adk-walk-v2-2026-08-23"
DEFAULT_SALT = "invoiceloop-qual-adk-walk-v2"
DEFAULT_ROUTING = (REPO / "docs/evidence/qual-narrow-v2-2026-08-23/"
                   "source-har-0023/routing_report.json")
DEFAULT_INPUT_MANIFEST = (REPO / "docs/evidence/qual-narrow-v2-2026-08-23/"
                          "source-har-0023/input_manifest.json")
DEFAULT_DECISION = (REPO / "docs/evidence/qual-narrow-v2-2026-08-23/"
                    "decision/qualification_decision.json")
AUTO = ("auto_accept", "auto_absent")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"不可读 JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须是 object:{path}")
    return value


def repo_rel(path: Path) -> str:
    path = Path(path).resolve()
    try:
        return str(path.relative_to(REPO.resolve()))
    except ValueError:
        return str(path)


def require_committed(paths: list[Path]) -> None:
    """Inputs that license a walk list must be tracked and byte-equal to HEAD."""
    failures = []
    for path in paths:
        path = Path(path).resolve()
        try:
            rel = path.relative_to(REPO.resolve())
        except ValueError:
            failures.append(f"仓库外:{path}")
            continue
        tracked = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "--error-unmatch", "--", str(rel)],
            capture_output=True, timeout=5)
        clean = subprocess.run(
            ["git", "-C", str(REPO), "diff", "--quiet", "HEAD", "--", str(rel)],
            capture_output=True, timeout=5)
        if tracked.returncode != 0 or clean.returncode != 0:
            failures.append(str(rel))
    if failures:
        raise ValueError(f"行走规划输入必须已提交且等于 HEAD:{failures}")


def qualification_binding(routing_path: Path, input_manifest_path: Path,
                          decision_path: Path) -> dict:
    """Verify that the walk source is exactly the source decided by qualification."""
    report = _json(routing_path)
    manifest = _json(input_manifest_path)
    decision = _json(decision_path)
    integrity = decision.get("integrity") or {}
    qualification = decision.get("qualification") or {}
    status = qualification.get("status")
    promotion = qualification.get("promotion")
    if integrity.get("passed") is not True or status not in ("pass", "fail"):
        raise ValueError("qualification decision 不完整或 invalid,不能抽行走集")
    if ((status == "pass" and promotion != "allowed")
            or (status == "fail" and promotion != "denied")):
        raise ValueError("qualification status 与 promotion 自相矛盾")
    expected = ((integrity.get("source_hashes") or {})
                .get("har_0023_routing_report_sha256"))
    if not expected or _sha(routing_path) != expected:
        raise ValueError("行走 routing report 不是 qualification decision 裁定的 D 臂")
    if report.get("harness_id") != "HAR-0023" or \
            manifest.get("harness_id") != "HAR-0023":
        raise ValueError("行走来源不是 HAR-0023")
    route_docs = sorted({str(row.get("doc_id"))
                         for row in (report.get("routes") or [])})
    input_docs = sorted(str(row.get("doc_id"))
                        for row in (manifest.get("docs") or []))
    if len(route_docs) != 200 or route_docs != input_docs:
        raise ValueError("D 臂 routing 与 input manifest 的 200 份文档不一致")
    return {
        "qualification_round": decision.get("round"),
        "qualification_status": status,
        "qualification_promotion": promotion,
        "qualification_decision_sha256": _sha(decision_path),
        "source_routing_sha256": _sha(routing_path),
        "source_input_manifest_sha256": _sha(input_manifest_path),
    }


def queue_slots(routes: list[dict], policy: dict) -> list[tuple[str, str]]:
    """工作台**真的会排进队列**的 (doc_id, field)。

    不能用「任意非 auto 路由」:HAR-0023 带 release_profile,工作台走的是
    workbench._walk_release_profile —— 只有 gating 字段的待裁决槽和 QA 探针
    进队列。按非 auto 抽,会抽到打开之后队列是空的文档。
    这里复用同一个谓词,改了那边这里必须跟着改。

    行走结果分析的完整性闸也吃这个函数:「该走的槽走完了没有」与「该抽哪些
    文档」必须是同一个定义,两处各写一遍迟早会分叉。
    """
    profile = parse_release_profile(policy or {})
    gate = profile["fields"] if profile else None
    out = set()
    for row in routes:
        codes = [str(c) for c in (row.get("reason_codes") or [])]
        is_qa = any(c.startswith("QA_SAMPLE") for c in codes)
        in_q = row.get("in_human_queue", row.get("requires_adjudication"))
        if in_q is None:
            in_q = row.get("route") not in AUTO
        if is_qa or (in_q and (gate is None or row["field"] in gate)):
            out.add((str(row["doc_id"]), str(row["field"])))
    return sorted(out)


def eligible(routes: list[dict], policy: dict) -> list[str]:
    """队列槽 ≥1 的文档。"""
    return sorted({doc for doc, _ in queue_slots(routes, policy)})


def pick(doc_ids: list[str], n: int, *, salt: str = DEFAULT_SALT) -> list[str]:
    if len(doc_ids) < n:
        raise SystemExit(f"合格文档只有 {len(doc_ids)} 份,不足 {n}")
    if not salt:
        raise SystemExit("抽样 salt 不得为空")
    ranked = sorted(doc_ids, key=lambda d: hashlib.sha256(
        f"{salt}|{d}".encode("utf-8")).hexdigest())
    return sorted(ranked[:n])


def build_payload(*, routing_path: Path, input_manifest_path: Path,
                  decision_path: Path, n: int, round_name: str,
                  salt: str, planner_code_revision: str) -> dict:
    binding = qualification_binding(
        routing_path, input_manifest_path, decision_path)
    report = _json(routing_path)
    pool = eligible(report["routes"], report.get("policy") or {})
    ids = pick(pool, n, salt=salt)
    return {
        "round": round_name,
        "n": n,
        "qualification_round": binding["qualification_round"],
        "qualification_status": binding["qualification_status"],
        "qualification_promotion": binding["qualification_promotion"],
        "qualification_decision": repo_rel(decision_path),
        "qualification_decision_sha256":
            binding["qualification_decision_sha256"],
        "source": repo_rel(routing_path),
        "source_sha256": binding["source_routing_sha256"],
        "source_input_manifest": repo_rel(input_manifest_path),
        "source_input_manifest_sha256":
            binding["source_input_manifest_sha256"],
        "eligibility": "臂 D(HAR-0023)下 workbench._walk_release_profile "
                       "会排进队列的槽 ≥1(gating 字段待裁决 或 QA 探针)",
        "eligible_n": len(pool),
        "eligible_sha256": doc_ids_line_digest(pool),
        "salt": salt,
        "sampling": f"min-hash:sha256(「{salt}|」+ doc_id) 升序取前 {n}",
        "doc_ids": ids,
        "doc_ids_sha256": hashlib.sha256(
            "\n".join(ids).encode("utf-8")).hexdigest(),
        "planner_code_revision": planner_code_revision,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--routing-report", type=Path, default=DEFAULT_ROUTING)
    ap.add_argument("--input-manifest", type=Path,
                    default=DEFAULT_INPUT_MANIFEST)
    ap.add_argument("--qualification-decision", type=Path,
                    default=DEFAULT_DECISION)
    ap.add_argument("--round", dest="round_name", default=DEFAULT_ROUND)
    ap.add_argument("--salt", default=DEFAULT_SALT)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()
    revision = _code_revision(REPO)
    if revision is None or revision.endswith(("-dirty", "-unknown-worktree")):
        raise SystemExit(
            f"fatal: 行走名单只能从干净 commit 生成,当前={revision}")
    try:
        require_committed([
            args.routing_report, args.input_manifest,
            args.qualification_decision])
        payload = build_payload(
            routing_path=args.routing_report,
            input_manifest_path=args.input_manifest,
            decision_path=args.qualification_decision,
            n=args.n, round_name=args.round_name, salt=args.salt,
            planner_code_revision=revision)
    except ValueError as exc:
        raise SystemExit(f"fatal: {exc}") from exc
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps({k: payload[k] for k in
                      ("qualification_status", "qualification_promotion",
                       "eligible_n", "n", "eligible_sha256", "doc_ids_sha256")},
                     ensure_ascii=False, indent=1))
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
