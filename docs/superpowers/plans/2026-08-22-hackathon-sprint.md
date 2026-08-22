# 双黑客松冲刺 实施计划(2026-08-22)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在两个黑客松截止前,拿到两条冻结证据 —— 窄放行契约在**未曝光** 200 份上的零触达率,以及一个 agent 以协议内一等公民身份参与的 20 份人工行走 —— 然后用它们收材料。

**Architecture:** 两条证据线共用一次提取。资格轮先抽 200 份从未被碰过的 DocILE 文档、跑 400 次双模式 DWS 调用,再零 API 地把四个路由臂投影出来;ADK 行走从这 200 份里确定性抽 20 份,建议全部**走前预生成并冻结成工件**,账本每槽记下当时屏幕上那条建议出自哪份工件、哪个模型。新代码集中在四处:抽样器(`heldout.py`)、名单过滤(`doctouch_arms.py`)、溯源字段(`adjudicate.py` + 新模块 `suggest_provenance.py`)、工作台隐藏字段(`workbench.py`)。其余全是搬运既有实现。

**Tech Stack:** Python 3(仓库自带 `.venv`)、pytest、Nutrient DWS 抽取 API、google-adk + Gemini(顾问层)、DocILE 校准语料(`~/Developer/dws-derisk/data/docile/`)。

**Spec:** `docs/superpowers/specs/2026-08-21-hackathon-sprint-design.md`

---

## 与 spec 的两处偏差(执行前先读)

spec 是设计,这里是核过实现之后的实施计划。两处数字/机制与 spec 不同,**以本计划为准**:

1. **未曝光池是 4,831 份,不是 spec 写的 5,020。** spec 算的是 `5,680 − 560 − 100`,漏了 `heldout_pool()` 自己的门槛:只收 ≥4 个记分字段标注的文档、并排除校准 160 份,于是 5,680 → 5,331;再减曝光清单 560 → 4,931;再减 SEALED-4 已抽的 100 → **4,831**。实测命令见 Task 1 Step 2。抽 200 份绰绰有余,结论不变。
2. **`doctouch_arms.py` 不能直接复用。** spec 说 `discover_dual_mode()` 会自动发现新 raw 目录 —— 会,但它同时发现**旧的 660 份已曝光文档**,四臂会跑成 860 份并把结果当成「未曝光数字」报出去。必须加 `--doc-list` 名单过滤,缺件即阻断(Task 2)。

另外两条核实结论,让计划比 spec 更省事:

- **不需要 OCR 步骤。** 4,831 份全部已有 pdf + 词级 OCR(实测 missing 0/0),资格轮的全部 API 花费就是那 400 次抽取。
- **不需要并发。** `heldout.cmd_extract` 是串行的,400 次 × ~10.5s ≈ 70–90 分钟,低于 spec 给的 3h 上限。spec 的「并发 ≤ 4」是不必要的新机制(GOAL.md 五:少造机制),不做。

时间线整体比 spec 晚一天(spec 的 D1 是 8/21,实际从 8/22 起),缓冲仍够:8/30 前交 ATA,9/1 交 Nutrient。

---

## 文件结构

**新建**

| 路径 | 职责 |
|---|---|
| `invoiceloop/suggest_provenance.py` | 建议工件溯源:读 `<run>/vision/suggestion_provenance.json`,把「哪些读者在这一槽出过声」映射成(工件哈希, 模型 id) |
| `scripts/suggest_provenance_freeze.py` | 建议预生成之后冻结溯源文件:逐份读法算 sha256,写盘 |
| `scripts/qual_walk_plan.py` | 从资格集 200 份的路由报告里抽 20 份行走集(最小哈希,只取人队列 ≥1 槽) |
| `scripts/qual_adk_walk_setup.py` | 装配行走工作区、跑 HAR-0023 流水线(复用 `doctouch_arms.assemble`) |
| `scripts/qual_walk_analyze.py` | 行走结果 P1–P5 对照 |
| `docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md` | 资格轮协议正文(冻结先于任何调用) |
| `docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md` | 行走协议正文(冻结先于任何裁决) |
| `docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md` | 资格轮结果 |
| `docs/QUAL_ADK_WALK_RESULTS_2026-08-25.md` | 行走结果 |
| `tests/test_qualify.py` | 资格池/抽样器测试 |
| `tests/test_doctouch_arms_doclist.py` | 名单过滤测试 |
| `tests/test_suggest_provenance.py` | 溯源模块 + 账本字段 + 工作台隐藏字段测试 |
| `tests/test_lint_release_profile.py` | lint 回归:机器不许 propose `release_profile` |

**修改**

| 路径 | 改什么 |
|---|---|
| `invoiceloop/heldout.py` | 追加 `QUAL_CONTEXTS` / `qual_pool()` / `qual_list()` / `cmd_plan_qual()` |
| `invoiceloop/__main__.py` | 追加 `qualify plan` / `qualify extract` 子命令 |
| `scripts/doctouch_arms.py` | 追加 `select_sources()` 与 `--doc-list` |
| `invoiceloop/adjudicate.py` | `append_adjudication` 追加 `suggestion_artifact_sha256` / `suggestion_model` |
| `invoiceloop/workbench.py` | `RunCtx` 载入溯源表;`_decide_form` 多写两个隐藏字段;`/decide` 透传 |
| `README.md` | 「For judges」三命令 quickstart + 新数字 |
| `DISCLOSURE.md` | 赛期内模块清单补 doctouch / release_profile / qual 新增 |
| `docs/RUBRIC_V01_SCORE_2026-08-06.md` | 不改;新自评另开一份 |

---

## Phase A —— 资格集确认轮(Nutrient 头牌)

### Task 1: 资格池与最小哈希抽样

**Files:**
- Modify: `invoiceloop/heldout.py`(在 `cmd_plan_sealed` 之后、`_load_keys` 之前插入新的 QUALIFY 段)
- Modify: `invoiceloop/__main__.py:16-18`(导入)、`:115-136` 附近(parser)、`:339-354`(dispatch)
- Test: `tests/test_qualify.py`

- [ ] **Step 1: 写失败的测试**

新建 `tests/test_qualify.py`:

```python
"""资格轮抽样测试:池里不许有任何被碰过的文档,名单必须第三方可复算。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from invoiceloop import heldout
from invoiceloop.ocr import corpus_available, derisk_root

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
class TestQualPool:
    def test_pool_excludes_every_document_that_was_ever_touched(self):
        """池里混进一份跑过的文档 = 「未曝光」这个头条主张直接是假的。"""
        from doctouch_arms import discover_dual_mode

        pool = set(heldout.qual_pool())
        manifest = {
            e["doc_id"] for e in json.loads(
                (REPO / "docs" / "development_exposure_manifest.json")
                .read_text(encoding="utf-8"))["doc_ids"]}
        sealed4 = set(json.loads(
            (REPO / "docs" / "sealed4_doc_list.json")
            .read_text(encoding="utf-8"))["doc_ids"])
        on_disk = set(discover_dual_mode())
        assert not pool & manifest, "开发期曝光清单里的文档进了资格池"
        assert not pool & sealed4, "SEALED-4 已抽的 100 份进了资格池"
        assert not pool & on_disk, "盘上已有双模式响应的文档进了资格池"

    def test_pool_members_all_have_pdf_and_word_ocr(self):
        """缺 OCR 的文档会被 doctouch_arms.assemble 静默剔掉 —— 报告仍写
        n=200,实际测了更少。所以进池就必须装得起来。"""
        root = derisk_root() / "data" / "docile"
        for doc in heldout.qual_list(20):
            assert (root / "pdfs" / f"{doc}.pdf").is_file(), doc
            assert (root / "ocr" / f"{doc}.json").is_file(), doc


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
class TestQualList:
    def test_list_is_recomputable_by_a_third_party(self):
        """预注册的意义全在这条:拿到池和盐,任何人都能算出同一份 200。"""
        ids = heldout.qual_list(200)
        salt = heldout.QUAL_CONTEXTS[heldout.DEFAULT_QUAL_CONTEXT]
        expected = sorted(sorted(
            heldout.qual_pool(),
            key=lambda d: hashlib.sha256(
                f"{salt}|{d}".encode("utf-8")).hexdigest())[:200])
        assert ids == expected
        assert len(set(ids)) == 200

    def test_unknown_context_is_refused(self):
        """盐是协议的一部分。打错语境应当报错,不该悄悄用默认盐抽一份别的。"""
        with pytest.raises(ValueError, match="未知资格语境"):
            heldout.qual_list(10, context="qual-narrow-v99")


@pytest.mark.skipif(not corpus_available(), reason="校准档案不在")
def test_plan_writes_the_list_before_any_call(tmp_path):
    """落盘即预注册:名单、池摘要、盐语境必须在调用之前就在盘上。"""
    ids = heldout.cmd_plan_qual(tmp_path, n=5)
    payload = json.loads((tmp_path / "doc_list.json").read_text(encoding="utf-8"))
    assert payload["doc_ids"] == ids
    assert payload["context"] == heldout.DEFAULT_QUAL_CONTEXT
    assert payload["doc_ids_sha256"] == heldout.doc_ids_line_digest(ids)
    assert payload["pool_sha256"] == heldout.doc_ids_line_digest(heldout.qual_pool())
    assert not list((tmp_path / "raw").glob("*.json")), "plan 阶段不许有任何响应"
```

- [ ] **Step 2: 跑测试确认失败,并核实池大小**

```bash
.venv/bin/python -m pytest tests/test_qualify.py -x -q
```
预期:`AttributeError: module 'invoiceloop.heldout' has no attribute 'qual_pool'`

同时把 spec 里那个 5,020 的算术核掉:

```bash
.venv/bin/python -c "
import json, pathlib
from invoiceloop.heldout import heldout_pool, sealed_pool
s4 = set(json.loads(pathlib.Path('docs/sealed4_doc_list.json').read_text())['doc_ids'])
print('heldout_pool', len(heldout_pool()))
print('sealed_pool ', len(sealed_pool()))
print('minus sealed4', len([d for d in sealed_pool() if d not in s4]))
"
```
预期输出:
```
heldout_pool 5331
sealed_pool  4931
minus sealed4 4831
```

- [ ] **Step 3: 写实现 —— heldout.py 的 QUALIFY 段**

在 `invoiceloop/heldout.py` 中 `cmd_plan_sealed` 函数结束之后、`def _load_keys()` 之前插入:

