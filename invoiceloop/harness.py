"""Harness loading: replay the PROM hash chain → policy dict + content-addressed
digest.

Where authority lives (83-point review P0-2, plus adjudication five): the active
harness is determined by replaying the **promotion hash chain**
(`improve/promotions/PROM-*.json`). `active_harness.json` is only a cache. Each
PROM record carries previous_promotion_digest (the sha256 of the previous
record's bytes) and both the from-side and to-side policy digests. The replay
checks that filename sequence numbers are contiguous, that record IDs match
filenames, that the from-side harness and digest equal the current replay state,
that chain digests are continuous, and that the target policy file's bytes match
to_policy_digest. A cache that disagrees with the replay, or a pointer with no
records behind it, fails closed.

A hash chain detects isolated edits and operational accidents. The anchor against
wholesale rewriting of local history is still out of band — a git tag, a published
digest — the same honesty boundary as bundle verify.

Default = the packaged HAR-0001: a conservative starting point, equivalent to the
inline triage logic used before 2026-08-05. The pointer has exactly one writer,
`improve promote` / `rollback`, and both require a name and a rationale.
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path

from .routing import policy_digest

DEFAULT_HARNESS = "HAR-0001"


def _builtin_schema_bytes() -> bytes:
    path = (resources.files("invoiceloop") / "harnesses" / DEFAULT_HARNESS
            / "extraction_schema.json")
    if path.is_file():
        return path.read_bytes()
    # 极端回退:与 ingest.default_extraction_schema 同形
    from .ingest import default_extraction_schema
    return (json.dumps(default_extraction_schema(), indent=1,
                       ensure_ascii=False) + "\n").encode("utf-8")


def _schema_bytes(root: Path, harness_id: str) -> bytes:
    """workspace harnesses/ 里的 schema 字节;缺则回退包内默认。

    既有 PROM 记录可能没有 to_schema_digest —— 缺文件视为包内默认,
    不破坏哈希链。
    """
    path = Path(root) / "harnesses" / harness_id / "extraction_schema.json"
    if path.exists():
        return path.read_bytes()
    return _builtin_schema_bytes()


def schema_digest(schema: dict) -> str:
    """canonical JSON sha256(与 policy_digest 同风格)。"""
    return hashlib.sha256(
        json.dumps(schema, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _builtin_policy_bytes() -> bytes:
    return (resources.files("invoiceloop") / "harnesses" / DEFAULT_HARNESS
            / "routing_policy.json").read_bytes()


def _builtin_policy() -> dict:
    return json.loads(_builtin_policy_bytes())


def _policy_bytes(root: Path, harness_id: str) -> bytes:
    """workspace harnesses/ 里的 policy 字节;包内默认回退到包内文件。"""
    path = Path(root) / "harnesses" / harness_id / "routing_policy.json"
    if path.exists():
        return path.read_bytes()
    if harness_id == DEFAULT_HARNESS:
        return _builtin_policy_bytes()
    raise RuntimeError(
        f"harness {harness_id} 没有 routing_policy.json —— "
        f"晋升记录指向的策略必须落盘可查")


def _replay_promotions(root: Path) -> tuple[str, bytes, bytes, list[dict]]:
    """重放晋升哈希链,返回 (active_id, policy_bytes, schema_bytes, records)。

    任一环节不符即 RuntimeError(fail closed,不许静默回退)。
    记录缺 to_schema_digest = 视为包内默认 schema(兼容 PROM-0001..0003)。
    """
    promotions_dir = Path(root) / "improve" / "promotions"
    files = sorted(promotions_dir.glob("PROM-*.json")) \
        if promotions_dir.exists() else []
    current = DEFAULT_HARNESS
    current_bytes = _builtin_policy_bytes()
    current_schema = _builtin_schema_bytes()
    prev_digest: str | None = None
    records: list[dict] = []
    for i, path in enumerate(files, start=1):
        if path.stem != f"PROM-{i:04d}":
            raise RuntimeError(
                f"晋升记录文件名不连续:{path.name}(期望 PROM-{i:04d}.json)"
                f" —— 链被插删,拒绝加载")
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("promotion_id") != path.stem:
            raise RuntimeError(
                f"{path.name}:记录内 promotion_id={rec.get('promotion_id')}"
                f" 与文件名不符 —— 拒绝加载")
        if rec.get("previous_promotion_digest") != prev_digest:
            raise RuntimeError(
                f"{path.name}:previous_promotion_digest 与上一条文件字节不符"
                f" —— 哈希链断裂,拒绝加载")
        if rec.get("from_harness_id") != current:
            raise RuntimeError(
                f"{path.name}:from={rec.get('from_harness_id')},重放到这里 "
                f"active 是 {current} —— 链断裂,拒绝加载")
        from_sha = hashlib.sha256(current_bytes).hexdigest()
        if rec.get("from_policy_digest") != from_sha:
            raise RuntimeError(
                f"{path.name}:from_policy_digest 与 {current} 的实际字节不符"
                f" —— 政策文件被改过,拒绝加载")
        target_bytes = _policy_bytes(root, rec["to_harness_id"])
        if rec.get("to_policy_digest") != hashlib.sha256(target_bytes).hexdigest():
            raise RuntimeError(
                f"{path.name}:目标 {rec['to_harness_id']} 的 policy 字节与记录"
                f"不符 —— 晋升后政策被改过,拒绝加载")
        target_schema = _schema_bytes(root, rec["to_harness_id"])
        expected_schema = rec.get("to_schema_digest")
        if expected_schema is not None:
            actual = hashlib.sha256(target_schema).hexdigest()
            if expected_schema != actual:
                raise RuntimeError(
                    f"{path.name}:目标 {rec['to_harness_id']} 的 schema 字节与记录"
                    f"不符 —— 晋升后 schema 被改过,拒绝加载")
        records.append(rec)
        current = rec["to_harness_id"]
        current_bytes = target_bytes
        current_schema = target_schema
        prev_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return current, current_bytes, current_schema, records


def load_active(root: Path | None = None) -> dict:
    """{harness_id, policy, policy_digest, policy_sha256, schema, schema_sha256}。

    root = workspace/语料根。policy_digest 是 canonical JSON 的内容寻址
    (进执行指纹);policy_sha256 是文件字节 sha256(晋升链绑定用)。
    schema 同理;旧 PROM 无 to_schema_digest 时用包内默认。
    """
    if root is not None:
        root = Path(root)
        active_id, active_bytes, schema_bytes, records = _replay_promotions(root)
        pointer = root / "improve" / "active_harness.json"
        if pointer.exists():
            rec = json.loads(pointer.read_text(encoding="utf-8"))
            if not records:
                raise RuntimeError(
                    "存在 active_harness.json 指针但没有任何晋升记录 —— "
                    "指针是缓存不是权威,伪造的指针拒绝加载"
                    "(要换 harness 走 improve promote/rollback)")
            last = records[-1]
            last_digest = hashlib.sha256(
                (root / "improve" / "promotions"
                 / f"{last['promotion_id']}.json").read_bytes()).hexdigest()
            if rec.get("harness_id") != active_id \
                    or rec.get("promotion_id") != last["promotion_id"] \
                    or rec.get("promotion_digest") != last_digest:
                raise RuntimeError(
                    "active_harness.json 与晋升链重放结果不一致 —— "
                    "指针是缓存不是权威,被手改过的指针拒绝加载")
        elif records:
            raise RuntimeError(
                "有晋升记录但缺 active_harness.json 缓存 —— "
                "状态不完整,拒绝猜测(重新 promote 或删 promotions/)")
        policy = json.loads(active_bytes)
        schema = json.loads(schema_bytes)
        return {"harness_id": active_id, "policy": policy,
                "policy_digest": policy_digest(policy),
                "policy_sha256": hashlib.sha256(active_bytes).hexdigest(),
                "schema": schema,
                "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
                "schema_digest": schema_digest(schema)}
    raw = _builtin_policy_bytes()
    policy = json.loads(raw)
    schema_raw = _builtin_schema_bytes()
    schema = json.loads(schema_raw)
    return {"harness_id": DEFAULT_HARNESS, "policy": policy,
            "policy_digest": policy_digest(policy),
            "policy_sha256": hashlib.sha256(raw).hexdigest(),
            "schema": schema,
            "schema_sha256": hashlib.sha256(schema_raw).hexdigest(),
            "schema_digest": schema_digest(schema)}
