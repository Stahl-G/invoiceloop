"""M4 人工裁决与交付(ARCHITECTURE.md §3 骨干④)。

人是裁决的写者,但只能写裁决 —— 不许改已冻结的运行输入(宪章一)。
裁决只追加,不编辑:`adjudication_ledger.jsonl` 是 append-only。
交付 = 把运行目录的全部冻结工件 + 裁决 + panel 打成 audit_bundle.zip,
包内 MANIFEST 列出每个文件的 sha256,拿到包的人可以逐项核验。
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

DECISIONS = ("accept", "reject", "correct", "abstain")

#: 打包进 audit bundle 的工件(缺了算包没打全,不静默跳过)
REQUIRED_ARTIFACTS = (
    "run_manifest.json",
    "artifact_registry.json",
    "evidence_span_registry.json",
    "field_claim_graph.json",
    "field_drafts.json",
    "field_ledger.json",
    "gate_report.json",
    "support_matrix.json",
    "support_panel.html",
    "event_log.jsonl",
    "adjudication_ledger.jsonl",
)


def append_adjudication(
    run_dir: Path,
    *,
    claim_id: str | None,
    doc_id: str,
    field: str,
    decision: str,
    rationale: str,
    adjudicator: str,
    decided_at: str,
    corrected_value: str | None = None,
) -> dict:
    """追加一条裁决。时间由调用方注入 —— 工件本身不读墙钟(可复算)。

    claim_id 若给,必须存在于已冻结账本;给错 ID 是写者的错误,显式拒绝。
    """
    run_dir = Path(run_dir)
    if decision not in DECISIONS:
        raise ValueError(f"decision 必须是 {DECISIONS} 之一,收到 {decision!r}")
    if claim_id is not None:
        ledger = json.loads((run_dir / "field_ledger.json").read_text(encoding="utf-8"))
        known = {c["claim_id"] for c in ledger["claims"]}
        if claim_id not in known:
            raise ValueError(f"claim_id {claim_id!r} 不在已冻结账本里 —— 裁决必须指向真实声明")
    entry = {
        "seq": _next_seq(run_dir),
        "claim_id": claim_id,
        "doc_id": doc_id,
        "field": field,
        "decision": decision,
        "corrected_value": corrected_value,
        "rationale": rationale,
        "adjudicator": adjudicator,
        "decided_at": decided_at,
    }
    with (run_dir / "adjudication_ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _next_seq(run_dir: Path) -> int:
    path = run_dir / "adjudication_ledger.jsonl"
    if not path.exists():
        return 1
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()) + 1


def build_audit_bundle(run_dir: Path) -> Path:
    """audit_bundle.zip:冻结工件 + crops + MANIFEST(每文件 sha256)。

    必备工件缺失 → FileNotFoundError(阻断,不打半个包)。
    """
    run_dir = Path(run_dir)
    missing = [name for name in REQUIRED_ARTIFACTS if not (run_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"audit bundle 缺工件,阻断:{missing}")

    members: list[Path] = [run_dir / name for name in REQUIRED_ARTIFACTS]
    for asset_dir in ("crops", "pages"):
        directory = run_dir / asset_dir
        if directory.exists():
            members.extend(sorted(directory.glob("*.png")))

    manifest_lines = []
    for path in members:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  {path.relative_to(run_dir)}")
    manifest = "\n".join(manifest_lines) + "\n"

    bundle = run_dir / "audit_bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.sha256", manifest)
        for path in members:
            zf.write(path, path.relative_to(run_dir))
    return bundle