```python
# ----------------------------------------------------------------- QUALIFY

#: 资格轮抽样盐。与 SEALED 不同,这里**不需要** drand:池里没有任何一份
#: 跑过结果,挑盐挑不出好看的样本。盐只承担确定性与第三方可复算。
QUAL_CONTEXTS = {
    "qual-narrow-v1": "invoiceloop-qual-narrow-v1",
}
DEFAULT_QUAL_CONTEXT = "qual-narrow-v1"

#: SEALED-4 抽走的 100 份不在 development_exposure_manifest 里(它们是
#: 「已抽、已跑、另行记账」的一类),但双模式响应确确实实在盘上,
#: 不排除就等于把已知答案混进「未曝光」的头条数字。
SEALED4_LIST = (Path(__file__).resolve().parent.parent
                / "docs" / "sealed4_doc_list.json")


@lru_cache(maxsize=1)
def qual_pool() -> tuple[str, ...]:
    """资格池:sealed_pool 再减 SEALED-4 名单,且 pdf 与词级 OCR 齐全。

    OCR 齐全是硬条件不是装饰:doctouch_arms.assemble 缺 OCR 就把该份记进
    missing 并从 doc_ids 里剔掉 —— 样本静默缩水,而报告照写 n=200。
    """
    sealed4 = set(json.loads(
        SEALED4_LIST.read_text(encoding="utf-8"))["doc_ids"])
    root = derisk_root() / "data" / "docile"
    out = []
    for doc in sealed_pool():
        if doc in sealed4:
            continue
        if not (root / "pdfs" / f"{doc}.pdf").is_file():
            continue
        if not (root / "ocr" / f"{doc}.json").is_file():
            continue
        out.append(doc)
    return tuple(sorted(out))


def qual_list(n: int = 200, *,
              context: str = DEFAULT_QUAL_CONTEXT) -> list[str]:
    """最小哈希抽样:按 sha256(「盐|doc_id」)升序取前 n 份,再按 id 排序。

    换掉 sealed 的 random.sample 只为一件事:第三方拿到池和盐就能用四行
    脚本复算,不必信任我们的 PRNG 版本。
    """
    if context not in QUAL_CONTEXTS:
        raise ValueError(f"未知资格语境:{context};允许 {sorted(QUAL_CONTEXTS)}")
    salt = QUAL_CONTEXTS[context]
    pool = qual_pool()
    if len(pool) < n:
        raise RuntimeError(f"资格池只有 {len(pool)} 份,不足 {n}")
    ranked = sorted(pool, key=lambda d: hashlib.sha256(
        f"{salt}|{d}".encode("utf-8")).hexdigest())
    return sorted(ranked[:n])


def cmd_plan_qual(workspace: Path, *, n: int = 200,
                  context: str = DEFAULT_QUAL_CONTEXT) -> list[str]:
    """资格集名单落盘 —— 先于任何调用,落盘即预注册。"""
    workspace = prepare_workspace(workspace)
    pool = qual_pool()
    ids = qual_list(n, context=context)
    payload = {
        "n": n,
        "pool_size": len(pool),
        "pool_min_fields": POOL_MIN_FIELDS,
        "exclusion": "docs/development_exposure_manifest.json 全量补集,"
                     "再减 docs/sealed4_doc_list.json;"
                     "并要求 pdf 与词级 OCR 齐全",
        "sampling": f"min-hash:sha256(「{QUAL_CONTEXTS[context]}|」+ doc_id) "
                    f"升序取前 {n}",
        "context": context,
        "pool_sha256": doc_ids_line_digest(pool),
        "doc_ids_sha256": doc_ids_line_digest(ids),
        "doc_ids": ids,
    }
    (workspace / "doc_list.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"pool={payload['pool_size']}  qual n={n}  context={context}")
    print(f"pool_sha256={payload['pool_sha256']}")
    print(f"doc_ids_sha256={payload['doc_ids_sha256']}")
    print(f"名单已落盘:{workspace / 'doc_list.json'} —— 先提交,再调用")
    return ids
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_qualify.py -q
```
预期:`5 passed`

- [ ] **Step 5: 接 CLI**

`invoiceloop/__main__.py` 第 16–18 行那组导入之后追加两行:

```python
from .heldout import DEFAULT_QUAL_CONTEXT as _DEFAULT_QUAL_CONTEXT
from .heldout import QUAL_CONTEXTS as _QUAL_CONTEXTS
```

在 `p_se`(sealed)那一段 parser 定义之后追加:

```python
    p_q = sub.add_parser(
        "qualify",
        help="资格集(未曝光确认轮;docs/QUALIFICATION_NARROW_PROTOCOL_*.md)")
    q_sub = p_q.add_subparsers(dest="qualify_command", required=True)
    p_qp = q_sub.add_parser("plan", help="最小哈希抽样并落盘名单(先于任何调用)")
    p_qp.add_argument("--workspace", type=Path, required=True)
    p_qp.add_argument("--n", type=int, default=200)
    p_qp.add_argument("--context", default=_DEFAULT_QUAL_CONTEXT,
                      choices=tuple(sorted(_QUAL_CONTEXTS)),
                      help=f"抽样盐语境(默认 {_DEFAULT_QUAL_CONTEXT})")
    p_qe = q_sub.add_parser("extract", help="按名单跑双模式,断点续跑,预算熔断")
    p_qe.add_argument("--workspace", type=Path, required=True)
    p_qe.add_argument("--budget", type=float, default=6000.0)
```

在 dispatch 的 `elif args.command == "sealed":` 分支之后追加:

```python
    elif args.command == "qualify":
        from . import heldout

        if args.qualify_command == "plan":
            heldout.cmd_plan_qual(args.workspace, n=args.n,
                                  context=args.context)
        else:
            heldout.cmd_extract(args.workspace, budget=args.budget)
```

- [ ] **Step 6: 验证 CLI 挂上了(不落盘到仓库里)**

```bash
.venv/bin/python -m invoiceloop qualify plan --workspace /tmp/qualcheck --n 3
```
预期:打印 `pool=4831  qual n=3  context=qual-narrow-v1`、两行 sha256、以及名单落盘路径。

```bash
rm -rf /tmp/qualcheck
```

- [ ] **Step 7: 提交**

```bash
git add invoiceloop/heldout.py invoiceloop/__main__.py tests/test_qualify.py
git commit -m "Add the qualification-round sampler: never-touched pool of 4,831 and a min-hash 200 that any third party can recompute from pool plus salt."
```

---

### Task 2: 四臂名单过滤 —— 缺件即阻断

**Files:**
- Modify: `scripts/doctouch_arms.py`(在 `discover_dual_mode` 之后加 `select_sources`;`main()` 加 `--doc-list`)
- Test: `tests/test_doctouch_arms_doclist.py`

- [ ] **Step 1: 写失败的测试**

新建 `tests/test_doctouch_arms_doclist.py`:

```python
"""四臂名单过滤:不带名单会把旧的 660 份已曝光文档一起测进去。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import doctouch_arms  # noqa: E402

A = "a" * 24
B = "b" * 24
C = "c" * 24


def test_filter_keeps_only_the_listed_documents():
    """不过滤的话资格轮会测 860 份(200 新 + 660 旧曝光),
    然后把它当作「未曝光」的零触达率报出去。"""
    sources = {A: Path("/raw/new"), C: Path("/raw/old")}
    assert doctouch_arms.select_sources(sources, [A]) == {A: Path("/raw/new")}


def test_missing_dual_mode_blocks_instead_of_shrinking_the_sample():
    """名单 200 份、盘上只有 187 份齐全 —— 静默丢掉 13 份,
    报告照写 n=200。硬约束:负面发现即阻断。"""
    sources = {A: Path("/raw/new")}
    with pytest.raises(SystemExit) as exc:
        doctouch_arms.select_sources(sources, [A, B])
    assert B in str(exc.value)


def test_no_list_means_every_dual_mode_document():
    """旧的 doctouch 复算路径不受影响。"""
    sources = {A: Path("/raw/old"), C: Path("/raw/old")}
    assert doctouch_arms.select_sources(sources, None) == sources
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_doctouch_arms_doclist.py -x -q
```
预期:`AttributeError: module 'doctouch_arms' has no attribute 'select_sources'`

- [ ] **Step 3: 写实现**

`scripts/doctouch_arms.py` 中,`discover_dual_mode()` 之后插入:

```python
def select_sources(sources: dict[str, Path],
                   requested: list[str] | None) -> dict[str, Path]:
    """按名单过滤双模式来源。缺件 = 阻断,不静默缩样本。

    资格轮必须带名单:discover_dual_mode 扫的是**盘上全部** raw 目录,
    资格集的响应一落盘,旧的 660 份已曝光文档就会跟着一起进臂 —— 报告
    会把 860 份的混合数字写成「未曝光」的结果。
    """
    if requested is None:
        return sources
    missing = [d for d in requested if d not in sources]
    if missing:
        raise SystemExit(json.dumps({
            "fatal": "名单里的文档缺双模式响应 —— 静默缩样本会让报告写着 "
                     "n=名单长度、实际测得更少",
            "requested": len(requested),
            "have": len(requested) - len(missing),
            "missing": sorted(missing),
        }, ensure_ascii=False, indent=1))
    return {d: sources[d] for d in requested}
```

`main()` 里,`ap.add_argument("--out", ...)` 之后加参数:

```python
    ap.add_argument("--doc-list", type=Path, default=None,
                    help="只测这份名单里的文档(资格轮:"
                         "runs/qual-narrow-<冻结日>/doc_list.json);"
                         "缺省 = 盘上全部双模式文档(旧 doctouch 复算路径)")
```

把 `sources = discover_dual_mode()` 那三行改成:

```python
    requested = (sorted(json.loads(
        args.doc_list.read_text(encoding="utf-8"))["doc_ids"])
        if args.doc_list else None)
    sources = select_sources(discover_dual_mode(), requested)
    doc_ids = sorted(sources)
    print(f"双模式齐全 {len(doc_ids)} 份"
          + (f"(名单 {args.doc_list})" if requested else ""), flush=True)
```

再把 `assemble` 之后那两行改成:

```python
    stats = assemble(ws, sources)
    print(f"  装齐 {stats['docs']};缺件 {len(stats['missing'])}", flush=True)
    if requested is not None and stats["missing"]:
        raise SystemExit(json.dumps({
            "fatal": "名单里的文档缺 pdf/ocr,装配不齐",
            "missing": stats["missing"]}, ensure_ascii=False, indent=1))
    doc_ids = [d for d in doc_ids if d not in set(stats["missing"])]
```

- [ ] **Step 4: 跑测试确认通过,并确认旧路径没坏**

```bash
.venv/bin/python -m pytest tests/test_doctouch_arms_doclist.py -q
```
预期:`3 passed`

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0, 'scripts')
from doctouch_arms import discover_dual_mode, select_sources
s = discover_dual_mode()
print('盘上双模式', len(s), '不带名单过滤后', len(select_sources(s, None)))
"
```
预期:`盘上双模式 660 不带名单过滤后 660`

- [ ] **Step 5: 提交**

```bash
git add scripts/doctouch_arms.py tests/test_doctouch_arms_doclist.py
git commit -m "Gate the arm runner on an explicit doc list: without it the qualification round would silently measure the 660 already-exposed documents alongside the new 200."
```

---

### Task 3: 冻结资格轮协议(先于任何 API 调用)

**Files:**
- Create: `docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md`
- Create: `runs/qual-narrow-2026-08-22/doc_list.json`(由命令生成)
- Create: `docs/qual_narrow_doc_list.json`(名单副本进仓库,与 `docs/sealed4_doc_list.json` 同款)

- [ ] **Step 1: 生成并落盘名单**

```bash
.venv/bin/python -m invoiceloop qualify plan \
  --workspace runs/qual-narrow-2026-08-22 --n 200
```
预期:`pool=4831  qual n=200  context=qual-narrow-v1`,后跟 `pool_sha256=…`、`doc_ids_sha256=…`、名单落盘路径。**把这两个 sha256 抄进下一步的协议正文。**

```bash
cp runs/qual-narrow-2026-08-22/doc_list.json docs/qual_narrow_doc_list.json
```

- [ ] **Step 2: 写协议正文**

新建 `docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md`。把 Step 1 打印的两个 sha256 填进 §2 的占位处 —— 这是本计划里唯一需要人抄数字的地方,因为它们要在提取之前就冻结:

```markdown
# QUALIFICATION_NARROW_2026-08-22 —— 资格集确认轮协议

冻结于本 commit,先于任何 API 调用。改了正文 = 臂不干净,照 HITL-narrow 先例声明。

## 1. 要回答什么

窄放行契约(`payment_required_v1`)在**从未被这个项目碰过**的文档上的零触达率。

`docs/DOCTOUCH_RESULTS_2026-08-18.md` §6 立的限定句是本轮的直接动因:
「在未曝光资格集给出同样闸定义下的数字之前,『窄放行降低打开张数』不得写成
产品能力。」08-18 那轮 660 份**全部是开发期曝光过的**,10.8% 因此只能当上限
参考,不能当产品能力。

## 2. 语料与抽样(可复算)

- 池 = `heldout_pool`(≥4 个记分字段标注、非校准 160)减 `development_exposure_manifest.json`
  全量(560),再减 `docs/sealed4_doc_list.json`(100),再要求 pdf 与词级 OCR 齐全。
- 池大小 = **4,831**。`pool_sha256` = `<抄 Step 1 输出>`
- 抽样 = 最小哈希:按 `sha256("invoiceloop-qual-narrow-v1|" + doc_id)` 升序取前 200,
  再按 doc_id 排序。语境 `qual-narrow-v1`,实现 `invoiceloop/heldout.py::qual_list`。
- 名单 200 份,`doc_ids_sha256` = `<抄 Step 1 输出>`,副本 `docs/qual_narrow_doc_list.json`。
- **为什么这轮的盐可以是常量**:SEALED 轮用 drand 是因为名单要在结果存在之前
  不可预知。这里池内 4,831 份**没有任何一份跑过**,挑盐挑不出好看的样本;
  换来的是第三方拿池和盐用四行脚本就能复算,不必信任我们的 PRNG 版本。
- 不分层抽取。strong / weak / none 三层用 `classify_broadcast_ocr` 事后分组报告
  (与 doctouch 08-18 同口径)。

