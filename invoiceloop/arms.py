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

import random

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
