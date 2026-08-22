"""建议工件溯源:每槽记「人看见的那条建议出自哪份工件、哪个模型」。

建议本身是显示层的东西(`vision/answers6.<tag>.tsv`),它不进冻结账本 ——
这是宪章一(单一写者)。溯源要解决的是另一个问题:一年后回看某条裁决,
能不能重算出当时屏幕上那条建议。所以记的是**工件的哈希**,不是建议的值:
值能从工件复算,哈希能证明工件没被改过。

三条设计约束,都是被挑出来的:

1. **冻结 TSV,不是冻结读法。** 裁决页显示的建议来自 answers6.<tag>.tsv
   (workbench._vision_state ← ctx.vision ← dws.load_vision_answers)。
   invoice_read.json 只是它的上游 —— suggest_inject.inject 会跳过已有
   (doc, field)、也会丢掉坏行,两者能漂开。冻结上游等于冻结了一份
   人没看过的东西。
2. **导出在服务端,不在浏览器。** 工件哈希与模型 id 是 (run, doc, field)
   加冻结表的纯函数,append_adjudication 自己查得到。让页面用隐藏字段
   发上来,旧标签页和改过的请求就能决定证据身份。
3. **冻结表本身也要被核。** 只信盘上那份 JSON 不够:走中途多注入一个
   reader,页面可能显示 split,而按 slot 查表仍查得到原 reader 的哈希;
   把 TSV 和 JSON 一起改掉,两边又自洽。所以每次都重算 live 工件,
   并与仓库里的走前副本对锚。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

FILENAME = "suggestion_provenance.json"


def record_digest(record: Mapping[str, Any]) -> str:
    """一份记录的 sha256:排序键、紧凑分隔符 —— 与写盘缩进无关。"""
    return hashlib.sha256(json.dumps(
        record, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def build_slots(run_dir: Path) -> dict[str, dict[str, str]]:
    """扫 run 目录下所有 answers6.*.tsv → {「doc|field」: 冻结行}。

    键取全部 tag 的并集,与 workbench 的 ctx.vision 同一个来源:那边也是
    把所有 tag 合并之后判 _vision_state。少扫一个 tag,对账就会误报。
    """
    slots: dict[str, dict[str, str]] = {}
    for tsv in sorted((Path(run_dir) / "vision").glob("answers6.*.tsv")):
        tag = tsv.name[len("answers6."):-len(".tsv")]
        for line in tsv.read_text(encoding="utf-8").splitlines()[1:]:
            if not line.strip():
                continue
            cols = line.split("\t")
            if len(cols) < 3 or not cols[0].strip() or not cols[1].strip():
                continue
            key = f"{cols[0].strip()}|{cols[1].strip()}"
            slots[key] = {
                "tag": tag,
                "displayed_value": cols[2],
                "row_sha256": hashlib.sha256(
                    f"{tag}\t{line}".encode("utf-8")).hexdigest(),
            }
    return slots


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_live(run_dir: Path, prov: Mapping[str, Any]) -> None:
    """盘上此刻的建议,必须逐槽等于走前冻结的那一份。

    只比对 JSON 里记的东西是不够的:走中途多注入一个 tag,页面会因为读者分歧
    显示 split,而按 slot 查表仍能查到原 tag 的哈希 —— 账本于是记下一份看起来
    完整、其实指错了工件的溯源。所以这里重算全量 slots 做集合与逐字段比对。
    """
    frozen = prov.get("slots") or {}
    live = build_slots(run_dir)
    added = sorted(set(live) - set(frozen))
    removed = sorted(set(frozen) - set(live))
    drifted = sorted(
        k for k in set(live) & set(frozen)
        if any(live[k].get(f) != frozen[k].get(f)
               for f in ("tag", "displayed_value", "row_sha256")))
    if added or removed or drifted:
        raise ValueError(
            f"建议在冻结之后变过 —— 新增 {added[:5]} / 消失 {removed[:5]} / "
            f"改动 {drifted[:5]}。走中途补建议或改 TSV 按废臂条款处理,"
            f"不能悄悄记进账本")
    for tag, reader in (prov.get("readers") or {}).items():
        for rel_key, sha_key in (("artifact", "artifact_sha256"),
                                 ("upstream", "upstream_sha256")):
            rel = reader.get(rel_key)
            if not rel:
                continue
            path = Path(run_dir) / rel
            if not path.is_file():
                raise ValueError(f"tag {tag!r} 的 {rel_key} 工件不见了:{rel}")
            if _file_sha(path) != reader.get(sha_key):
                raise ValueError(
                    f"tag {tag!r} 的 {rel} 内容与冻结的 {sha_key} 不符 —— "
                    f"人看的不是工件里那份")


def _verify_repo_copy(prov: Mapping[str, Any], live_path: Path,
                      repo_root: Path) -> None:
    """走前副本已提交时,盘上这份 JSON 必须等于它。

    把 TSV 与 JSON 一起改掉,_verify_live 会两边自洽地放行。仓库里那份
    走前副本是唯一不在 run 目录里、改不动的锚。
    """
    round_name = str(prov.get("round") or "")
    if not round_name:
        raise ValueError("冻结表没有 round 名 —— 找不到走前副本就锚不住")
    manifest = (Path(repo_root) / "docs" / "evidence" / round_name
                / "prewalk" / "MANIFEST.sha256")
    if not manifest.is_file():
        return  # 走前副本尚未提交(开发/测试路径);live 校验仍然生效
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        if name.strip() == FILENAME and digest.strip() != _file_sha(live_path):
            raise ValueError(
                f"{FILENAME} 与 {manifest} 里的走前副本不符 —— "
                f"冻结表在走开始之后被改过")


def load(run_dir: Path, *, repo_root: Path | None = None) -> dict[str, Any] | None:
    """→ 冻结表(已核过);文件不在返回 None(没冻结过建议的 run 照常工作)。

    核验失败抛 ValueError —— 由 append_adjudication 转成「一行都不写」。
    """
    path = Path(run_dir) / "vision" / FILENAME
    if not path.is_file():
        return None
    prov = json.loads(path.read_text(encoding="utf-8"))
    _verify_live(Path(run_dir), prov)
    _verify_repo_copy(prov, path,
                      repo_root or Path(__file__).resolve().parent.parent)
    return prov


def derive(prov: Mapping[str, Any] | None, doc_id: str, field: str,
           suggestion_seen: str | None) -> tuple[str, str] | None:
    """→ (工件 sha256, 模型 id);没有冻结表返回 None。对不上就抛 ValueError。

    三向对账。任何一边说了另一边不认的话,都是阻断,不是「尽力而为」:
    - 表里没有、账本说看见了  → 走中途补生成的建议(废臂条款点名的那条)
    - 表里有、账本说没看见    → 该展示建议的槽一个字没记(P1 最该抓的故障)
    - 值对不上                → 冻结之后 TSV 被改过,人看的不是工件里那条
    """
    if not prov:
        return None
    slots = prov.get("slots") or {}
    key = f"{doc_id}|{field}"
    entry = slots.get(key)
    if suggestion_seen is None:
        if entry is not None:
            raise ValueError(
                f"冻结表里有 {key} 的建议,这条裁决却没记 suggestion_seen —— "
                f"该展示建议的槽一个字都没记下来,先查渲染再裁决")
        return None
    if entry is None:
        raise ValueError(
            f"冻结表里没有 {key} —— 人看见的建议不在走前冻结的工件里。"
            f"走中途补生成的建议按废臂条款处理,不能悄悄记进账本")
    state, _, value = str(suggestion_seen).partition(":")
    if state in ("agree", "agree_rejected") and value != entry["displayed_value"]:
        raise ValueError(
            f"{key} 展示值与冻结值不符(账本 {value!r} / 工件 "
            f"{entry['displayed_value']!r})—— 冻结之后 TSV 被改过")
    reader = (prov.get("readers") or {}).get(entry["tag"])
    if not reader or not reader.get("artifact_sha256") or not reader.get("model"):
        raise ValueError(
            f"冻结表缺 tag {entry['tag']!r} 的工件哈希或模型 id —— "
            f"半份溯源比没有更糟,它看起来像证据")
    return str(reader["artifact_sha256"]), str(reader["model"])
