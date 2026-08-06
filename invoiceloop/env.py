"""统一凭证入口:项目根一个 `.env`,DWS / 读图 / 签名 / 顾问层都从这里取。

在这之前有四套各找各的:`DWS_API_KEY` 只认进程环境、读图另有
`~/.config/invoiceloop/vision.env`、seal 认 `NUTRIENT_API_KEY`、
heldout 认 `DWS_API_KEYS` 或另一个文件。配一次跑不通三次是必然的。

纪律(和原来一样,一条没松):

- **进程环境永远优先**,`.env` 只补缺 —— 免得文件里的旧值悄悄盖掉你刚
  export 的临时 key;
- **不写回 `os.environ`**。注入全局环境会让「这个值哪来的」变得不可回答,
  也会让测试互相污染。取值一律走 `get()`;
- `.env` 已在 `.gitignore` 里;权限不是 0600 时 `doctor` 会说,但不阻断 ——
  报告缺口,不替人做决定(宪章四);
- 值**永不落进任何工件**:run 目录、bundle、日志里都不出现 key 本身,
  只出现「有没有」。
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILENAME = ".env"
#: 旧的读图专用凭证文件,继续认(换机的人不该因为升级就跑不了),
#: 但优先级最低 —— 项目 .env 是新的单一入口
LEGACY_VISION_ENV = Path("~/.config/invoiceloop/vision.env").expanduser()

#: 各用途的键名别名表,从高到低。写在一处,免得散在四个模块里各写各的
ALIASES: dict[str, tuple[str, ...]] = {
    "dws": ("DWS_API_KEY",),
    "dws_pool": ("DWS_API_KEYS",),
    "nutrient": ("NUTRIENT_API_KEY", "DWS_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    "anthropic_base": ("ANTHROPIC_BASE_URL",),
    # ANTHROPIC_MODEL 排第一:它是用户直接指定模型的那个变量。2026-08-06
    # 之前它不在表里 —— .env 里写了也不生效,实际读到的是宿主会话中的
    # ANTHROPIC_DEFAULT_SONNET_MODEL,于是「我配的模型」与「真正被调的
    # 模型」是两个东西,而且不报错(实测:配 mimo-v2.5,读到 deepseek)。
    "anthropic_model": ("ANTHROPIC_MODEL",
                        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
                        "ANTHROPIC_DEFAULT_SONNET_MODEL",
                        "ANTHROPIC_DEFAULT_HAIKU_MODEL"),
}


#: 关掉文件查找的逃生阀。测试套件在仓库里跑,而仓库根往往就放着开发者
#: 真实的 `.env` —— 不关掉的话,「缺 key 该报错」这类用例会读到真凭证而
#: 变绿(2026-08-06 实测:test_missing_key_is_typed_unavailable 就这么假绿过),
#: 更糟的是可能真的花掉 API 额度。conftest 默认置位。
DISABLE_VAR = "INVOICELOOP_NO_DOTENV"


def _files_disabled() -> bool:
    return os.environ.get(DISABLE_VAR, "") not in ("", "0")


def find_env_file(start: Path | str | None = None) -> Path | None:
    """从 start(默认 cwd)向上找 `.env`,到文件系统根为止。

    向上找是为了 workspace 在子目录时也能用到项目根那一份;
    找到第一个就停,不合并多份 —— 两份 .env 谁赢会变成玄学。
    """
    if _files_disabled():
        return None
    here = Path(start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def parse_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE,一行一个。`#` 开头是注释;值两侧的引号剥掉。

    解析失败的行**跳过并忽略**,不抛 —— 凭证文件里一行手滑不该让整条
    命令挂掉;真正缺 key 的时候调用方会报得很清楚。
    """
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def file_vars(workspace: Path | str | None = None) -> dict[str, str]:
    """`.env`(项目根,或 workspace 起向上找)+ 旧 vision.env 的合并视图。

    项目 `.env` 覆盖旧文件 —— 迁移期两份都在时,新的说了算。
    """
    merged: dict[str, str] = {}
    if _files_disabled():
        return merged
    if LEGACY_VISION_ENV.exists():
        merged.update(parse_env_file(LEGACY_VISION_ENV))
    found = find_env_file(workspace)
    if found is not None:
        merged.update(parse_env_file(found))
    return merged


def get(*names: str, workspace: Path | str | None = None) -> str | None:
    """按 names 顺序取第一个非空值:进程环境 → .env → 旧 vision.env。"""
    variables = file_vars(workspace)
    for name in names:
        value = os.environ.get(name) or variables.get(name)
        if value:
            return value
    return None


def credential(purpose: str, *, workspace: Path | str | None = None) -> str | None:
    """按用途取凭证(别名表见 ALIASES)。未知用途直接抛,不静默返回 None。"""
    if purpose not in ALIASES:
        raise KeyError(f"未知凭证用途 {purpose!r};已知:{sorted(ALIASES)}")
    return get(*ALIASES[purpose], workspace=workspace)


def status(workspace: Path | str | None = None) -> dict:
    """给 doctor 用:**只报有没有与来自哪里,永不回显值本身。**"""
    path = find_env_file(workspace)
    variables = file_vars(workspace)
    mode = None
    if path is not None:
        try:
            mode = oct(path.stat().st_mode & 0o777)
        except OSError:
            mode = None
    present = {}
    for purpose, names in ALIASES.items():
        source = None
        for name in names:
            if os.environ.get(name):
                source = "env"
                break
            if variables.get(name):
                source = "file"
                break
        present[purpose] = source
    return {
        "env_file": str(path) if path else None,
        "env_file_mode": mode,
        "legacy_vision_env": (str(LEGACY_VISION_ENV)
                              if LEGACY_VISION_ENV.exists() else None),
        "credentials": present,
    }
