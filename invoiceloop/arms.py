"""Shared rig for the agent-vs-human adjudication arms.

Protocol: `docs/ARM_AGENT_VS_HUMAN_PREREG_2026-08-08.md`, frozen before either arm ran.

Two properties this module exists to guarantee, because the experiment is
worthless without them:

**The slot sample is recomputable.** The 200 slots come from a public drand
beacon drawn after the code froze, sampled off a *sorted* pool so the row order
inside an artifact cannot quietly pick the list. Anyone can rerun it.

**A slot pack never carries the answer.** Both arms judge blind: no DocILE
truth, no decision from the other arm. The field list is an **allowlist**, not a
blocklist, for the same reason the critic view is (2026-08-07): a blocklist
fails open, and here failing open silently voids the whole measurement rather
than raising. A leaked truth value would not crash anything — it would just
produce a very good agent score.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

#: 抽样 PRNG 语境。与 heldout.SEALED_CONTEXTS 同一套做法:换实验换语境,
#: 免得两个实验从同一条随机流上取样。
ARM_CONTEXT = "invoiceloop-arm-v1"

#: 进人工队列的路由。auto_accept / auto_absent 不在池里 —— 没人复核过的
#: 槽才是本实验要问的题。
REVIEW_ROUTE = "review"

#: slot pack 白名单:复核者在 workbench 上看得到的槽位事实,一项不多。
#: **加字段前先问它是不是答案的一部分。**
PACK_FIELDS = (
    "doc_id", "field", "value", "claim_id", "support_strength",
    "source_tiers", "applicability", "limitations", "gate_verdicts",
    "reason_codes", "blocking_findings", "span_ids", "cited_span_ids",
)


def slot_key(row: dict) -> str:
    return f"{row['doc_id']}|{row['field']}"


def review_pool(matrix: dict) -> list[str]:
    """support_matrix → 排序后的待复核槽键。排序是抽样可复算的前提。"""
    return sorted(slot_key(r) for r in matrix["rows"]
                  if r.get("route") == REVIEW_ROUTE)


def sample_slots(matrix: dict, seed_hex: str, n: int) -> list[str]:
    """种子抽样(预注册 §2)。确定性:同 matrix 同种子同名单。

    返回**抽样顺序**,不再排序 —— 顺序本身也是种子的产物,复算时要对得上。
    """
    pool = review_pool(matrix)
    if n > len(pool):
        raise ValueError(f"要 {n} 个槽,池只有 {len(pool)} 个")
    return random.Random(f"{ARM_CONTEXT}|{seed_hex}").sample(pool, n)


def slot_pack(matrix: dict, key: str) -> dict:
    """一个槽给两臂看的全部东西。白名单投影,顺序固定 → 两臂逐字节同题。"""
    rows = {slot_key(r): r for r in matrix["rows"] if "doc_id" in r}
    row = rows.get(key)
    if row is None:
        raise KeyError(f"槽位不存在:{key}")
    return {f: row[f] for f in PACK_FIELDS if f in row}


# ------------------------------------------------------------------ 视觉证据

def visual_pack(run_dir: Path, workspace: Path, key: str, out_dir: Path,
                *, registry: list[dict] | None = None) -> list[Path]:
    """一个槽的图像证据,**顺序确定**:先整页,再按 span_id 排序的裁切图。

    顺序确定是重放身份的前提(`slot_call_id` 把图像顺序也哈希进去)。

    人在 workbench 上看到的是整页 + CSS 画的框;agent 拿到的是同一张整页
    加每个 span 区域的裁切图。**同样的证据,呈现方式不同** —— 这台机器上
    没有 PIL/PyMuPDF,只有 poppler,把框烧进图里要新增依赖(GOAL.md §5:
    新增依赖前先问它挡住哪个具体故障)。这条不对称照登进结果文档。

    渲染不出来就少给,不抛 —— 缺图是要人看见的形状,不是要 200 槽一起崩
    (evidence.render_pages 同一条纪律)。
    """
    from . import evidence

    run_dir, workspace, out_dir = Path(run_dir), Path(workspace), Path(out_dir)
    matrix = json.loads(
        (run_dir / "support_matrix.json").read_text(encoding="utf-8"))
    row = next((r for r in matrix["rows"] if slot_key(r) == key), None)
    if row is None:
        raise KeyError(f"槽位不存在:{key}")
    if registry is None:
        registry = json.loads(
            (run_dir / "evidence_span_registry.json").read_text(encoding="utf-8"))
    by_id = {s["span_id"]: s for s in registry}

    doc = row["doc_id"]
    pdf = workspace / "input" / "pdfs" / f"{doc}.pdf"
    # 绑定 span 与 DWS 指向 span 都给 —— 复核者两种框都看得到
    span_ids = sorted(set(row.get("span_ids") or [])
                      | set(row.get("cited_span_ids") or []))
    spans = [by_id[s] for s in span_ids if s in by_id]

    pages_dir = out_dir / "pages" / doc
    if not pages_dir.is_dir():
        evidence.render_pages(pdf, pages_dir)
    wanted = sorted({s["page"] for s in spans if s.get("bbox_rel")}) or [1]
    images: list[Path] = []
    for page_no in wanted:
        hit = sorted(pages_dir.glob(f"{doc}-*{page_no}.png"))
        exact = [p for p in hit
                 if p.stem.rsplit("-", 1)[-1].lstrip("0") == str(page_no)]
        if exact:
            images.append(exact[0])

    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    for s in spans:
        if not s.get("bbox_rel"):
            continue
        stem = crops_dir / f"{doc}-{s['span_id']}"
        existing = sorted(stem.parent.glob(f"{stem.name}-*.png"))
        if not existing:
            evidence.render_crop(pdf, s["page"], s["bbox_rel"], stem)
            existing = sorted(stem.parent.glob(f"{stem.name}-*.png"))
        if existing:
            images.append(existing[0])
    return images