复算命令(零 API):

    .venv/bin/python -c "
    import hashlib
    from invoiceloop.heldout import qual_pool
    salt = 'invoiceloop-qual-narrow-v1'
    print(sorted(sorted(qual_pool(), key=lambda d: hashlib.sha256(
        f'{salt}|{d}'.encode()).hexdigest())[:200])[:3])"

## 3. 提取(本轮唯一的 API 花费)

- 200 份 × 双模式(understand + agentic)= 400 次调用。
- 驱动 = `invoiceloop.heldout.cmd_extract`(串行、断点续跑、余额换 key、预算熔断)。
- 响应存 `runs/qual-narrow-2026-08-22/raw/`。
- 失败处理:该函数对网络异常退避重试 2 次、429 退避重试 2 次、401/402/403 换 key;
  仍失败则写进 `extract_summary.json` 的 `failures`。
  **`failures` 非空 = 本轮 `blocking_level: "blocking"`,结果文档头一句就写它,
  不跳过、不静默缩样本。**
- 不做并发。串行 400 次 ≈ 70–90 分钟,没必要为此造新机制。

## 4. 四臂与指标

| 臂 | harness | 闸 | 说明 |
|---|---|---|---|
| A | HAR-0001 | census | 结构性锚点,普查闸全挡 |
| B | HAR-0021 | census | 现役策略 |
| C | HAR-0021 投影 | payment_required_v1 | 同路由换闸,不重跑 |
| D | HAR-0023 | payment_required_v1 + `release_tier1_explicit: false` | 候选 |

- 运行:`scripts/doctouch_arms.py --out runs/qual-narrow-2026-08-22/doctouch
  --doc-list runs/qual-narrow-2026-08-22/doc_list.json`。**必须带 `--doc-list`** ——
  不带就会把盘上 660 份已曝光文档一起测进来。
- 指标定义不变:`release_profile.document_touch_metrics`,主终点 = **文档零触达**。
- 三层分开报,ALL 只作合计。真静默(`silent_absent_true`)与口径争议照登。

## 5. 预注册预测(错了照登)

| # | 预测 | 依据 |
|---|---|---|
| P1 | A 臂零触达 = 0% | 普查闸全挡,结构性锚点 |
| P2 | D 臂零触达落在 **5–20%** | doctouch 实测 10.8% 为中心的诚实先验;上一轮 20–35% 的预测错了,不重复那个错法 |
| P3 | C ≥ D | `release_tier1_explicit: false` 的 QA 探针只增触达 |
| P4 | 真静默 ≤ 3 | 不高于 doctouch 各臂 |
| P5 | 三闸全自动占比 15–19% | doctouch 盘上 17.1%,合取机制应复现 |

## 6. 结果语义与顺序纪律

- P2 成立 → 「窄放行降低打开张数」升级为可主张的产品能力,带新 n 与新数字,
  仍带 ARCHITECTURE §8 三条限定。不成立 → 照登,保留 08-18 的限定句。
  **两种结果都进提交叙事。**
- 顺序:先跑臂、算完 200 份的路由指标,人再碰任何一份。ADK 行走集从这 200 份里抽,
  但必须在路由指标算完之后 —— 行走不得污染路由数字。
- 两轮独立记账,数字不拼接。

## 7. 废臂条款

提取开始后改动以下任何一项 = 臂不干净,照实声明:抽样盐或语境、名单、
四臂的策略文件、`document_touch_metrics` 的定义、本协议正文。
```

- [ ] **Step 3: 确认名单落盘且 raw 为空(预注册的定义)**

```bash
.venv/bin/python -c "
import json, pathlib
p = pathlib.Path('runs/qual-narrow-2026-08-22')
d = json.loads((p / 'doc_list.json').read_text())
print('n =', len(d['doc_ids']), 'pool =', d['pool_size'])
print('raw 里的响应数 =', len(list((p / 'raw').glob('*.json'))))
"
```
预期:
```
n = 200 pool = 4831
raw 里的响应数 = 0
```

- [ ] **Step 4: 提交 —— 这一条 commit 必须先于任何提取**

```bash
git add docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md docs/qual_narrow_doc_list.json
git commit -m "Freeze the qualification-round protocol and its 200-document list before any extraction: pool 4,831 never-touched, min-hash sampling, five predictions on the record."
```

---

### Task 4: 跑 400 次提取(唯一 API 花费)

**Files:**
- Create: `runs/qual-narrow-2026-08-22/raw/*.json`(400 份响应)
- Create: `runs/qual-narrow-2026-08-22/extract_summary.json`

- [ ] **Step 1: 确认凭证在位(不回显值)**

```bash
.venv/bin/python -m invoiceloop doctor 2>&1 | grep -i "dws\|key"
```
预期:每项报「有没有、来自哪里」,**不回显值本身**。`DWS_API_KEY` 应显示存在且来自本项目 `.env`。

- [ ] **Step 2: 后台启动提取**

`cmd_extract` 的 key 轮换读 `DWS_API_KEYS`;新 token 在 `DWS_API_KEY` 里,要让它进轮换列表的第一位:

```bash
set -a && . ./.env && set +a && \
DWS_API_KEYS="$DWS_API_KEY,$DWS_API_KEYS" \
nohup .venv/bin/python -m invoiceloop qualify extract \
  --workspace runs/qual-narrow-2026-08-22 --budget 6000 \
  > runs/qual-narrow-2026-08-22/extract.log 2>&1 &
echo "pid $!"
```
预期:立刻返回一个 pid;日志每 20 份打一次进度。

- [ ] **Step 3: 等待并确认收尾**

```bash
tail -20 runs/qual-narrow-2026-08-22/extract.log
```
预期(约 70–90 分钟后)以一段 JSON 收尾:`{"done": 400, "skipped": 0, "failed": 0, ...}`。

中断了就重发 Step 2 的同一条命令 —— 已存 200 的 (doc, mode) 会被 skip。

- [ ] **Step 4: 阻断判定 —— failures 非空就停在这里**

```bash
.venv/bin/python -c "
import json, pathlib
s = json.loads(pathlib.Path(
    'runs/qual-narrow-2026-08-22/extract_summary.json').read_text())
print(json.dumps({k: s[k] for k in
                  ('done', 'skipped', 'failed', 'spent_estimate', 'keys_used')},
                 ensure_ascii=False))
if s['failed']:
    print('BLOCKING —— 失败明细必须进结果文档第一段:')
    print(json.dumps(s['failures'][:10], ensure_ascii=False, indent=1))
"
```
预期:`{"done": 400, "skipped": 0, "failed": 0, ...}`。

`failed > 0` 时**不要缩样本、不要补抽**:把 `failures` 原样带进 Task 5 的结果文档第一段,并在那里标 `blocking_level: "blocking"`。

- [ ] **Step 5: 确认双模式齐全 200 份**

```bash
.venv/bin/python -c "
import json, pathlib, sys
sys.path.insert(0, 'scripts')
from doctouch_arms import discover_dual_mode, select_sources
want = json.loads(pathlib.Path(
    'runs/qual-narrow-2026-08-22/doc_list.json').read_text())['doc_ids']
print('名单', len(want), '→ 过滤后', len(select_sources(discover_dual_mode(), want)))
"
```
预期:`名单 200 → 过滤后 200`(缺件会在这里 SystemExit,不会走到臂)。

- [ ] **Step 6: 提交存盘响应**

```bash
git add runs/qual-narrow-2026-08-22/extract_summary.json
git commit -m "Record the qualification-round extraction summary: 400 dual-mode calls over the 200 never-touched documents."
```

`raw/` 是否进仓库按仓库既有惯例走:

```bash
git check-ignore -v runs/qual-narrow-2026-08-22/raw/ || echo "raw 未被忽略 —— 照 sealed4 的先例决定是否入库"
```

---

### Task 5: 跑四臂并写结果文档

**Files:**
- Create: `runs/qual-narrow-2026-08-22/doctouch/doctouch_metrics.json`(由命令生成)
- Create: `docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md`

- [ ] **Step 1: 跑四臂(零 API)**

```bash
.venv/bin/python scripts/doctouch_arms.py \
  --out runs/qual-narrow-2026-08-22/doctouch \
  --doc-list runs/qual-narrow-2026-08-22/doc_list.json
```
预期:开头 `双模式齐全 200 份(名单 …/doc_list.json)`,然后逐臂跑,末尾一张表,每行是
`arm / gate / 层 / 零触达 / 队列槽 / 真静默`,四个臂各四层(strong/weak/none/ALL)。

- [ ] **Step 2: 把 P1–P5 的实测值抽出来**

```bash
.venv/bin/python -c "
import json, pathlib
m = json.loads(pathlib.Path(
    'runs/qual-narrow-2026-08-22/doctouch/doctouch_metrics.json').read_text())
print('n_docs', m['n_docs'], '分层', m['strata'])
for arm, rec in m['arms'].items():
    all_ = rec['metrics'].get('ALL', {})
    print(f\"{arm:36s} gate={rec['gate']:18s} \"
          f\"零触达 {all_.get('zero_touch_pct')}%  \"
          f\"真静默 {all_.get('silent_absent_true')}  \"
          f\"口径争议 {all_.get('caliber_disputes')}\")
"
```
预期:四行,A 臂 `零触达 0.0%`(P1),D 臂即 `HAR-0023` 的百分比落进 5–20 就是 P2 成立。

- [ ] **Step 3: 算 P5(三闸全自动占比)**

```bash
.venv/bin/python -c "
import json, pathlib
from invoiceloop.release_profile import PAYMENT_REQUIRED_V1
r = json.loads(pathlib.Path(
    'runs/qual-narrow-2026-08-22/doctouch/arms/HAR-0023/routing_report.json'
    ).read_text())
auto = {}
for row in r['routes']:
    if row['field'] in PAYMENT_REQUIRED_V1:
        auto.setdefault(row['doc_id'], []).append(
            row['route'] in ('auto_accept', 'auto_absent'))
full = sum(1 for v in auto.values() if len(v) == 3 and all(v))
print(f'三闸全自动 {full}/{len(auto)} = {100.0*full/max(len(auto),1):.1f}%')
"
```
预期:一行百分比。落在 15–19 就是 P5 成立。

- [ ] **Step 4: 写结果文档**

新建 `docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md`,骨架如下,方括号处填 Step 1–3 的实测值。**先写预测栏,再填实测栏,不许回改预测。**

```markdown
# QUALIFICATION_NARROW_2026-08-22 结果(未曝光资格集,n=200)

协议:`docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md`(冻结于提取之前)
数据:`runs/qual-narrow-2026-08-22/doctouch/doctouch_metrics.json`
复算:零 API。四臂全部从存盘响应投影,`--doc-list` 锁死这 200 份。

## 0. 阻断状态

`extract_summary.json`:done [填] / failed [填]。
[failed = 0 时写:无阻断。failed > 0 时把 failures 明细贴在这里,
并写明 `blocking_level: "blocking"` 与它对下面每个数字的影响。]

## 1. 这一轮跟 08-18 那轮差在哪

| | doctouch 2026-08-18 | 本轮 |
|---|---|---|
| n | 660 | 200 |
| 曝光状态 | **全部开发期曝光过** | **一份都没被碰过** |
| 抽样 | 盘上凡有双模式响应即入 | 未曝光池 4,831 最小哈希取 200 |
| 闸定义 | 同 | 同 |
| 指标 | 同 | 同 |

08-18 的 10.8% 只能当上限参考。本轮回答的是同一个问题在未曝光文档上的答案。

## 2. 预注册对照

| # | 预测 | 实测 | 判定 |
|---|---|---|---|
| P1 | A 臂零触达 = 0% | [填] | [成立 / 不成立] |
| P2 | D 臂零触达 5–20% | [填] | [成立 / 不成立] |
| P3 | C ≥ D | [填] | [成立 / 不成立] |
| P4 | 真静默 ≤ 3 | [填] | [成立 / 不成立] |
| P5 | 三闸全自动 15–19% | [填] | [成立 / 不成立] |

[逐条一句话说明。预测错了照登,不改预测、不补理由把它说圆。]

## 3. 四臂 × 三层

| 臂 | 闸 | 层 | 文档数 | 零触达 | 未决放行槽 | QA 探针槽 | 人队列槽 | 真静默 | 口径争议 |
|---|---|---|---|---|---|---|---|---|---|
[从 doctouch_metrics.json 逐行填,strong/weak/none/ALL 四层都要有]

## 4. 可以对外说的一句话

[P2 成立时:「在 200 份此前从未被本项目接触过的 DocILE 发票上,窄放行契约
(invoice_number / seller_name / amount_due 三字段)让 [X]% 的文档在路由阶段
无需任何人打开。」后面必须跟 ARCHITECTURE §8 的三条限定。]

[P2 不成立时:保留 08-18 §6 的限定句原文,并写明本轮实测值与它的关系。]

## 5. 这句话证明不了什么

- 不是「抽取更准了」。零触达是**路由时属性**,与抽取正确性无关。
- 不是「这三个字段一定是对的」。窄放行只承诺:这三个字段在本策略下达到了
  免复核的证据门槛;其余字段照旧进支持矩阵。
- DocILE 是一个语料。换域名、换版式、换语言,这个数字不迁移。
```

- [ ] **Step 5: 提交**

```bash
git add runs/qual-narrow-2026-08-22/doctouch/doctouch_metrics.json \
        docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md
git commit -m "Report the qualification round on 200 never-touched documents against its five pre-registered predictions."
```

---

## Phase B —— ADK×HITL 协议内行走(ATA 头牌)

一句话:agent(Gemini,走 ADK)以**协议内一等公民**身份参与人工行走 —— 建议从第一槽就在场、每条账本行带完整溯源、**零权威**(不能 accept / reject / 改任何闸)。

Task 6–7 是代码,Task 8–10 是跑轮。

### Task 6: 溯源字段进账本

**Files:**
- Modify: `invoiceloop/adjudicate.py:60-72`(正则)、`:94-152`(签名与校验)、`:256-282`(entry)
- Test: `tests/test_suggest_provenance.py`

- [ ] **Step 1: 写失败的测试**

新建 `tests/test_suggest_provenance.py`:

```python
"""建议工件溯源:账本每槽能不能说清「当时屏幕上那条建议出自哪份工件」。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoiceloop import adjudicate

SHA_A = "a" * 64
SHA_B = "b" * 64


def _kwargs(**over):
    base = dict(
        claim_id="CL-0001", doc_id="doc1", field="invoice_number",
        decision="accept", rationale="页面左上角",
        adjudicator="tester", decided_at="2026-08-24T10:00:00+00:00",
    )
    base.update(over)
    return base


class TestValidation:
    """校验在 append_adjudication 里,不需要 run 目录 —— 这些用例全部
    在 manifest 读取之前就该抛。"""

    def test_provenance_without_suggestion_seen_is_refused(self, tmp_path):
        """没展示过建议的槽带着工件哈希 = 账本在替一次没发生的展示背书。"""
        with pytest.raises(ValueError, match="必须与 suggestion_seen 同行"):
            adjudicate.append_adjudication(
                tmp_path, **_kwargs(),
                suggestion_artifact_sha256=SHA_A,
                suggestion_model="gemini-3.6-flash")

    def test_half_a_provenance_is_refused(self, tmp_path):
        """只有哈希没有模型 id,复算不出来 —— 半份溯源比没有更糟,
        它看起来像证据。"""
        with pytest.raises(ValueError, match="必须成对"):
            adjudicate.append_adjudication(
                tmp_path, **_kwargs(), suggestion_seen="agree:INV-1",
                suggestion_artifact_sha256=SHA_A)

    def test_non_sha256_artifact_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="sha256"):
            adjudicate.append_adjudication(
                tmp_path, **_kwargs(), suggestion_seen="agree:INV-1",
                suggestion_artifact_sha256="not-a-hash",
                suggestion_model="gemini-3.6-flash")

    def test_free_text_model_id_is_refused(self, tmp_path):
        """模型 id 是要拿来分组统计的。自由文本会让「哪个模型的建议被采纳」
        算不出来。"""
        with pytest.raises(ValueError, match="suggestion_model"):
            adjudicate.append_adjudication(
                tmp_path, **_kwargs(), suggestion_seen="agree:INV-1",
                suggestion_artifact_sha256=SHA_A,
                suggestion_model="gemini 3.6 flash（顾问）")

    def test_mismatched_hash_and_model_counts_are_refused(self, tmp_path):
        """两个读者的哈希配一个模型 id —— 对不齐就说不清哪个哈希属于谁,
        而「哪个模型的建议被采纳」正是靠这个配对算的。"""
        with pytest.raises(ValueError, match="条数必须相同"):
            adjudicate.append_adjudication(
                tmp_path, **_kwargs(), suggestion_seen="agree:INV-1",
                suggestion_artifact_sha256=f"{SHA_A},{SHA_B}",
                suggestion_model="gemini-3.6-flash")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_suggest_provenance.py -x -q
```
预期:`TypeError: append_adjudication() got an unexpected keyword argument 'suggestion_artifact_sha256'`

- [ ] **Step 3: 写实现 —— 正则**

`invoiceloop/adjudicate.py` 中 `_SUGGESTION_SEEN` 那个正则之后追加:

```python
#: 建议工件溯源(ADK 行走轮)。多读者按 tag 排序后逗号连接;单读者退化成单值。
#: 记的是**工件的哈希**不是建议的值 —— 值能从工件复算,哈希能证明工件没被改过。
_SUGGESTION_ARTIFACT = re.compile(r"[0-9a-f]{64}(?:,[0-9a-f]{64})*")
SUGGESTION_MODEL_MAX = 200
_SUGGESTION_MODEL = re.compile(r"[A-Za-z0-9._\-]+(?:,[A-Za-z0-9._\-]+)*")
```

- [ ] **Step 4: 写实现 —— 签名与校验**

`append_adjudication` 的签名里,`suggestion_seen: str | None = None,` 之后追加两行:

```python
    suggestion_artifact_sha256: str | None = None,
    suggestion_model: str | None = None,
```

docstring 末尾追加一段:

```python
    suggestion_artifact_sha256 / suggestion_model 可选,必须成对、且必须与
    suggestion_seen 同行:它们回答的是「一年后回看这条裁决,能不能重算出
    当时屏幕上那条建议」。工件哈希指向预生成并冻结的读法记录,模型 id 让
    「哪个模型的建议被采纳」可分组统计。
```

现有 `if suggestion_seen is not None:` 那个校验块之后追加:

```python
    if suggestion_artifact_sha256 is not None or suggestion_model is not None:
        if suggestion_seen is None:
            raise ValueError(
                "建议溯源字段必须与 suggestion_seen 同行 —— 没展示过建议的槽"
                "带着工件哈希,账本就在替一次没发生的展示背书")
        if suggestion_artifact_sha256 is None or suggestion_model is None:
            raise ValueError(
                "工件哈希与模型 id 必须成对 —— 半份溯源复算不出来,"
                "而它看起来像证据")
        if not _SUGGESTION_ARTIFACT.fullmatch(str(suggestion_artifact_sha256)):
            raise ValueError(
                "suggestion_artifact_sha256 必须是 sha256 十六进制串"
                "(多读者用逗号连接)")
        if len(str(suggestion_model)) > SUGGESTION_MODEL_MAX \
                or not _SUGGESTION_MODEL.fullmatch(str(suggestion_model)):
            raise ValueError(
                f"suggestion_model 只认 [A-Za-z0-9._-] 与逗号、且 ≤"
                f"{SUGGESTION_MODEL_MAX} 字 —— 自由文本会让「哪个模型的建议"
                f"被采纳」算不出来")
        if len(str(suggestion_artifact_sha256).split(",")) \
                != len(str(suggestion_model).split(",")):
            raise ValueError(
                "工件哈希与模型 id 的条数必须相同 —— 对不齐就说不清"
                "哪个哈希属于哪个模型")
```

- [ ] **Step 5: 写实现 —— entry**

`if suggestion_seen is not None: entry["suggestion_seen"] = suggestion_seen` 之后追加:

```python
            if suggestion_artifact_sha256 is not None:
                entry["suggestion_artifact_sha256"] = suggestion_artifact_sha256
            if suggestion_model is not None:
                entry["suggestion_model"] = suggestion_model
```

- [ ] **Step 6: 跑测试确认通过,并确认旧账本没坏**

```bash
.venv/bin/python -m pytest tests/test_suggest_provenance.py tests/test_adjudicate.py -q
```
预期:新文件 5 条全过,`test_adjudicate.py` 原有条数一条不少也全过 —— 两个新参数缺省 None,不改变任何旧行为。

- [ ] **Step 7: 提交**

```bash
git add invoiceloop/adjudicate.py tests/test_suggest_provenance.py
git commit -m "Let a ledger row name the suggestion artifact and model it was shown alongside, refusing half a provenance."
```

---

### Task 7: 溯源模块与工作台隐藏字段

**Files:**
- Create: `invoiceloop/suggest_provenance.py`
- Create: `scripts/suggest_provenance_freeze.py`
- Modify: `invoiceloop/workbench.py:1300-1320`(RunCtx)、`:2150-2160`(`_decide_form`)、`:3491`(`/decide`)
- Test: `tests/test_suggest_provenance.py`(追加)

- [ ] **Step 1: 写失败的测试(追加到 `tests/test_suggest_provenance.py` 末尾)**

```python
class TestSlotProvenance:
    def test_maps_readers_to_their_artifact_and_model(self):
        from invoiceloop import suggest_provenance

        prov = {"readers": {"adk-invoice": {
            "model": "gemini-3.6-flash", "docs": {"doc1": SHA_A}}}}
        assert suggest_provenance.slot_provenance(
            prov, "doc1", ["adk-invoice"]) == (SHA_A, "gemini-3.6-flash")

    def test_unknown_reader_yields_nothing_for_the_whole_slot(self):
        """一个读者查不到就整槽不给溯源。凑出来的半份会被当成完整证据读。"""
        from invoiceloop import suggest_provenance

        prov = {"readers": {"adk-invoice": {
            "model": "gemini-3.6-flash", "docs": {"doc1": SHA_A}}}}
        assert suggest_provenance.slot_provenance(
            prov, "doc1", ["adk-invoice", "triad"]) is None

    def test_document_without_a_frozen_reading_yields_nothing(self):
        """建议是走中途补生成的(废臂条款点名的那条),这里就查不到 ——
        查不到即无溯源,而不是编一个。"""
        from invoiceloop import suggest_provenance

        prov = {"readers": {"adk-invoice": {
            "model": "gemini-3.6-flash", "docs": {"doc1": SHA_A}}}}
        assert suggest_provenance.slot_provenance(
            prov, "doc2", ["adk-invoice"]) is None

    def test_digest_ignores_key_order_and_indentation(self):
        """工件哈希要能跨「重新排版过的同一份读法」保持稳定,
        否则每次改写盘缩进都会让全轮溯源对不上。"""
        from invoiceloop import suggest_provenance

        assert suggest_provenance.record_digest({"a": 1, "b": "x"}) == \
            suggest_provenance.record_digest({"b": "x", "a": 1})


def test_freeze_writes_a_digest_for_every_document_that_was_read(tmp_path):
    """P1 的前提:有建议工件的槽 100% 带溯源。工件里有的文档一个都不能漏。"""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import suggest_provenance_freeze as freeze

    run_dir = tmp_path / "run-0001"
    (run_dir / "vision").mkdir(parents=True)
    (run_dir / "vision" / "invoice_read.json").write_text(json.dumps({
        "advisory": True, "source": "adk_invoice_read",
        "model": "gemini-3.6-flash",
        "docs": {"doc1": {"seller_name": "ACME", "model": "gemini-3.6-flash"},
                 "doc2": {"seller_name": "BETA", "model": "gemini-3.6-flash"}},
        "failed": [],
    }), encoding="utf-8")

    freeze.freeze(run_dir, tag="adk-invoice", round_name="test-round",
                  frozen_at="2026-08-24T09:00:00+00:00")

    prov = json.loads((run_dir / "vision" / "suggestion_provenance.json")
                      .read_text(encoding="utf-8"))
    docs = prov["readers"]["adk-invoice"]["docs"]
    assert sorted(docs) == ["doc1", "doc2"]
    assert all(len(d) == 64 for d in docs.values())
    assert docs["doc1"] != docs["doc2"], "两份不同的读法不能算出同一个哈希"
    assert prov["prompt_digest"] and prov["schema_digest"]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_suggest_provenance.py -x -q -k "SlotProvenance or freeze"
```
预期:`ModuleNotFoundError: No module named 'invoiceloop.suggest_provenance'`

- [ ] **Step 3: 写 `invoiceloop/suggest_provenance.py`**

```python
"""建议工件溯源:每槽记「人看见的那条建议出自哪份工件、哪个模型」。

建议本身是显示层的东西(`vision/answers6.<tag>.tsv`),它不进冻结账本 ——
这是宪章一(单一写者)。溯源要解决的是另一个问题:一年后回看某条裁决,
能不能重算出当时屏幕上那条建议。所以记的是**工件的哈希**,不是建议的值:
值能从工件复算,哈希能证明工件没被改过。

查不到就整槽不给溯源。凑出来的半份会被下游当成完整证据读,那比没有更糟。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

FILENAME = "suggestion_provenance.json"


def record_digest(record: Mapping[str, Any]) -> str:
    """一份读法记录的 sha256:排序键、紧凑分隔符 —— 与写盘缩进无关。"""
    return hashlib.sha256(json.dumps(
        record, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def load(run_dir: Path) -> dict[str, Any] | None:
    """→ 溯源表;文件不在返回 None(没冻结过建议的 run 照常工作)。"""
    path = Path(run_dir) / "vision" / FILENAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def slot_provenance(prov: Mapping[str, Any] | None, doc_id: str,
                    readers: Sequence[str]) -> tuple[str, str] | None:
    """→ (逗号连接的工件哈希, 逗号连接的模型 id);任一读者查不到 → None。

    readers 是**这一槽上真正出过声**的读者 tag(workbench 的 ctx.vision
    键),不是全轮读者表 —— 溯源要对得上人当时看见的那条建议。
    """
    if not prov or not readers:
        return None
    table = prov.get("readers") or {}
    hashes: list[str] = []
    models: list[str] = []
    for tag in sorted(set(readers)):
        rec = table.get(tag)
        if not rec:
            return None
        digest = (rec.get("docs") or {}).get(doc_id)
        model = rec.get("model")
        if not digest or not model:
            return None
        hashes.append(str(digest))
        models.append(str(model))
    return ",".join(hashes), ",".join(models)
```

- [ ] **Step 4: 写 `scripts/suggest_provenance_freeze.py`**

```python
#!/usr/bin/env python3
"""建议预生成之后冻结溯源文件 —— 走前跑一次,走中途不跑。

读 `<run>/vision/invoice_read.json`,逐份读法算 sha256,连同全轮一份的
prompt / schema digest 写成 `<run>/vision/suggestion_provenance.json`。

已存在则拒绝覆盖:溯源文件被改写过,账本里已有的哈希就对不上了 ——
那正是废臂条款要挡的「走中途补生成建议」。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop import suggest_provenance  # noqa: E402
from invoiceloop.agents.invoice_read import (  # noqa: E402
    INVOICE_READ_SYSTEM, READ_USER_PROMPT, InvoiceReading, SUGGEST_TAG,
)


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def freeze(run_dir: Path, *, tag: str, round_name: str,
           frozen_at: str) -> Path:
    run_dir = Path(run_dir)
    out = run_dir / "vision" / suggest_provenance.FILENAME
    if out.exists():
        raise SystemExit(json.dumps({
            "fatal": "溯源文件已存在,拒绝覆盖 —— 账本里已有的哈希会对不上。"
                     "要重来就换一个 run。",
            "path": str(out),
        }, ensure_ascii=False, indent=1))
    packed = json.loads((run_dir / "vision" / "invoice_read.json")
                        .read_text(encoding="utf-8"))
    top_model = str(packed.get("model") or "")
    docs = {}
    for doc_id, rec in sorted((packed.get("docs") or {}).items()):
        docs[doc_id] = suggest_provenance.record_digest(rec)
    if packed.get("failed"):
        print(json.dumps({
            "warning": "有读法失败的文档 —— 它们没有工件,那些槽不会带溯源。"
                       "结果文档必须把这件事写出来,不能当成 100% 覆盖。",
            "failed": packed["failed"],
        }, ensure_ascii=False, indent=1), flush=True)
    payload = {
        "round": round_name,
        "frozen_at": frozen_at,
        "prompt_digest": _text_digest(INVOICE_READ_SYSTEM + "\n" + READ_USER_PROMPT),
        "schema_digest": _text_digest(json.dumps(
            InvoiceReading.model_json_schema(), sort_keys=True,
            ensure_ascii=False, separators=(",", ":"))),
        "readers": {tag: {
            "model": top_model,
            "artifact": "vision/invoice_read.json",
            "artifact_sha256": hashlib.sha256(
                (run_dir / "vision" / "invoice_read.json").read_bytes()).hexdigest(),
            "docs": docs,
        }},
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--tag", default=SUGGEST_TAG)
    ap.add_argument("--round", required=True, dest="round_name")
    ap.add_argument("--frozen-at", required=True,
                    help="ISO 8601;时间由人给,工件不读墙钟")
    args = ap.parse_args()
    path = freeze(args.run_dir, tag=args.tag, round_name=args.round_name,
                  frozen_at=args.frozen_at)
    prov = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps({
        "wrote": str(path),
        "tag": args.tag,
        "model": prov["readers"][args.tag]["model"],
        "docs": len(prov["readers"][args.tag]["docs"]),
        "prompt_digest": prov["prompt_digest"][:16] + "…",
        "schema_digest": prov["schema_digest"][:16] + "…",
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_suggest_provenance.py -q
```
预期:`10 passed`

- [ ] **Step 6: 接工作台 —— RunCtx 载入溯源表**

`invoiceloop/workbench.py` 的 `RunCtx` 里,`self.invoice_read: dict[str, dict] = {}` 那一段之前(即第 1300–1306 行那块 vision 载入之后)插入:

```python
        # 建议工件溯源(ADK 行走轮)。没冻结过就是 None,老 run 照常工作。
        from . import suggest_provenance as _sp

        self.suggest_provenance = _sp.load(self.dir)
```

- [ ] **Step 7: 接工作台 —— `_decide_form` 多写两个隐藏字段**

`_decide_form` 里那段 `sug_input` 的构造(`invoiceloop/workbench.py:2150-2160`)整段替换为:

```python
        sug_state, sug_value = self._vision_state(ctx, row)
        sug_input = ""
        if sug_state != "none":
            seen = f"{sug_state}:{sug_value}" if sug_value is not None else sug_state
            sug_input = (f'<input type="hidden" name="suggestion_seen" '
                         f'value="{_esc(seen)}">')
            # 溯源与 suggestion_seen 同一个判定点:出过声的读者 tag 就是
            # _vision_state 看的那一批。查不到就整槽不写 —— 半份溯源看起来
            # 像证据,而 append_adjudication 也会拒。
            from . import suggest_provenance as _sp

            readers = [m for m, _ in
                       (ctx.vision.get((row["doc_id"], row["field"])) or [])]
            prov = _sp.slot_provenance(
                getattr(ctx, "suggest_provenance", None),
                row["doc_id"], readers)
            if prov is not None:
                sug_input += (
                    f'<input type="hidden" name="suggestion_artifact_sha256" '
                    f'value="{_esc(prov[0])}">'
                    f'<input type="hidden" name="suggestion_model" '
                    f'value="{_esc(prov[1])}">')
```

- [ ] **Step 8: 接工作台 —— `/decide` 透传**

`invoiceloop/workbench.py:3491` 那行 `suggestion_seen=...` 之后追加两行:

```python
                suggestion_artifact_sha256=form.get(
                    "suggestion_artifact_sha256", [""])[0] or None,
                suggestion_model=form.get("suggestion_model", [""])[0] or None,
```

- [ ] **Step 9: 跑工作台测试确认没坏**

```bash
.venv/bin/python -m pytest tests/test_workbench.py tests/test_adjudicate.py \
  tests/test_suggest_provenance.py -q
```
预期:全绿。

- [ ] **Step 10: 提交**

```bash
git add invoiceloop/suggest_provenance.py scripts/suggest_provenance_freeze.py \
        invoiceloop/workbench.py tests/test_suggest_provenance.py
git commit -m "Freeze suggestion artifacts before the walk and carry their digest into every slot the reviewer sees them on."
```

---

### Task 8: 抽行走集并冻结行走协议

**Files:**
- Create: `scripts/qual_walk_plan.py`
- Create: `docs/qual_adk_walk_doc_list.json`(由命令生成)
- Create: `docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md`

**前置**:Task 5 已跑完,资格集路由指标已算完并提交。**顺序纪律:人在这之前不许碰这 200 份里的任何一份。**

- [ ] **Step 1: 写 `scripts/qual_walk_plan.py`**

```python
#!/usr/bin/env python3
"""从资格集 200 份里抽 20 份行走集(最小哈希,只取人队列 ≥1 槽)。

零 API:只读臂 D 的 routing_report.json。抽样规则与资格轮同款,换一把盐。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from invoiceloop.heldout import doc_ids_line_digest  # noqa: E402

SALT = "invoiceloop-qual-adk-walk-v1"
AUTO = ("auto_accept", "auto_absent")


def eligible(routes: list[dict]) -> list[str]:
    """人队列 ≥1 槽的文档。零触达的文档进行走集没有意义 —— 没有槽可走。"""
    return sorted({str(r["doc_id"]) for r in routes if r["route"] not in AUTO})


def pick(doc_ids: list[str], n: int) -> list[str]:
    if len(doc_ids) < n:
        raise SystemExit(f"合格文档只有 {len(doc_ids)} 份,不足 {n}")
    ranked = sorted(doc_ids, key=lambda d: hashlib.sha256(
        f"{SALT}|{d}".encode("utf-8")).hexdigest())
    return sorted(ranked[:n])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--routing-report", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()

    routes = json.loads(args.routing_report.read_text(encoding="utf-8"))["routes"]
    pool = eligible(routes)
    ids = pick(pool, args.n)
    payload = {
        "round": "qual-adk-walk",
        "n": args.n,
        "source": str(args.routing_report),
        "eligibility": "臂 D(HAR-0023)路由下人队列 ≥1 槽",
        "eligible_n": len(pool),
        "eligible_sha256": doc_ids_line_digest(pool),
        "sampling": f"min-hash:sha256(「{SALT}|」+ doc_id) 升序取前 {args.n}",
        "doc_ids": ids,
        "doc_ids_sha256": hashlib.sha256(
            "\n".join(ids).encode("utf-8")).hexdigest(),
    }
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps({k: payload[k] for k in
                      ("eligible_n", "n", "eligible_sha256", "doc_ids_sha256")},
                     ensure_ascii=False, indent=1))
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
```

注意 `doc_ids_sha256` 用的是 `"\n".join(ids)` 的 sha256 —— 与 `hitl_narrow_setup._load_docs` 的校验口径一致(那里也是 `"\n".join(doc_ids)`),不是 `doc_ids_line_digest`。两个口径在这里恰好同值(ids 已排序),但校验方读的是前者,所以就按前者写。

- [ ] **Step 2: 抽名单**

```bash
.venv/bin/python scripts/qual_walk_plan.py \
  --routing-report runs/qual-narrow-2026-08-22/doctouch/arms/HAR-0023/routing_report.json \
  --out docs/qual_adk_walk_doc_list.json --n 20
```
预期:一段 JSON(`eligible_n` 约 150–190、`n` 20、两个 sha256),然后 `→ docs/qual_adk_walk_doc_list.json`。

- [ ] **Step 3: 写行走协议正文**

新建 `docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md`,把 Step 2 打印的两个 sha256 填进 §2:

```markdown
# QUAL_ADK_WALK_2026-08-24 —— ADK×HITL 协议内行走协议

冻结于本 commit,先于**任何一条裁决**。改了正文 = 臂不干净,照 HITL-narrow 先例声明。

## 1. 一句话

agent(Gemini,走 google-adk)以**协议内一等公民**身份参与人工行走:
建议从第一槽就在场、每条账本行带完整溯源、**零权威**。

零权威的含义是结构性的,不是承诺:agent 的输出只能落到
`vision/answers6.adk-invoice.tsv`(显示层)和 `vision/invoice_read.json`(工件)。
它不进 `field_drafts.json`、不进冻结账本、不进 review_snapshot 的 components、
不改任何 gate,也不能 accept / reject。

## 2. 行走集

- 来源:`runs/qual-narrow-2026-08-22/doctouch/arms/HAR-0023/routing_report.json`
- 合格条件:臂 D 路由下人队列 ≥1 槽。合格 [填] 份,`eligible_sha256` = `<抄 Step 2>`
- 抽样:最小哈希,盐 `invoiceloop-qual-adk-walk-v1`,取 20 份。
- 名单:`docs/qual_adk_walk_doc_list.json`,`doc_ids_sha256` = `<抄 Step 2>`
- **顺序**:资格集零触达已在 `docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md`
  里算完并提交,人才碰这 20 份。行走不回写、不污染路由指标。
- 两轮独立记账,数字不拼接。

## 3. 建议:走前冻结,不走中途

修掉 HITL-narrow 自认混淆里的两条(中途注入、中途改协议)。

1. 20 份的建议在**任何裁决开始之前**全部生成完毕。
2. 生成完立刻冻结成溯源工件:`scripts/suggest_provenance_freeze.py` 写
   `vision/suggestion_provenance.json`,含每份读法的 sha256、全轮一份的
   prompt digest 与 schema digest。该文件已存在则拒绝覆盖。
3. 账本每槽记三样:`suggestion_seen`(人当时看见的建议状态)、
   `suggestion_artifact_sha256`(那份读法的哈希)、`suggestion_model`。
   prompt / schema digest 是**全轮一份**,在溯源文件里,不进每一行。
4. 读法失败的文档没有工件,那些槽不会带溯源 —— 结果文档必须写出失败数,
   不能把它算进 100% 覆盖。

## 4. 预注册预测(错了照登)

| # | 预测 | 依据 |
|---|---|---|
| P1 | 有建议工件的槽 100% 带 `suggestion_seen` + 两个溯源字段 | 「有机结合」的结构性主张,可测试 |
| P2 | agree 类建议采纳率 ≥ 60% | HITL-narrow 实测 10/13 = 77%,留回落空间 |
| P3 | 行走槽中位耗时 ≤ 60s | narrow 30s / 普查 R1-S1 52s;建议不该拖慢行走 |
| P4 | 模型提出异议且人采纳改值的槽 ≥ 1 | = 0 则顾问层价值主张如实登记为**未证明** |
| P5 | 零权威违反 | 结构保证,见 §1 |

## 5. 废臂条款(触发即声明)

裁决开始之后做以下任何一件 = 臂不干净:改本协议正文、换模型、中途补生成建议、
覆盖溯源文件、复查 DocILE 标注、改 HAR-0023 策略。

## 6. 人时口径

沿用 `scripts/hitl_round_analyze.py`:相邻 `decided_at` 之差为当前槽耗时,
首条剔除,间隔 > 1h 视为休息剔除,只报中位数。
含学习效应混淆(第二十份比第一份熟),照登不修正。
```

- [ ] **Step 4: 提交 —— 这一条 commit 必须先于任何裁决**

```bash
git add scripts/qual_walk_plan.py docs/qual_adk_walk_doc_list.json \
        docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md
git commit -m "Freeze the ADK walk protocol and its 20-document set drawn from the qualification round after its routing numbers were already published."
```

---

### Task 9: 装配、预生成建议、冻结、行走

**Files:**
- Create: `scripts/qual_adk_walk_setup.py`
- Create: `runs/qual-adk-walk/`(工作区,由命令生成)

- [ ] **Step 1: 写 `scripts/qual_adk_walk_setup.py`**

```python
#!/usr/bin/env python3
"""装配 ADK 行走轮(docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md)。

冻结 HAR-0023(payment_required_v1,TIER1 explicit off),与资格轮臂 D 同策略。
语料来自资格集的存盘响应 —— 走 doctouch_arms.assemble 而不是
hitl_round_setup._populate:后者的 RAW_WORKSPACES 是写死的四个目录,
不含 runs/qual-narrow-*。

不注入任何建议:建议由 hitl_adk_invoice_read.py 单独跑,跑完再冻结溯源。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from doctouch_arms import assemble, discover_dual_mode, select_sources  # noqa: E402
from invoiceloop import pipeline  # noqa: E402
from invoiceloop.harness import schema_digest  # noqa: E402
from invoiceloop.release_profile import document_touch_metrics  # noqa: E402
from invoiceloop.round_status import write_round_status  # noqa: E402
from invoiceloop.routing import policy_digest  # noqa: E402
from invoiceloop.sealed_batch import _corpus_environment, frozen_harness  # noqa: E402

LIST = REPO / "docs" / "qual_adk_walk_doc_list.json"
HAR_POLICY = REPO / "docs/evidence/narrow_v1_2026-08-14/HAR-0023.routing_policy.json"
HAR_SCHEMA = REPO / "invoiceloop/harnesses/HAR-0001/extraction_schema.json"


def _har0023_active() -> dict:
    policy = json.loads(HAR_POLICY.read_text(encoding="utf-8"))
    schema = json.loads(HAR_SCHEMA.read_text(encoding="utf-8"))
    return {
        "harness_id": "HAR-0023",
        "policy": policy,
        "policy_digest": policy_digest(policy),
        "policy_sha256": hashlib.sha256(HAR_POLICY.read_bytes()).hexdigest(),
        "schema": schema,
        "schema_digest": schema_digest(schema),
        "schema_sha256": hashlib.sha256(HAR_SCHEMA.read_bytes()).hexdigest(),
    }


def _load_docs() -> list[str]:
    spec = json.loads(LIST.read_text(encoding="utf-8"))
    doc_ids = spec["doc_ids"]
    digest = hashlib.sha256("\n".join(doc_ids).encode("utf-8")).hexdigest()
    if digest != spec["doc_ids_sha256"]:
        raise SystemExit("fatal: 行走集名单 sha 不符,名单被改过")
    return doc_ids


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", type=Path,
                    default=REPO / "runs" / "qual-adk-walk")
    ap.add_argument("--no-crops", action="store_true")
    args = ap.parse_args()

    ws = args.workspace
    doc_ids = _load_docs()
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "doc_list.json").write_text(LIST.read_text(encoding="utf-8"),
                                      encoding="utf-8")
    status_action = write_round_status(ws, {
        "round": "qual-adk-walk",
        "status": "live",
        "harness_id": "HAR-0023",
        "protocol": "docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md",
    })
    if status_action == "preserved_terminated":
        print("round_status 已是 terminated,setup 不复活")

    sources = select_sources(discover_dual_mode(), sorted(doc_ids))
    stats = assemble(ws, sources)
    if stats["missing"]:
        raise SystemExit(json.dumps(
            {"fatal": "语料缺失,协议要求缺响应换单不补抽",
             "missing": stats["missing"]}, ensure_ascii=False, indent=1))

    run_dir = ws / "runs" / "run-0001"
    if not run_dir.exists():
        with _corpus_environment(ws), frozen_harness(_har0023_active()):
            pipeline.run(doc_ids, run_dir,
                         render_crops=not args.no_crops,
                         include_vision=False, out_of_calibration=True)
    else:
        print(f"run 已存在,重放:{run_dir}")

    (ws / "runs" / "current.json").write_text(
        json.dumps({"run": "run-0001"}) + "\n", encoding="utf-8")
    routing = json.loads((run_dir / "routing_report.json").read_text())
    print(json.dumps({
        "round": "qual-adk-walk",
        "docs": len(doc_ids),
        "corpus": {"docs": stats["docs"]},
        "run": str(run_dir),
        "harness_id": routing.get("harness_id"),
        "touch": document_touch_metrics(routing["routes"], routing["policy"]),
        "next": [
            f".venv/bin/python scripts/hitl_adk_invoice_read.py --run-dir {run_dir}",
            f".venv/bin/python scripts/suggest_provenance_freeze.py "
            f"--run-dir {run_dir} --round qual-adk-walk --frozen-at <ISO8601>",
        ],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 装配并跑流水线**

```bash
.venv/bin/python scripts/qual_adk_walk_setup.py
```
预期:一段 JSON,`docs: 20`、`harness_id: "HAR-0023"`、`touch` 里 `docs: 20`、以及两条 next 命令。

- [ ] **Step 3: 预生成 20 份建议(唯一的 Gemini 花费)**

```bash
set -a && . ./.env && set +a && \
.venv/bin/python scripts/hitl_adk_invoice_read.py \
  --run-dir runs/qual-adk-walk/runs/run-0001 \
  --model gemini-3.6-flash 2>&1 | tail -30
```
预期:逐份打印 `[i/20] <doc_id>`,末尾一段 JSON 含 `"docs": 20`、`"failed": []`、`"injected"`。
`failed` 非空则退出码为 1 —— 把失败明细带进结果文档,**不要为了凑满 20 而重跑换模型**(换模型 = 废臂)。

- [ ] **Step 4: 冻结溯源工件(裁决开始之前的最后一步)**

```bash
.venv/bin/python scripts/suggest_provenance_freeze.py \
  --run-dir runs/qual-adk-walk/runs/run-0001 \
  --round qual-adk-walk \
  --frozen-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```
预期:一段 JSON,`docs: 20`、`model: "gemini-3.6-flash"`、两个 digest 前缀。

- [ ] **Step 5: 提交冻结状态 —— 这一条 commit 必须先于第一条裁决**

```bash
git add scripts/qual_adk_walk_setup.py \
        runs/qual-adk-walk/runs/run-0001/vision/invoice_read.json \
        runs/qual-adk-walk/runs/run-0001/vision/suggestion_provenance.json
git commit -m "Pre-generate and freeze all twenty ADK readings before a single slot is adjudicated."
```

- [ ] **Step 6: 走**

```bash
.venv/bin/python -m invoiceloop workbench --workspace runs/qual-adk-walk --port 8793
```
浏览器打开 `http://127.0.0.1:8793`。逐槽裁决。

走的时候盯三件事:
1. 每个带建议的槽,页面上都能看到 ADK 读法卡片。
2. 提交后 `adjudication_ledger.jsonl` 的那一行应当同时有 `suggestion_seen`、
   `suggestion_artifact_sha256`、`suggestion_model`。走完前几槽先抽查一次:

```bash
tail -3 runs/qual-adk-walk/runs/run-0001/adjudication_ledger.jsonl | \
  .venv/bin/python -c "
import json, sys
for line in sys.stdin:
    e = json.loads(line)
    print(e['decision_id'], e['field'], e['decision'],
          '| seen', e.get('suggestion_seen'),
          '| sha', (e.get('suggestion_artifact_sha256') or '-')[:12],
          '| model', e.get('suggestion_model'))
"
```
预期:有建议的槽三个字段齐全;没建议的槽三个都缺。**只缺其中一两个 = 阻断,停下来查。**

3. 协议不许中途改。想改 = 停下来,按废臂条款声明。

- [ ] **Step 7: 提交账本**

```bash
git add runs/qual-adk-walk/runs/run-0001/adjudication_ledger.jsonl
git commit -m "Record the twenty-document ADK walk: every slot the agent spoke on carries its artifact digest and model id."
```

---

### Task 10: 行走结果分析与结果文档

**Files:**
- Create: `scripts/qual_walk_analyze.py`
- Create: `docs/QUAL_ADK_WALK_RESULTS_2026-08-25.md`

- [ ] **Step 1: 写 `scripts/qual_walk_analyze.py`**

```python
#!/usr/bin/env python3
"""ADK 行走轮 P1–P5 对照(零 API,只读账本与冻结工件)。

P2/P3 直接复用 hitl_round_analyze(采纳率与人时口径不另立一套)。
P1/P4/P5 是本轮新增的结构性判据。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import hitl_round_analyze  # noqa: E402
from invoiceloop import suggest_provenance  # noqa: E402
from invoiceloop.fields import FIELD_KINDS, normalise  # noqa: E402


def provenance_coverage(entries: list[dict], prov: dict) -> dict:
    """P1:有建议工件的槽,是不是 100% 带 suggestion_seen + 两个溯源字段。

    分母不是「全部槽」,是「文档在工件里有读法、且该槽展示过建议」的槽。
    """
    reader_docs = set()
    for rec in (prov.get("readers") or {}).values():
        reader_docs |= set(rec.get("docs") or {})
    denom = complete = seen_only = 0
    gaps = []
    for entry in entries:
        if entry["doc_id"] not in reader_docs:
            continue
        if not entry.get("suggestion_seen"):
            continue
        denom += 1
        has_sha = bool(entry.get("suggestion_artifact_sha256"))
        has_model = bool(entry.get("suggestion_model"))
        if has_sha and has_model:
            complete += 1
        else:
            seen_only += 1
            gaps.append({"decision_id": entry["decision_id"],
                         "doc_id": entry["doc_id"], "field": entry["field"],
                         "has_sha": has_sha, "has_model": has_model})
    return {
        "slots_with_a_shown_suggestion": denom,
        "with_full_provenance": complete,
        "coverage": round(complete / denom, 4) if denom else None,
        "gaps": gaps,
    }


def model_dissent_adopted(entries: list[dict], claims: dict) -> dict:
    """P4:模型给的值与冻结声明不同,人**改成了模型那个值**的槽。

    这是顾问层唯一无法用结构保证代替的价值主张:模型说了别的,而人信了。
    = 0 就如实登记为未证明,不找补。
    """
    hits = []
    for entry in entries:
        seen = entry.get("suggestion_seen") or ""
        if not seen.startswith("agree:") or entry["decision"] != "correct":
            continue
        suggested = seen.split(":", 1)[1]
        kind = FIELD_KINDS.get(entry["field"])
        if normalise(str(entry.get("corrected_value") or ""), kind) != \
                normalise(suggested, kind):
            continue
        claim = claims.get(entry.get("claim_id") or "") or {}
        if normalise(str(claim.get("value") or ""), kind) == \
                normalise(suggested, kind):
            continue  # 模型只是复述了声明,不算异议
        hits.append({"decision_id": entry["decision_id"],
                     "doc_id": entry["doc_id"], "field": entry["field"],
                     "claim_value": claim.get("value"),
                     "model_value": suggested})
    return {"n": len(hits), "slots": hits}


def authority_violations(entries: list[dict], prov: dict, run_dir: Path) -> dict:
    """P5:零权威。三条检查,任何一条非空 = 违反。

    第二条查的是**成分表这个常量**,不是某个 run 的快照实例:
    SNAPSHOT_COMPONENTS 是写死的七个文件名,扫实例永远扫不出建议工件 ——
    那是同义反复。真正会出事的是哪天有人把 vision/ 加进成分表,
    建议层就此进入冻结身份。
    """
    from invoiceloop.snapshot import SNAPSHOT_COMPONENTS

    models = {str(rec.get("model")) for rec in
              (prov.get("readers") or {}).values() if rec.get("model")}
    tags = set(prov.get("readers") or {})
    signed_by_model = [e["decision_id"] for e in entries
                       if str(e.get("adjudicator") or "") in models]
    suggestion_in_contract = sorted(
        c for c in SNAPSHOT_COMPONENTS
        if "answers6" in c or "invoice_read" in c or c.startswith("vision/"))
    claims = json.loads(
        (run_dir / "field_ledger.json").read_text(encoding="utf-8"))["claims"]
    claims_drafted_by_agent = [
        c["claim_id"] for c in claims
        if str(c.get("drafted_by") or "") in (models | tags)]
    return {
        "decisions_signed_by_a_model": signed_by_model,
        "suggestion_paths_in_snapshot_contract": suggestion_in_contract,
        "claims_drafted_by_the_agent": claims_drafted_by_agent,
        "clean": not (signed_by_model or suggestion_in_contract
                      or claims_drafted_by_agent),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, type=Path)
    args = ap.parse_args()
    run_dir = args.run
    base = hitl_round_analyze.analyze(run_dir)
    entries = [json.loads(x) for x in
               (run_dir / "adjudication_ledger.jsonl")
               .read_text(encoding="utf-8").splitlines() if x.strip()]
    claims = {c["claim_id"]: c for c in json.loads(
        (run_dir / "field_ledger.json").read_text())["claims"]}
    prov = suggest_provenance.load(run_dir) or {}
    print(json.dumps({
        **base,
        "P1_provenance": provenance_coverage(entries, prov),
        "P2_adoption": base["suggestions"],
        "P3_timing": base["timing"],
        "P4_model_dissent_adopted": model_dissent_adopted(entries, claims),
        "P5_authority": authority_violations(entries, prov, run_dir),
        "provenance_frozen_at": prov.get("frozen_at"),
        "prompt_digest": prov.get("prompt_digest"),
        "schema_digest": prov.get("schema_digest"),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑分析**

```bash
.venv/bin/python scripts/qual_walk_analyze.py \
  --run runs/qual-adk-walk/runs/run-0001 \
  > runs/qual-adk-walk/walk_analysis.json
.venv/bin/python -c "
import json, pathlib
a = json.loads(pathlib.Path('runs/qual-adk-walk/walk_analysis.json').read_text())
print('P1 覆盖', a['P1_provenance']['with_full_provenance'], '/',
      a['P1_provenance']['slots_with_a_shown_suggestion'],
      '=', a['P1_provenance']['coverage'])
print('P2 采纳', a['P2_adoption']['adopted'], '/',
      a['P2_adoption']['agree_slots'], '=', a['P2_adoption']['adoption_rate'])
print('P3 中位', a['P3_timing']['median_seconds'], 's  (n_timed',
      a['P3_timing']['n_timed'], ')')
print('P4 模型异议被采纳', a['P4_model_dissent_adopted']['n'])
print('P5 零权威', a['P5_authority']['clean'])
"
```
预期:五行。P1 应当是 `1.0`;P5 应当是 `True`。P2/P3/P4 是实测,好坏都照登。

- [ ] **Step 3: 写结果文档**

新建 `docs/QUAL_ADK_WALK_RESULTS_2026-08-25.md`:

```markdown
# QUAL_ADK_WALK_2026-08-24 结果(n=20 文档)

协议:`docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md`(冻结于第一条裁决之前)
数据:`runs/qual-adk-walk/walk_analysis.json`
账本:`runs/qual-adk-walk/runs/run-0001/adjudication_ledger.jsonl`(sha256 见分析输出)
复算:零 API。

## 0. 臂干净吗

[没有触发废臂条款就写:协议正文、模型、建议工件、HAR-0023 策略在裁决期间均未改动。
触发了就照 HITL-narrow 先例,把改了什么、什么时候改的、影响哪些槽全写出来。]

读法失败 [填] 份。[非 0 时:那些文档没有工件,它们的槽不计入 P1 分母,也不能算进覆盖率。]

## 1. 预注册对照

| # | 预测 | 实测 | 判定 |
|---|---|---|---|
| P1 | 有建议工件的槽 100% 带完整溯源 | [填] | [成立 / 不成立] |
| P2 | agree 采纳率 ≥ 60% | [填] | [成立 / 不成立] |
| P3 | 中位耗时 ≤ 60s | [填] | [成立 / 不成立] |
| P4 | 模型异议被采纳 ≥ 1 槽 | [填] | [成立 / 不成立] |
| P5 | 零权威违反 | [填] | [成立 / 不成立] |

## 2. 「有机结合」到底证明了什么

**证明了**:一个模型可以在一条人工审批流程里从第一槽就在场、每次发言都在
账本上留下可复算的溯源(哪份工件、哪个模型、什么时候冻结的),而**完全不持有
任何权威** —— 它不能接受、不能拒绝、不能改闸,它的输出连 review_snapshot
的 components 都进不去。P1 与 P5 是这句话的两条可测证据。

**没证明**:模型的建议让人更快或更准。P3 是同一个人走 20 份的中位耗时,含
学习效应混淆,没有对照组。P2 的采纳率不是准确率 —— 人采纳了不等于对。
[P4 = 0 时写:本轮没有观察到「模型说了别的、人信了」的槽,顾问层的价值主张
在这一轮登记为**未证明**。P1/P5 这两条结构性主张不受影响。]

## 3. 与 HITL-narrow(2026-08-14)的差别

| | HITL-narrow | 本轮 |
|---|---|---|
| 建议时机 | 走中途注入(自认混淆) | **全部走前预生成并冻结** |
| 协议 | 中途改过(自认混淆) | 冻结于第一条裁决之前 |
| 溯源 | 只有 `suggestion_seen` | + 工件 sha256 + 模型 id + 全轮 digest |
| 文档 | 20(开发集) | 20(**从未曝光资格集抽出**) |
```

- [ ] **Step 4: 提交**

```bash
git add scripts/qual_walk_analyze.py runs/qual-adk-walk/walk_analysis.json \
        docs/QUAL_ADK_WALK_RESULTS_2026-08-25.md
git commit -m "Report the ADK walk against its five predictions: the agent spoke on every slot it was given and held no authority on any of them."
```

---

## Phase C —— 收尾与材料

### Task 11: lint 回归、rubric 便宜分、诚实重跑自评

**Files:**
- Create: `tests/test_lint_release_profile.py`
- Modify: `README.md`(H 项推广主张一段;「For judges」quickstart 在 Task 12)
- Modify: `docs/FIELD_COVERAGE.md` 或 `README.md`(E 项 line-item 范围声明一句)
- Create: `docs/RUBRIC_V01_SCORE_2026-08-28.md`

- [ ] **Step 1: 写 lint 回归测试**

`lint_policy` **已经**会拒绝机器 propose `release_profile`(实测返回
`['候选改了 release_profile —— 第一版只允许加 cohorts']`),spec 里那条「代码未接」
是过期判断。所以这一项缩成一条把契约钉住的回归测试 —— 它不是仪式:
`lint_policy` 的默认分支是「凡 key 不同即拒」,哪天有人为了别的需求给白名单
加一项,放行契约就会跟着被机器改宽,而那正是这个项目全部论点的反面。

新建 `tests/test_lint_release_profile.py`:

```python
"""机器不许 propose 放行契约 —— 改宽 release_profile = 把「谁能免复核」
这个决定从人手里拿走。lint 的白名单哪天放松了,这条会红。"""

from __future__ import annotations

import pytest

from invoiceloop.improve import lint_policy

PARENT = {
    "harness_id": "HAR-0021",
    "version": 1,
    "auto_accept_cohorts": [],
    "absent_expected_cohorts": [],
}


def test_machine_cannot_introduce_a_release_profile():
    candidate = {**PARENT, "harness_id": "HAR-0099", "version": 2,
                 "release_profile": {"id": "payment_required_v1",
                                     "fields": ["invoice_number",
                                                "seller_name", "amount_due"]}}
    violations = lint_policy(PARENT, candidate)
    assert any("release_profile" in v for v in violations), violations


def test_machine_cannot_widen_an_existing_release_profile():
    parent = {**PARENT, "release_profile": {"id": "payment_required_v1",
                                            "fields": ["invoice_number"]}}
    candidate = {**parent, "harness_id": "HAR-0099", "version": 2,
                 "release_profile": {"id": "payment_required_v1",
                                     "fields": ["invoice_number",
                                                "seller_name"]}}
    violations = lint_policy(parent, candidate)
    assert any("release_profile" in v for v in violations), violations


def test_machine_cannot_flip_tier1_explicit():
    """release_tier1_explicit: false 会把 TIER1 自动接受移出人队列 ——
    与改契约同样是权威转移,同样只能由人做。"""
    candidate = {**PARENT, "harness_id": "HAR-0099", "version": 2,
                 "release_tier1_explicit": False}
    violations = lint_policy(PARENT, candidate)
    assert any("release_tier1_explicit" in v for v in violations), violations


def test_adding_a_cohort_still_passes():
    """守住的是放行契约,不是把改进循环整个锁死。"""
    candidate = {**PARENT, "harness_id": "HAR-0099", "version": 2,
                 "auto_accept_cohorts": [
                     {"id": "c1", "field": "invoice_number",
                      "tier": "TIER1", "strength": "strong"}]}
    assert lint_policy(PARENT, candidate) == []


@pytest.mark.parametrize("key", ["release_profile", "release_tier1_explicit"])
def test_the_violation_says_which_key(key):
    """违规文案要指名道姓 —— 「候选没通过审查」这种话让人查不下去。"""
    candidate = {**PARENT, "harness_id": "HAR-0099", "version": 2, key: {}}
    assert any(key in v for v in lint_policy(PARENT, candidate))
```

- [ ] **Step 2: 跑测试**

```bash
.venv/bin/python -m pytest tests/test_lint_release_profile.py -q
```
预期:`6 passed`。全绿说明契约本来就守着 —— 这条 commit 的价值是从此**有人守着它**。
有红的先读 `invoiceloop/improve.py::lint_policy` 再动,不要为了让测试变绿去放宽 lint。

- [ ] **Step 3: E 项 +1 —— line-item 范围声明**

`README.md` 里字段覆盖那一节末尾加一段(位置:`docs/FIELD_COVERAGE.md` 的引用附近):

```markdown
**Line items are out of scope, and that is a design decision, not a gap.**
This system's unit of evidence is a field whose support relation is geometric:
a value, a page rectangle, and an independent OCR reading that either does or
does not contain it. A line-item table is a *structure* — rows, column
alignment, cross-row arithmetic — and its correctness claim is not reducible
to "is this string on the page here." Extending the support matrix to tables
would need a second kind of evidence and a second kind of gate. We did not
build one, so we do not score one. The ten scored fields are the ones where
the claim we make is the claim we can check.
```

- [ ] **Step 4: H 项 +1 —— 推广主张**

`README.md` 第 20 行附近那半句论证补全成一段:

```markdown
**Where this mechanism generalises.** Nothing in the six gates knows what an
invoice is. They know that a claimed value must be locatable on a page, that
an independent reading of that page must contain it, that two extraction modes
must agree, and that arithmetic between claimed values must hold. That set of
questions applies to any document domain where the support relation is
geometric — where "is this true?" reduces to "is this on the page, here?"
Receipts, purchase orders, bills of lading, remittance advices, and delivery
notes all fall inside it: each is a page with printed values whose provenance
is a rectangle. Contracts and correspondence fall outside it, because their
claims live in prose and their support relation is semantic, not geometric.
The line is not "invoice vs not-invoice"; it is "can a rectangle carry the
proof."
```

- [ ] **Step 5: 诚实重跑自评分**

判据不动(`docs/HACKATHON_RUBRIC_v0.1.md` v0.1 冻结),在提交 commit 上重打。
新建 `docs/RUBRIC_V01_SCORE_2026-08-28.md`,结构照 `docs/RUBRIC_V01_SCORE_2026-08-06.md`:

```markdown
# v0.1 判据重跑自评(2026-08-28)

判据:`docs/HACKATHON_RUBRIC_v0.1.md`,**未改动**。上一次:`docs/RUBRIC_V01_SCORE_2026-08-06.md`(93/96)。
本次在提交 commit `<填 git rev-parse --short HEAD>` 上重打。

## 一、分项变化

| 项 | 08-06 | 本次 | 依据 |
|---|---:|---:|---|
| E 可靠性改进与实验证据 | [填] | [填] | 08-06 §五 #3 的 line-item 范围声明已写(README);资格轮结果 `docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md` |
| F 风险路由与 HITL | [填] | [填] | ADK 行走 P1/P5 |
| G 审计、来源与可回放性 | [填] | [填] | 每槽建议溯源进账本 |
| H 创新性与差异化 | [填] | [填] | 08-06 §五 #4 的推广主张已写(README) |
| B 项目进展与端到端执行 | [填] | [填] | 08-06 §五 #5 挂着「等走完资格流程再谈零触碰」;资格轮就是那个流程 —— **但是否加分要照 v0.1 判据 B 段的原文判,不能因为跑了一轮就自己给** |

## 二、本轮亲手验过的(不是读 README)

[逐条列出实际跑过的命令与看到的输出。08-06 那份的这一节是它可信的原因,照做。]

## 三、没变的项与理由

[略]

## 四、剩余 ROI

[照 08-06 §五 的格式,重新列]
```

**纪律**:重打时如果发现 08-06 那份给高了,就往下调并写明理由。自评分只有在
会往下走的时候才有意义(GOAL.md 一:诚实 > 好看)。

- [ ] **Step 6: 跑全量测试**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```
预期:全绿,条数 ≥ 116 + 本计划新增(约 24 条)。

- [ ] **Step 7: 提交**

```bash
git add tests/test_lint_release_profile.py README.md \
        docs/RUBRIC_V01_SCORE_2026-08-28.md
git commit -m "Pin the release contract against machine widening, state why line items are out of scope, and re-score against the frozen v0.1 rubric."
```

---

### Task 12: 材料

**这一项不是 TDD。** 视频、表单、README 面向评委的整理没有可失败的测试,
硬写一个测试断言「视频存在」是仪式。所以本任务是清单式,每项给验收条件。

**Files:**
- Modify: `README.md`(「For judges」quickstart)
- Modify: `DISCLOSURE.md`(赛期内模块清单)
- Create: `docs/submission/NUTRIENT_FORM.md`、`docs/submission/ATA_FORM.md`(表单文案底稿)

- [ ] **Step 1: README 加「For judges」三命令零 API quickstart**

`README.md` 顶部(项目一句话之后、架构之前)插入:

````markdown
## For judges — three commands, zero API cost

Everything below reads saved artifacts from disk. No key needed, nothing billed.

```bash
git clone https://github.com/Stahl-G/invoiceloop && cd invoiceloop
python3 -m venv .venv && .venv/bin/pip install -e .

# 1. Run the demo end to end on the vendored sample documents
.venv/bin/python -m invoiceloop run --out runs/demo --crops

# 2. Open the review workbench on what it produced
.venv/bin/python -m invoiceloop workbench --workspace runs/demo --port 8793

# 3. Verify every number in this README is recomputable
.venv/bin/python -m pytest tests/ -q
```
````

验收:在一个干净目录里照抄跑一遍,三条都成功。用 `scripts/fresh_venv_check.sh` 复验:

```bash
bash scripts/fresh_venv_check.sh 2>&1 | tail -20
```

- [ ] **Step 2: DISCLOSURE.md 刷新**

`DISCLOSURE.md` 的「Modules that did not exist before 2026-08-03 09:00 PT」代码块里补:

```
invoiceloop/release_profile.py       invoiceloop/suggest_provenance.py
invoiceloop/truth_caliber.py         invoiceloop/amount_triad.py
invoiceloop/party_caliber.py         invoiceloop/round_status.py
```

(先核对哪些确实是赛期内新建的:)

```bash
for f in release_profile suggest_provenance truth_caliber amount_triad party_caliber round_status scope sealed_batch; do
  printf "%-22s " "$f"
  git log main --diff-filter=A --date=short --pretty='%ad %h' -- "invoiceloop/$f.py" | tail -1
done
```
预期:每行一个首次出现日期。**只把 2026-08-03 之后的写进赛期内清单**;
之前的照实归到 pre-existing 那一节。日期对不上就以 git 为准改文档,不是反过来。

- [ ] **Step 3: 一次录制,两版剪辑(英文解说)**

**Nutrient 版**(rubric §I 的 3:30 结构,2–4 分钟):

| 段 | 镜头 | 素材 |
|---|---|---|
| 问题 | 一句话:抽取对不对不可信,支持关系可验证 | README 顶部 |
| 闭环 | 上传 → 抽取 → 冻结 → 六闸 → 支持矩阵 → 人队列 | `invoiceloop run` 实跑 |
| clean 自动放行 | 一份三闸全过、零人工的文档 | 资格集真 PDF |
| risky 拦截 + 人工修正 | 一份进人队列的,人改值 | 工作台实操 |
| 审计链 | 账本行 → 快照 → bundle | `audit_bundle.zip` |
| 证据数字 | 资格轮 200 份零触达 [X]%,带限定句 | Task 5 结果文档 |
| DWS heavy-lifting | 双模式抽取是核心,不是装饰调用 | `runs/qual-narrow-*/raw/` 里的真实响应 |

**「真实上传」镜头必须用资格集真 PDF**,不用 vendored 样本 —— 评委会看得出区别。

**ATA 版**(2–4 分钟,开场即 agent 提议 / 人处置):

| 段 | 镜头 |
|---|---|
| 开场 | ADK 读法卡片出现在裁决页上,人在旁边做决定 |
| 账本溯源 | `adjudication_ledger.jsonl` 一行:`suggestion_seen` + 工件 sha256 + 模型 id |
| 零权威 | Task 10 的 P5 三条结构性检查输出 |
| Gemini 3.5+ | `hitl_adk_invoice_read.py` 实跑,模型名在输出里 |
| Google Agent Framework | `invoiceloop/agents/` 的 `Runner.run_async` + `SequentialAgent`;`docs/ADK_INTEGRATION.md` |
| Google Cloud | Cloud Run 实例;`docs/evidence/cloud_run_2026-08-07/` |

验收:两版各自 2–4 分钟;三条硬性要求在 ATA 版里**各有一个实证镜头**(不是口播)。

- [ ] **Step 4: 表单文案底稿**

新建 `docs/submission/NUTRIENT_FORM.md` 与 `docs/submission/ATA_FORM.md`,各含:
pitch(一段)、setup 复验步骤(指向 `scripts/fresh_venv_check.sh`)、
DWS heavy-lifting 一句话、公开仓库链接、视频链接。

数字全部指向已冻结的结果文档,不在表单里现算。

- [ ] **Step 5: 提交**

```bash
git add README.md DISCLOSURE.md docs/submission/
git commit -m "Put the judge-facing quickstart, the refreshed disclosure, and both submission drafts in the repo."
```

- [ ] **Step 6: 递交**

- 8/30 前:ATA(截止 2026-08-31 17:00 PT)
- 9/1:Nutrient(截止 2026-09-03)

递交前最后一次:

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -3
git log --oneline -12
git status --short
```
预期:测试全绿;工作区干净;协议 commit 在结果 commit 之前(顺序纪律在 git log 里看得见)。

