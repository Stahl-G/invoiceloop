"""vision-ingest:整页渲染 → 读图模型作答 → `vision/answers6.<tag>.tsv`。

packet 规格原样搬自 dws-derisk vision_eval6.py 第六轮(2026-08-03 规格挖掘,
逐项从代码抄回):DPI 150 全页渲染、五条纪律的 prompt、tsv 列序、
ABSTAIN 约定、空值=弃权。两处必要的适配(round6 是 agentic 包,这里是
单文档 API 调用):文件引用改成内联说明;一次调用带**一份**文档的全部页
(纪律 5 本来就禁止拼图与跨文档)。

宪章位置:模型只写 tsv(草稿),进不进账本由冻结事务与门禁决定;
tsv 经 snapshot 的 answers6 glob 进输入指纹 —— 改了作答 = 新 run 代。
断点续跑:已有页图不重渲,tsv 里已有该文档的行不重问。
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from .fields import FIELD_KINDS
from .ingest import discover

#: 默认读者与显示名(tag D ≡ kimi-k3;自定义模型请换 --tag,别让显示名撒谎)
DEFAULT_MODEL = "kimi-k3"
API_VERSION = "2023-06-01"

#: 本地凭证文件(0600,永不进仓库):env 缺省时从这里补,三行 KEY=VALUE
VISION_ENV = Path("~/.config/invoiceloop/vision.env").expanduser()

_FIELDS = sorted(FIELD_KINDS)


def _credentials() -> tuple[str | None, str, str]:
    """(api_key, base_url, model)。env 优先,本地凭证文件兜底;
    base_url/model 也走 env(代理兼容层,如 ANTHROPIC_BASE_URL)。"""
    file_vars: dict[str, str] = {}
    if VISION_ENV.exists():
        for line in VISION_ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                file_vars[k.strip()] = v.strip()

    def get(*names: str) -> str | None:
        for name in names:
            value = os.environ.get(name) or file_vars.get(name)
            if value:
                return value
        return None

    key = get("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
    base = (get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
    model = (get("ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
                 "ANTHROPIC_DEFAULT_SONNET_MODEL",
                 "ANTHROPIC_DEFAULT_HAIKU_MODEL") or DEFAULT_MODEL)
    return key, base, model

#: prompt:第六轮 READER_DOC 的五条纪律逐字保留(那是被测过的部分),
#: 文件引用改内联,输出格式改成四列(调用方自己补 doc 列)
_PROMPT = """# 读者任务:从整页发票图上读出指定字段的值

你会拿到一份发票的全部整页扫描图({n_pages} 页,按页码顺序),以及要读的字段列表。
你的任务是把图上印着的值抄下来。**只做这一件事。**

## 要读的字段(每行一个,全部回答)

{fields}

## 输出格式

每行一个字段,恰好四列,制表符(TAB)分隔。**不要表头,不要任何多余文字。**

field<TAB>value<TAB>printed_label<TAB>note

- `value` — 值,**照抄纸面**,连同小数点、逗号、货币符号
- `printed_label` — 该值旁边**印着的标签原文**(如 `Total Due:`、`Gross Amt:`);
  没有可见标签填 `NONE`
- `note` — 可选说明;没有就留空(行尾仍是 TAB)

## 五条纪律

**1. 抄,不要算,不要推。**
不要把 net 加 vat 得出 gross,不要换算货币,不要从别处推断。只写你看见的字符。

**2. 分清"合计"与"明细行"。**
整页上有很多数字,包括每一条明细。要的是该字段的**合计值**,不是某一行的金额。
分不清就按第 3 条弃权,并在 `note` 里说明"分不清合计与明细"。

**3. 不确定就写 `ABSTAIN`,不要猜。**
图糊了、字段不在页上、有多个候选值分不清 —— `value` 填 `ABSTAIN`,`note` 说明原因。

> `ABSTAIN` 是**正确且被预期**的答案。猜一个值会污染结果;弃权不会。
> **不要为了填满表格而猜。**

**4. 按图上的标签走,不要按你以为的行业惯例走。**
如果图上印着 `Gross` 的那个数比印着 `Net` 的小,就照抄,不要"纠正"它。
`printed_label` 这一列存在的意义就是让下游能看出这种情况。

