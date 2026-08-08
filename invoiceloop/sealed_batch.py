"""Deterministic multi-harness opening for a sealed evidence set.

This is research orchestration, not a second harness authority.  Every arm is
loaded from a committed, digest-pinned plan and is visible only inside one
``pipeline.run`` call.  Product state (the promotion chain and active pointer)
is never changed.

The batch writes ``batch_complete.json`` only after every arm and every paired
invariant has passed.  A scorer must refuse a directory without that marker, so
partial arm outcomes cannot become an accidental adaptive prompt.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import harness as harness_mod
from . import ocr, pipeline
from .routing import policy_digest


PROTOCOL_VERSION = "sealed3-multiharness-v1"
_SAFE_ARM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_UPSTREAM_ARTIFACTS = (
    "artifact_registry.json",
    "evidence_span_registry.json",
    "field_claim_graph.json",
    "field_drafts.json",
    "field_ledger.json",
)


class BatchPlanError(RuntimeError):
    """The frozen plan, workspace, or batch boundary does not match."""


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchPlanError(f"不可读 JSON:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise BatchPlanError(f"JSON 顶层必须是 object:{path}")
    return payload


def _write_json(path: Path, payload: object) -> None:
    Path(path).write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _repo_path(repo_root: Path, relative: str, *, label: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute():
        raise BatchPlanError(f"{label} 必须是仓库相对路径:{relative}")
    root = Path(repo_root).resolve()
    resolved = (root / raw).resolve()
    if not resolved.is_relative_to(root):
        raise BatchPlanError(f"{label} 逃出仓库:{relative}")
    return resolved


def _checked_file(path: Path, expected: str, *, label: str) -> Path:
    if not path.is_file():
        raise BatchPlanError(f"{label} 不存在:{path}")
    actual = _sha(path)
    if actual != expected:
        raise BatchPlanError(
            f"{label} sha256 漂移:expected={expected},actual={actual}"
        )
    return path


def load_plan(plan_path: Path, *, repo_root: Path | None = None,
              verify_frozen_files: bool = True) -> dict:
    """Load and fully validate a committed multi-harness plan.

    The returned dictionary contains private ``_loaded_*`` values for the
    runner.  Those values are derived from pinned files; they are never written
    back to the protocol artifact.

    ``verify_frozen_files`` 钉的是**代码修订**,不是协议内容。跑批必须验 ——
    拿漂移过的代码执行一份冻结计划,产出的数字不属于它声称的那次冻结 ——
    所以默认 True,运行路径(`run_batch`)不许关。

    读一份**历史**计划是另一回事:SEALED-3 的计划钉在 447acf0,此后任何一次
    正常开发都会让这些哈希对不上,那不是计划坏了。要核对历史计划的代码钉,
    应该和它开箱那个 commit 的 blob 比,不是和当前工作树比
    (见 tests/test_sealed_batch.py)。
    """
    plan_path = Path(plan_path).resolve()
    repo_root = Path(repo_root or Path(__file__).resolve().parent.parent).resolve()
    plan = _json(plan_path)
    if plan.get("protocol_version") != PROTOCOL_VERSION:
        raise BatchPlanError(
            f"protocol_version 必须是 {PROTOCOL_VERSION!r}"
        )

    doc_list_path = _repo_path(
        repo_root, str(plan.get("doc_list_path", "")), label="doc_list_path"
    )
    _checked_file(
        doc_list_path, str(plan.get("doc_list_sha256", "")), label="doc_list"
    )
    doc_list = _json(doc_list_path)
    doc_ids = doc_list.get("doc_ids")
    if not isinstance(doc_ids, list) or not all(
            isinstance(doc_id, str) and doc_id for doc_id in doc_ids):
        raise BatchPlanError("doc_list.doc_ids 必须是非空字符串数组")
    if len(doc_ids) != len(set(doc_ids)):
        raise BatchPlanError("doc_list.doc_ids 有重复")
    if len(doc_ids) != plan.get("n_docs") or doc_list.get("n") != len(doc_ids):
        raise BatchPlanError("n_docs / doc_list.n / doc_ids 长度不一致")

    schema_spec = plan.get("schema")
    if not isinstance(schema_spec, dict):
        raise BatchPlanError("schema 规格缺失")
    schema_path = _repo_path(
        repo_root, str(schema_spec.get("path", "")), label="schema.path"
    )
    _checked_file(
        schema_path, str(schema_spec.get("sha256", "")), label="schema.sha256"
    )
    schema = _json(schema_path)
    schema_actual = harness_mod.schema_digest(schema)
    if schema_actual != schema_spec.get("digest"):
        raise BatchPlanError(
            "schema.digest 漂移:"
            f"expected={schema_spec.get('digest')},actual={schema_actual}"
        )

    options = plan.get("run_options")
    expected_options = {
        "include_vision": False,
        "render_crops": False,
        "out_of_calibration": False,
    }
    if options != expected_options:
        raise BatchPlanError(
            f"SEALED-3 批处理 run_options 必须固定为 {expected_options}"
        )

    specs = plan.get("arms")
    if not isinstance(specs, list) or not specs:
        raise BatchPlanError("arms 必须是非空数组")
    loaded_arms: list[dict] = []
    seen: set[str] = set()
    by_id: dict[str, dict] = {}
    for spec in specs:
        if not isinstance(spec, dict):
            raise BatchPlanError("每个 arm 必须是 object")
        arm_id = spec.get("arm_id")
        if not isinstance(arm_id, str) or not _SAFE_ARM_ID.fullmatch(arm_id):
            raise BatchPlanError(f"非法 arm_id:{arm_id!r}")
        if arm_id in seen:
            raise BatchPlanError(f"重复 arm_id:{arm_id}")
        seen.add(arm_id)

        policy_path = _repo_path(
            repo_root, str(spec.get("policy_path", "")),
            label=f"{arm_id}.policy_path",
        )
        _checked_file(
            policy_path, str(spec.get("policy_sha256", "")),
            label=f"{arm_id}.policy_sha256",
        )
        policy = _json(policy_path)
        harness_id = spec.get("harness_id")
        if policy.get("harness_id") != harness_id:
            raise BatchPlanError(
                f"{arm_id}:policy.harness_id={policy.get('harness_id')!r} "
                f"!= spec {harness_id!r}"
            )
        actual_digest = policy_digest(policy)
        if actual_digest != spec.get("policy_digest"):
            raise BatchPlanError(
                f"{arm_id}.policy_digest 漂移:"
                f"expected={spec.get('policy_digest')},actual={actual_digest}"
            )
        loaded = {
            **spec,
            "_active": {
                "harness_id": harness_id,
                "policy": policy,
                "policy_digest": actual_digest,
                "policy_sha256": spec["policy_sha256"],
                "schema": schema,
                "schema_digest": schema_actual,
                "schema_sha256": schema_spec["sha256"],
            },
        }
        loaded_arms.append(loaded)
        by_id[arm_id] = loaded

    primary = plan.get("primary_arm_id")
    if primary not in by_id:
        raise BatchPlanError(f"primary_arm_id 不在 arms:{primary!r}")
    qualification_baseline = plan.get("qualification_baseline_arm_id")
    if qualification_baseline not in by_id:
        raise BatchPlanError(
            "qualification_baseline_arm_id 不在 arms:"
            f"{qualification_baseline!r}"
        )
    for arm in loaded_arms:
        repeat_of = arm.get("repeat_of")
        if repeat_of is None:
            continue
        parent = by_id.get(repeat_of)
        if parent is None or repeat_of == arm["arm_id"]:
            raise BatchPlanError(
                f"{arm['arm_id']}.repeat_of 必须指向前述另一个 arm"
            )
        if parent["_active"] != arm["_active"]:
            raise BatchPlanError(
                f"{arm['arm_id']} 标成 repeat_of={repeat_of},但 harness 内容不同"
            )

    comparisons = plan.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise BatchPlanError("comparisons 必须是非空数组")
    comparison_ids: set[str] = set()
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            raise BatchPlanError("每个 comparison 必须是 object")
        cid = comparison.get("comparison_id")
        if not isinstance(cid, str) or not _SAFE_ARM_ID.fullmatch(cid):
            raise BatchPlanError(f"非法 comparison_id:{cid!r}")
        if cid in comparison_ids:
            raise BatchPlanError(f"重复 comparison_id:{cid}")
        comparison_ids.add(cid)
        candidate = comparison.get("candidate")
        baseline = comparison.get("baseline")
        if candidate not in by_id or baseline not in by_id or candidate == baseline:
            raise BatchPlanError(
                f"{cid}:candidate/baseline 必须指向两个不同的冻结 arm"
            )

    frozen_files = plan.get("frozen_files")
    if not isinstance(frozen_files, list) or not frozen_files:
        raise BatchPlanError("frozen_files 必须是非空数组")
    frozen_paths: set[str] = set()
    for item in frozen_files:
        if not isinstance(item, dict):
            raise BatchPlanError("每个 frozen_file 必须是 object")
        relative = item.get("path")
        if not isinstance(relative, str) or relative in frozen_paths:
            raise BatchPlanError(f"frozen_file 路径缺失或重复:{relative!r}")
        frozen_paths.add(relative)
        path = _repo_path(repo_root, relative, label="frozen_file.path")
        if verify_frozen_files:
            _checked_file(path, str(item.get("sha256", "")),
                          label=f"frozen_file:{relative}")

    return {
        **plan,
        "_repo_root": repo_root,
        "_plan_path": plan_path,
        "_plan_sha256": _sha(plan_path),
        "_doc_ids": doc_ids,
        "_loaded_arms": loaded_arms,
    }


@contextmanager
def frozen_harness(active: dict) -> Iterator[None]:
    """Expose one frozen arm to the pipeline without changing product state."""
    original = harness_mod.load_active

    def _load_active(_root: Path | None = None) -> dict:
        return copy.deepcopy(active)

    harness_mod.load_active = _load_active
    try:
        yield
    finally:
        harness_mod.load_active = original


@contextmanager
def _corpus_environment(root: Path) -> Iterator[None]:
    keys = ("INVOICELOOP_CORPUS", "INVOICELOOP_DWS_DERISK")
    previous = {key: os.environ.get(key) for key in keys}
    for key in keys:
        os.environ[key] = str(Path(root).resolve())
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    try:
        yield
    finally:
        ocr.load_ocr.cache_clear()
        ocr.doc_tokens.cache_clear()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _git_head(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise BatchPlanError("无法读取 opening git HEAD")
    return result.stdout.strip()


def _tracked_dirty(repo_root: Path) -> bool:
    for args in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 1:
            return True
        if result.returncode != 0:
            raise BatchPlanError("无法确认 opening 工作树状态")
    return False


def _tree_digest(root: Path) -> tuple[str, dict[str, str]]:
    files: dict[str, str] = {}
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        file_sha = _sha(path)
        files[relative] = file_sha
        digest.update(f"{relative}={file_sha}\n".encode())
    return digest.hexdigest(), files


def _arm_record(run_dir: Path, arm: dict) -> dict:
    manifest = _json(run_dir / "run_manifest.json")
    inputs = _json(run_dir / "input_manifest.json")
    routing = _json(run_dir / "routing_report.json")
    active = arm["_active"]
    checks = {
        "run_manifest.harness_id": manifest.get("harness_id"),
        "input_manifest.harness_id": inputs.get("harness_id"),
        "routing_report.harness_id": routing.get("harness_id"),
    }
    bad = {name: value for name, value in checks.items()
           if value != active["harness_id"]}
    if bad:
        raise BatchPlanError(f"{arm['arm_id']} harness 身份不一致:{bad}")
    if inputs.get("harness_digest") != active["policy_digest"] \
            or routing.get("policy_digest") != active["policy_digest"]:
        raise BatchPlanError(f"{arm['arm_id']} policy digest 未进入 run 工件")
    if inputs.get("schema_digest") != active["schema_digest"]:
        raise BatchPlanError(f"{arm['arm_id']} schema digest 未进入执行指纹")

    tree_sha, file_shas = _tree_digest(run_dir)
    upstream = {name: file_shas[name] for name in _UPSTREAM_ARTIFACTS}
    return {
        "arm_id": arm["arm_id"],
        "harness_id": active["harness_id"],
        "role": arm.get("role"),
        "provenance": arm.get("provenance"),
        "parent_harness_id": arm.get("parent_harness_id"),
        "hypothesis": arm.get("hypothesis"),
        "repeat_of": arm.get("repeat_of"),
        "policy_digest": active["policy_digest"],
        "schema_digest": active["schema_digest"],
        "input_fingerprint": inputs["fingerprint"],
        "execution_fingerprint": inputs["execution_fingerprint"],
        "code_revision": inputs.get("code_revision"),
        "run_tree_sha256": tree_sha,
        "upstream_artifacts": upstream,
        "files": file_shas,
    }


def run_batch(
    plan_path: Path,
    output_root: Path,
    *,
    corpus_root: Path,
    expected_head: str,
    repo_root: Path | None = None,
) -> dict:
    """Open one evidence set under every frozen arm, then seal the batch marker.

    No metric is calculated here.  Only identities, hashes, and equality
    invariants are exposed before ``batch_complete.json`` exists.
    """
    repo_root = Path(repo_root or Path(__file__).resolve().parent.parent).resolve()
    plan = load_plan(plan_path, repo_root=repo_root)
    output_root = Path(output_root)
    corpus_root = Path(corpus_root).resolve()
    if output_root.exists():
        raise BatchPlanError(f"批输出目录必须不存在:{output_root}")
    if _tracked_dirty(repo_root):
        raise BatchPlanError("opening 前存在已跟踪但未提交的改动")
    actual_head = _git_head(repo_root)
    if actual_head != expected_head:
        raise BatchPlanError(
            f"opening HEAD 不符:expected={expected_head},actual={actual_head}"
        )

    corpus_list_rel = plan.get("corpus_doc_list")
    if not isinstance(corpus_list_rel, str) or not corpus_list_rel:
        raise BatchPlanError("corpus_doc_list 缺失")
    corpus_list = (corpus_root / corpus_list_rel).resolve()
    if not corpus_list.is_relative_to(corpus_root):
        raise BatchPlanError("corpus_doc_list 逃出 corpus")
    corpus_docs = _json(corpus_list).get("doc_ids")
    if corpus_docs != plan["_doc_ids"]:
        raise BatchPlanError("corpus doc_list 与冻结 doc_list 不一致")
    missing = [
        f"{doc_id}.{mode}.json"
        for doc_id in plan["_doc_ids"]
        for mode in ("understand", "agentic")
        if not (corpus_root / "raw" / f"{doc_id}.{mode}.json").is_file()
    ]
    if missing:
        raise BatchPlanError(f"sealed raw 缺 {len(missing)} 个响应")

    output_root.mkdir(parents=True)
    started = {
        "status": "opened",
        "protocol_version": PROTOCOL_VERSION,
        "plan_sha256": plan["_plan_sha256"],
        "opened_at_commit": actual_head,
        "primary_arm_id": plan["primary_arm_id"],
        "qualification_baseline_arm_id": plan["qualification_baseline_arm_id"],
        "n_docs": len(plan["_doc_ids"]),
        "arms": [arm["arm_id"] for arm in plan["_loaded_arms"]],
        "comparisons": plan["comparisons"],
        "note": "只记录身份;batch_complete 前禁止读取任何臂的结果。",
    }
    _write_json(output_root / "batch_started.json", started)

    records: list[dict] = []
    try:
        with _corpus_environment(corpus_root):
            for arm in plan["_loaded_arms"]:
                # Every arm uses the same leaf name.  ``deliverable.json`` records
                # run_dir.name, so using arm_id as the leaf would manufacture a
                # byte difference in an otherwise exact repeatability control.
                run_dir = output_root / arm["arm_id"] / "run"
                with frozen_harness(arm["_active"]):
                    pipeline.run(
                        plan["_doc_ids"],
                        run_dir,
                        render_crops=False,
                        include_vision=False,
                        out_of_calibration=False,
                    )
                records.append(_arm_record(run_dir, arm))

        same_input = len({r["input_fingerprint"] for r in records}) == 1
        same_upstream = len({
            json.dumps(r["upstream_artifacts"], sort_keys=True)
            for r in records
        }) == 1
        by_id = {record["arm_id"]: record for record in records}
        repeat_equal = all(
            record["run_tree_sha256"] == by_id[record["repeat_of"]]["run_tree_sha256"]
            for record in records if record.get("repeat_of")
        )
        invariants = {
            "same_input_fingerprint": same_input,
            "same_upstream_artifacts": same_upstream,
            "repeat_runs_byte_identical": repeat_equal,
        }
        if not all(invariants.values()):
            raise BatchPlanError(f"paired batch invariant 失败:{invariants}")

        complete = {
            **started,
            "status": "complete",
            "invariants": invariants,
            "arms": records,
            "note": "批次完整;现在才允许运行独立 scorer 读取结果。",
        }
        _write_json(output_root / "batch_complete.json", complete)
        return complete
    except Exception as exc:
        _write_json(output_root / "batch_failed.json", {
            **started,
            "status": "failed",
            "completed_arm_ids": [record["arm_id"] for record in records],
            "error_type": type(exc).__name__,
            "error": str(exc),
            "note": "失败与已产出的部分臂均保留;不得原地续写或删掉重来。",
        })
        raise


def _digest_from_file_map(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative, file_sha in sorted(files.items()):
        digest.update(f"{relative}={file_sha}\n".encode())
    return digest.hexdigest()


def verify_completed_batch(output_root: Path) -> dict:
    """Verify every file captured at opening; later derived files are allowed.

    ``audit_bundle.zip`` is intentionally built after opening and therefore is
    not in the recorded map.  It may be added, but no recorded byte may change.
    """
    output_root = Path(output_root)
    complete_path = output_root / "batch_complete.json"
    if not complete_path.is_file():
        raise BatchPlanError(f"缺 batch_complete.json:{output_root}")
    complete = _json(complete_path)
    if complete.get("status") != "complete":
        raise BatchPlanError("batch_complete status 不是 complete")
    started_path = output_root / "batch_started.json"
    if not started_path.is_file():
        raise BatchPlanError("缺 batch_started.json")
    started = _json(started_path)
    for key in (
        "protocol_version", "plan_sha256", "opened_at_commit",
        "primary_arm_id", "qualification_baseline_arm_id", "n_docs",
        "comparisons",
    ):
        if started.get(key) != complete.get(key):
            raise BatchPlanError(f"batch_started 与 complete 的 {key} 不一致")

    records = complete.get("arms")
    if not isinstance(records, list) or not records:
        raise BatchPlanError("batch_complete.arms 缺失")
    by_id: dict[str, dict] = {}
    for record in records:
        arm_id = record.get("arm_id")
        files = record.get("files")
        if not isinstance(arm_id, str) or not isinstance(files, dict):
            raise BatchPlanError("batch_complete arm 结构不完整")
        if arm_id in by_id:
            raise BatchPlanError(f"batch_complete 重复 arm:{arm_id}")
        by_id[arm_id] = record
        run_dir = output_root / arm_id / "run"
        for relative, expected in files.items():
            path = run_dir / relative
            if not path.is_file() or _sha(path) != expected:
                raise BatchPlanError(
                    f"{arm_id} run 工件哈希漂移:{relative}"
                )
        if _digest_from_file_map(files) != record.get("run_tree_sha256"):
            raise BatchPlanError(f"{arm_id} run_tree_sha256 自身不一致")

    if len({r.get("input_fingerprint") for r in records}) != 1:
        raise BatchPlanError("完成标记里的 input_fingerprint 不一致")
    upstream = {
        json.dumps(r.get("upstream_artifacts"), sort_keys=True)
        for r in records
    }
    if len(upstream) != 1:
        raise BatchPlanError("完成标记里的 upstream_artifacts 不一致")
    for record in records:
        repeat_of = record.get("repeat_of")
        if repeat_of and (
            repeat_of not in by_id
            or record.get("run_tree_sha256") != by_id[repeat_of].get("run_tree_sha256")
        ):
            raise BatchPlanError(f"{record.get('arm_id')} repeatability 对照不一致")
    return complete


def _heldout_module(repo_root: Path):
    path = Path(repo_root) / "scripts" / "heldout_metrics.py"
    if not path.is_file():
        raise BatchPlanError(f"冻结 H1-H6 scorer 不存在:{path}")
    spec = importlib.util.spec_from_file_location("_sealed_heldout_metrics", path)
    if spec is None or spec.loader is None:
        raise BatchPlanError(f"无法加载 H1-H6 scorer:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _band_pass(value: float, band: tuple[float | None, float | None]) -> bool:
    low, high = band
    return (low is None or value >= low) and (high is None or value <= high)


def score_completed_batch(
    output_root: Path,
    *,
    corpus_root: Path,
    repo_root: Path | None = None,
    bundle: Path | None = None,
) -> dict:
    """Score a complete batch.  Truth referees both arms; it is not an arm."""
    output_root = Path(output_root)
    repo_root = Path(repo_root or Path(__file__).resolve().parent.parent).resolve()
    complete = verify_completed_batch(output_root)

    from . import dws
    from .safety_metrics import score_routes, truth

    scored_arms: list[dict] = []
    with _corpus_environment(Path(corpus_root)):
        heldout = _heldout_module(repo_root)
        for record in complete["arms"]:
            run_dir = output_root / record["arm_id"] / "run"
            matrix = _json(run_dir / "support_matrix.json")
            routing = _json(run_dir / "routing_report.json")
            deliverable = _json(run_dir / "deliverable.json")
            h_metrics = heldout.measure(run_dir)
            doc_ids = sorted({row["doc_id"] for row in routing["routes"]})
            understand = {}
            for doc_id in doc_ids:
                response = dws.load_response(doc_id, "understand")
                understand[doc_id] = response.data if response else None
            safety = score_routes(
                routing["routes"],
                truth_of=truth,
                understand_of=lambda doc_id: understand.get(doc_id),
            )
            summary = matrix["summary"]
            if safety["slots"] != summary["slots"] \
                    or safety["review"] != summary["human_queue"]:
                raise BatchPlanError(
                    f"{record['arm_id']} workload 的两个权威投影不一致"
                )
            touched = len({
                row["doc_id"] for row in routing["routes"]
                if row["route"] not in ("auto_accept", "auto_absent")
            })
            n_slots = summary["slots"]
            n_docs = len(doc_ids)
            scored_arms.append({
                "arm_id": record["arm_id"],
                "harness_id": record["harness_id"],
                "role": record.get("role"),
                "repeat_of": record.get("repeat_of"),
                "policy_digest": record["policy_digest"],
                "H1_H6": {
                    name: {
                        "value": h_metrics[name],
                        "pass": _band_pass(h_metrics[name], heldout.BANDS[name]),
                    }
                    for name in heldout.BANDS
                },
                "H_details": {
                    key: value for key, value in h_metrics.items()
                    if key.startswith("_")
                },
                "workload": {
                    "slots": n_slots,
                    "human_queue": summary["human_queue"],
                    "human_queue_rate": summary["human_queue"] / max(n_slots, 1),
                    "requires_adjudication": summary["requires_adjudication"],
                    "requires_adjudication_rate":
                        summary["requires_adjudication"] / max(n_slots, 1),
                    "decision_load_for_release":
                        deliverable["summary"]["decision_load_for_release"],
                    "documents_touched": touched,
                    "document_touch_rate": touched / max(n_docs, 1),
                    "machine_decided": summary["machine_decided"],
                    "machine_absent": summary["machine_absent"],
                },
                "safety": safety,
            })

    by_id = {arm["arm_id"]: arm for arm in scored_arms}
    comparisons = []
    for spec in complete["comparisons"]:
        candidate = by_id[spec["candidate"]]
        baseline = by_id[spec["baseline"]]
        c_work = candidate["workload"]
        b_work = baseline["workload"]
        c_safe = candidate["safety"]
        b_safe = baseline["safety"]
        comparisons.append({
            **spec,
            "delta": {
                "human_queue_slots": c_work["human_queue"] - b_work["human_queue"],
                "human_queue_rate":
                    c_work["human_queue_rate"] - b_work["human_queue_rate"],
                "decision_load_for_release":
                    c_work["decision_load_for_release"]
                    - b_work["decision_load_for_release"],
                "documents_touched":
                    c_work["documents_touched"] - b_work["documents_touched"],
                "silent_absent":
                    c_safe["silent_absent"] - b_safe["silent_absent"],
                "silent_wrong": c_safe["silent_wrong"] - b_safe["silent_wrong"],
                "absent_hits": c_safe["absent_hits"] - b_safe["absent_hits"],
                "value_hits": c_safe["value_hits"] - b_safe["value_hits"],
            },
            "candidate_not_worse": {
                "P1_silent_absent":
                    c_safe["silent_absent"] <= b_safe["silent_absent"],
                "P1_silent_wrong":
                    c_safe["silent_wrong"] <= b_safe["silent_wrong"],
                "P2_human_queue":
                    c_work["human_queue"] <= b_work["human_queue"],
            },
        })

    primary = by_id[complete["primary_arm_id"]]
    baseline = by_id[complete["qualification_baseline_arm_id"]]
    h7: dict = {"status": "PENDING_BUNDLE_VERIFY"}
    if bundle is not None:
        from .adjudicate import verify_bundle

        bundle = Path(bundle)
        report = verify_bundle(bundle)
        h7 = {
            "status": "PASS" if report.get("ok") else "FAIL",
            "bundle": str(bundle),
            "bundle_sha256": _sha(bundle),
            "verify": report,
        }
    qualification = {
        "primary_arm_id": primary["arm_id"],
        "baseline_arm_id": baseline["arm_id"],
        "H1_H6": primary["H1_H6"],
        "H7": h7,
        "P1": {
            "silent_absent_not_up":
                primary["safety"]["silent_absent"]
                <= baseline["safety"]["silent_absent"],
            "silent_wrong_not_up":
                primary["safety"]["silent_wrong"]
                <= baseline["safety"]["silent_wrong"],
        },
        "P2": {
            "human_queue_not_up":
                primary["workload"]["human_queue"]
                <= baseline["workload"]["human_queue"],
        },
    }
    return {
        "protocol_version": complete["protocol_version"],
        "batch_complete_sha256": _sha(output_root / "batch_complete.json"),
        "opened_at_commit": complete["opened_at_commit"],
        "primary_arm_id": complete["primary_arm_id"],
        "qualification_baseline_arm_id":
            complete["qualification_baseline_arm_id"],
        "n_docs": complete["n_docs"],
        "arms": scored_arms,
        "comparisons": comparisons,
        "qualification": qualification,
        "human_adjudication_accuracy": {
            "status": "NOT_MEASURED",
            "reason": "需要完整的人类裁决臂;本批只测确定性 workload 与真值安全指标。",
        },
        "discipline": (
            "DocILE truth 只作两臂共同裁判,不是实验臂;本 scorer 未调用 DWS 或 ADK。"
        ),
    }