---

## 时间线

比 spec 整体晚一天(spec 的 D1 是 8/21,实际从 8/22 起)。

| 日 | Task | 事 |
|---|---|---|
| 8/22 D1 | 1–4 | 抽样器 + 名单过滤 + 冻结协议 → 后台启动 400 次提取(~1.5h) |
| 8/23 D2 | 5 | 四臂跑完,写资格集结果文档(P1–P5 对照) |
| 8/24 D3 | 6–8 | 溯源字段 + 工作台 + 抽行走集 + 冻结行走协议 |
| 8/25 D4 | 9 | 装配、预生成 20 份建议、冻结工件、走完 20 份 |
| 8/26 D5 | 10 | 行走结果 P1–P5,写结果文档 |
| 8/27 D6 | 11 | lint 回归 + 便宜分 + 诚实重跑自评 |
| 8/28 D7 | 12 | 录制、剪辑、表单、README、披露刷新 |
| 8/29–30 | — | 缓冲;**8/30 前交 ATA** |
| 9/1 | — | **交 Nutrient** |

## 全程纪律

- 提取失败 = blocking 记录,不跳过、不补抽、不缩样本。
- 协议文本冻结后不改;改了 = 臂不干净,照登。
- 预测错了照登,不回改预测。
- 所有新代码带测试,且每条测试钉住一个用户可见的失败(抽样器可复算、
  名单缺件阻断、半份溯源被拒、放行契约不被机器改宽)。