**5. 只读这一份文档,不要跨文档联想,也不要联网检索。**"""


def _tsv_path(workspace: Path, tag: str) -> Path:
    return Path(workspace) / "vision" / f"answers6.{tag}.tsv"


def _answered_docs(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.split("\t")[0] for line in
            path.read_text(encoding="utf-8").splitlines()[1:] if line.strip()}


def _parse_rows(text: str, doc_id: str) -> list[list[str]]:
    """模型输出 → (doc, field, value, printed_label, note) 行。

    只认首列是合法字段名的行(模型夹带散文时丢弃);没答的字段补空值行 ——
    空值在下游就是弃权(规格:blank = abstained),不藏漏答。
    """
    by_field: dict[str, list[str]] = {}
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0].strip() in FIELD_KINDS:
            field = cols[0].strip()
            by_field[field] = [
                doc_id, field,
                cols[1].strip() if len(cols) > 1 else "",
                cols[2].strip() if len(cols) > 2 else "",
                cols[3].strip() if len(cols) > 3 else "",
            ]
    return [by_field.get(field, [doc_id, field, "", "", ""]) for field in _FIELDS]


def read_doc(doc_id: str, pages: list[Path], *, model: str, api_key: str,
             base_url: str | None = None, _post=None) -> str:
    """一份文档的全部页 → 一次 messages 调用 → 模型的 tsv 文本。"""
    import requests

    content = [
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/png",
                    "data": base64.b64encode(p.read_bytes()).decode()}}
        for p in pages
    ]
    content.append({"type": "text", "text": _PROMPT.format(
        n_pages=len(pages), fields=", ".join(_FIELDS))})
    post = _post or requests.post
    resp = post(
        (base_url or "https://api.anthropic.com") + "/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": API_VERSION,
                 "content-type": "application/json"},
        json={"model": model, "max_tokens": 4096,
              "messages": [{"role": "user", "content": content}]},
        timeout=300,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"读图 API {resp.status_code}:{resp.text[:300]}")
    return "".join(block.get("text", "")
                   for block in resp.json().get("content", []))


def cmd_vision(workspace: Path, *, tag: str = "D", model: str | None = None,
               api_key: str | None = None, _post=None) -> dict:
    """workspace 的全部文档 → 读图作答 tsv。缺 key = typed unavailable,不藏。"""
    workspace = Path(workspace)
    cred_key, base_url, cred_model = _credentials()
    key = api_key or cred_key
    model = model or cred_model
    if not key:
        raise SystemExit(
            "读图需要 ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN(或写进 "
            f"{VISION_ENV})—— 没有它读图步不可用,"
            "按宪章四这是「跑不了」,不是「跳过」"
        )
    docs = discover(workspace)
    if not docs:
        raise SystemExit(f"输入契约:{workspace}/input/pdfs/ 里没有 .pdf 文件")

    from .evidence import render_pages

    tsv = _tsv_path(workspace, tag)
    tsv.parent.mkdir(parents=True, exist_ok=True)
    done = _answered_docs(tsv)
    pages_dir = workspace / "vision" / "pages"
    summary = {"docs": len(docs), "read": 0, "skipped": 0,
               "abstained_fields": 0, "failed": []}
    new_lines: list[str] = []
    for doc_id, pdf in docs.items():
        if doc_id in done:
            summary["skipped"] += 1
            continue
        try:
            if not list(pages_dir.glob(f"{doc_id}-*.png")):
                render_pages(pdf, pages_dir)
            pages = sorted(pages_dir.glob(f"{doc_id}-*.png"))
            text = read_doc(doc_id, pages, model=model, api_key=key,
                            base_url=base_url, _post=_post)
            rows = _parse_rows(text, doc_id)
            summary["abstained_fields"] += sum(
                1 for r in rows if not r[2] or r[2].upper() == "ABSTAIN")
            new_lines.extend("\t".join(r) for r in rows)
            done.add(doc_id)
            summary["read"] += 1
        except Exception as exc:  # noqa: BLE001 —— 记失败,不中断整批
            summary["failed"].append({"doc_id": doc_id, "error": repr(exc)})
    # 只追加,不重写:没有新行就一个字不动(续跑不许把已有作答截掉)
    if new_lines:
        needs_header = not tsv.exists() or tsv.stat().st_size == 0
        with tsv.open("a", encoding="utf-8") as fh:
            if needs_header:
                fh.write("doc\tfield\tvalue\tprinted_label\tnote\n")
            for line in new_lines:
                fh.write(line + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary
