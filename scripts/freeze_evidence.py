#!/usr/bin/env python3
"""把 run 目录里的冻结工件复制进 docs/evidence/<round>/<stage>/ 并写 MANIFEST.sha256。

存在的理由很实际:runs/ 是 gitignored 的 symlink,`git add runs/...` 不成立,
于是「协议冻结的 commit 先于结果」这条纪律在 git 历史里根本看不见。

分阶段不可变:一个 stage 只能冻一次,manifest 存在即拒绝。一轮里冻好几次
(名单 / 提取小结 / 四臂 / 走前工件 / 走后账本)必须各占一个 stage ——
共用一份 manifest 的话,后一次会把前一次的条目删掉,而前一个 commit 已经
背书过那份清单了。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(round_name: str, stage: str, items: list[Path]) -> Path:
    for part, label in ((round_name, "round"), (stage, "stage")):
        if not _NAME.fullmatch(part):
            raise SystemExit(f"fatal: 非法 {label} 名:{part!r}")
    dest = REPO / "docs" / "evidence" / round_name / stage
    manifest = dest / "MANIFEST.sha256"
    if manifest.exists():
        raise SystemExit(
            f"fatal: {round_name}/{stage} 已冻结过 —— 冻结是一次性的。"
            f"新证据用新 stage;真要重来就换 round 名。\n"
            f"  现有清单:{manifest}")
    lines = []
    staged: list[tuple[Path, Path]] = []
    for src in sorted(set(items)):
        if not src.is_file():
            raise SystemExit(f"fatal: 要冻结的工件不存在:{src}")
        staged.append((src, dest / src.name))
    names = [dst.name for _, dst in staged]
    if len(set(names)) != len(names):
        raise SystemExit(f"fatal: 同名工件撞车,一个 stage 内不许重名:{sorted(names)}")
    dest.mkdir(parents=True, exist_ok=True)
    for src, dst in staged:
        shutil.copyfile(src, dst)
        lines.append(f"{_sha(dst)}  {dst.name}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--round", required=True, dest="round_name")
    ap.add_argument("--stage", required=True,
                    help="本轮的第几次冻结,如 plan / extract / arms / "
                         "prewalk / postwalk。一个 stage 只能冻一次")
    ap.add_argument("items", nargs="+", type=Path)
    args = ap.parse_args()
    dest = freeze(args.round_name, args.stage, args.items)
    print((dest / "MANIFEST.sha256").read_text(encoding="utf-8"), end="")
    print(f"→ {dest.relative_to(REPO)}")


if __name__ == "__main__":
    main()
