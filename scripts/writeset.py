#!/usr/bin/env python3
"""run 目录的文件哈希快照与差集 —— 用来证明某一趟只动了该动的东西。

snapshot 存一份 {相对路径: sha256};diff 拿旧快照与当前状态比,
输出新增/删除/改动的相对路径。零依赖,不读墙钟。

存在的理由:P5「零权威」原先只查了「没有裁决署名是模型名」,那只证明没人
把模型名填进 adjudicator。真要证的是 ADK 那一趟只碰了 vision/ 与
agent_calls/,账本、门禁报告、快照一个字节没动。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def snapshot(run_dir: Path) -> dict[str, str]:
    run_dir = Path(run_dir)
    out = {}
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(run_dir).as_posix()
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def diff(before: dict[str, str], after: dict[str, str]) -> dict:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(k for k in set(before) & set(after)
                      if before[k] != after[k])
    return {"added": added, "removed": removed, "modified": modified,
            "changed": sorted(added + removed + modified)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("snapshot", "diff"))
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--before", type=Path, help="diff 用:之前那份快照")
    args = ap.parse_args()
    if args.command == "snapshot":
        payload = snapshot(args.run_dir)
    else:
        if args.before is None:
            raise SystemExit("diff 需要 --before")
        payload = diff(json.loads(args.before.read_text(encoding="utf-8")),
                       snapshot(args.run_dir))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps(payload if args.command == "diff"
                     else {"files": len(payload)},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