- 任何对外数字带 `ARCHITECTURE.md` §8 三条限定;不说工件证明不了的话。
- 凭证只在 `.env`(gitignored):不进仓库、不进 run 目录、不进 bundle、不进日志、
  不写进任何文档。

## 风险登记

| 风险 | 处置 |
|---|---|
| 资格集数字比 10.8% 难看 | 不是风险,是结果;照登,带新限定进叙事。P2 的区间 5–20% 已经是诚实先验 |
| P4 = 0(agent 无可采纳异议) | 顾问层价值主张登记为未证明;P1/P5 两条结构性主张不受影响,ATA 叙事仍成立 |
| 提取中途 API 故障 / 限流 | `cmd_extract` 已内建退避重试与换 key;仍失败进 `failures` 并阻断。断点续跑,重发同一条命令即可 |
| 提取比预计慢 | 串行 400 次约 1.5h;D1 后台跑,D2 才需要结果。真慢了就让它跨夜,不加并发 |
| ADK 读法失败几份 | 那几份没有工件,不计入 P1 分母;**不换模型重跑**(换模型 = 废臂),失败数写进结果文档 |
| 行走人时不足 | 20 份按 narrow 实测中位 30s/槽,≈ 数小时级,D4 全天可容 |
| 材料挤压 | D7 之前所有证据已冻结;视频与表单只引用已落盘的数字,不依赖未完成的东西 |
| 走到一半想改协议 | 停下,按废臂条款声明,把改动与影响的槽写进结果文档 §0 |
