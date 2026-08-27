# 双黑客松冲刺 实施计划(2026-08-22)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在两个黑客松截止前,拿到两条冻结证据 —— 窄放行契约在**未曝光** 200 份上的零触达率,以及一个 agent 以协议内一等公民身份参与的 20 份人工行走 —— 然后用它们收材料。

**Architecture:** 两条证据线共用一次提取。资格轮先抽 200 份从未被碰过的 DocILE 文档、跑 400 次双模式 DWS 调用,再零 API 地把四个路由臂投影出来;ADK 行走从这 200 份里确定性抽 20 份,建议全部**走前预生成并冻结成工件**,账本每槽记下当时屏幕上那条建议出自哪份工件、哪个模型。新代码集中在四处:抽样器(`heldout.py`)、名单过滤(`doctouch_arms.py`)、溯源导出与对账(新模块 `suggest_provenance.py` + `adjudicate.py`)、证据落盘(`scripts/freeze_evidence.py`)。工作台一行不改 —— 溯源在服务端导出,浏览器只提交裁决。其余全是搬运既有实现。

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

另有四条是本计划第一版的缺陷,已在执行前修掉(2026-08-22 外部评审,逐条核实过):

- **`runs/` 进不了仓库。** 它是指向 `../invoiceloop-data/runs` 的 symlink,且 `.gitignore:10`
  忽略它(`git ls-files runs/` = 0)。所以「首条裁决前已提交冻结状态」不能靠 `git add runs/...`
  兑现。改用仓库既有做法:证据副本进 `docs/evidence/<round>/`,名单进 `docs/*_doc_list.json`
  (narrow_v1、absence_v3 都是这么做的),不另建 evidence repo。
- **冻结的必须是「人真正看见的那一行」。** 裁决页的建议来自 `vision/answers6.<tag>.tsv`
  (`_vision_state` ← `ctx.vision` ← `load_vision_answers`),而 `invoice_read.json` 是它的上游。
  `suggest_inject.inject` 会 `skipped_existing`、也会 `dropped`,两者双向可漂。所以冻结
  **TSV 的每一行**(`doc | field | displayed_value | tag` + 行哈希 + 整表哈希),读法摘要作为上游溯源一并留存。
- **溯源由服务端导出,浏览器不当证据写者。** `suggestion_artifact_sha256` 与 `suggestion_model`
  是 `(run, doc, field)` + 冻结表的纯函数,`append_adjudication` 自己查得到。让页面发这两个字段,
  等于让旧标签页或改过的请求决定证据身份,而后端只查格式。改成:页面只发 `suggestion_seen`,
  后端查冻结表导出溯源,**并与 `suggestion_seen` 对账** —— 一方说展示过、另一方查不到 = 阻断。
- **P1 的分母不能来自账本自己。** 原写法只统计已有 `suggestion_seen` 的行,于是「整套隐藏字段
  丢失」这个最该被发现的故障会直接从分母消失,覆盖率照样 100%。分母改成
  **冻结建议表 ∩ 实际裁决过的槽**。

时间线整体比 spec 晚一天(spec 的 D1 是 8/21,实际从 8/22 起),缓冲仍够:8/30 前交 ATA,9/1 交 Nutrient。

---

## 文件结构

**新建**

| 路径 | 职责 |
|---|---|
| `invoiceloop/suggest_provenance.py` | 从 TSV 建冻结建议表;`derive()` 按 `(run, doc, field)` 导出(工件哈希, 模型 id)并与 `suggestion_seen` 三向对账 |
| `scripts/suggest_provenance_freeze.py` | 建议预生成之后冻结:把 TSV 每一行(人真正看见的那条)与读法摘要一起写成溯源表 |
| `scripts/freeze_evidence.py` | 把冻结工件复制进 `docs/evidence/<round>/<stage>/` 并写 `MANIFEST.sha256`;**一个 stage 只能冻一次**(`runs/` 是 gitignored symlink,不复制就没有仓库内锚点) |
| `scripts/writeset.py` | run 目录的文件哈希快照与差集 —— P5 靠它证明 agent 那一趟只碰了 `vision/` 与 `agent_calls/` |
| `scripts/qual_walk_plan.py` | 从资格集 200 份的路由报告里抽 20 份行走集(最小哈希,只取人队列 ≥1 槽) |
| `scripts/qual_adk_walk_setup.py` | 装配行走工作区、跑 HAR-0023 流水线(复用 `doctouch_arms.assemble`) |
| `scripts/qual_walk_analyze.py` | 行走结果 P1–P5 对照 |
| `docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md` | 资格轮协议正文(冻结先于任何调用) |
| `docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md` | 行走协议正文(冻结先于任何裁决) |
| `docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md` | 资格轮结果 |
| `docs/QUAL_ADK_WALK_RESULTS_2026-08-25.md` | 行走结果 |
| `tests/test_qualify.py` | 资格池/抽样器测试 |
| `tests/test_doctouch_arms_doclist.py` | 名单过滤测试 |
| `tests/test_suggest_provenance.py` | 溯源导出、三向对账、冻结表构建与拒绝覆盖 |
| `tests/test_qual_walk_plan.py` | 行走集抽样与工作台队列谓词一致 |
| `tests/test_freeze_evidence.py` | 冻结分阶段不可变,后一次不改写前一次 |
| `tests/test_writeset.py` | 账本被动过时写集看得见 |
| `tests/test_lint_release_profile.py` | lint 回归:机器不许 propose `release_profile` |

**修改**

| 路径 | 改什么 |
|---|---|
| `invoiceloop/heldout.py` | 追加 `QUAL_CONTEXTS` / `qual_pool()` / `qual_list()` / `cmd_plan_qual()` |
| `invoiceloop/__main__.py` | 追加 `qualify plan` / `qualify extract` 子命令 |
| `scripts/doctouch_arms.py` | 追加 `select_sources()` 与 `--doc-list` |
| `invoiceloop/adjudicate.py` | `append_adjudication` 追加 `suggestion_artifact_sha256` / `suggestion_model` |
| `invoiceloop/workbench.py` | `RunCtx` 载入冻结建议表(只为渲染断言用);**不新增任何隐藏字段** —— 溯源由 `append_adjudication` 服务端导出 |
| `README.md` | 「For judges」三命令 quickstart + 新数字 |
| `DISCLOSURE.md` | 赛期内模块清单补 doctouch / release_profile / qual 新增 |
| `docs/RUBRIC_V01_SCORE_2026-08-06.md` | 不改;新自评另开一份 |

---

## Phase A —— 资格集确认轮(Nutrient 头牌)

### Task 0: 证据落盘助手(分阶段不可变)

**Files:**
- Create: `scripts/freeze_evidence.py`
- Test: `tests/test_freeze_evidence.py`

`runs/` 是指向 `../invoiceloop-data/runs` 的 symlink,且被 `.gitignore:10` 忽略
(`git ls-files runs/` = 0)。所以 `git add runs/...` 兑现不了「冻结状态已提交」——
它要么报 `beyond a symbolic link`,要么被忽略。仓库既有做法是把不可变副本放进
`docs/evidence/<round>/`(见 `docs/evidence/narrow_v1_2026-08-14/`、
`docs/evidence/absence_v3_2026-08-10/`),本任务把它做成一条命令。

**分阶段,不是一个 round 一个目录。** 一轮里要冻结好几次(资格轮:名单 → 提取小结 →
四臂结果;行走轮:走前工件 → 走后账本)。若每次都往同一个 `MANIFEST.sha256` 里写当次的
条目,第二次就把第一次的条目删掉了 —— 等于改写已冻结的历史,而这份 manifest 存在的
全部意义就是「这些东西在那个 commit 时是这个样子」。所以:
**`docs/evidence/<round>/<stage>/`,manifest 一旦存在就拒绝任何写入。**

- [ ] **Step 1: 写失败的测试**

新建 `tests/test_freeze_evidence.py`:

```python
"""证据落盘:分阶段不可变。已冻结的清单不许被后来的冻结改写。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import freeze_evidence  # noqa: E402


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(freeze_evidence, "REPO", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    return tmp_path, src


def test_a_second_stage_cannot_erase_the_first(repo):
    """一轮里冻结好几次。若共用一份 manifest,后一次会把前一次的条目删掉 ——
    前一个 commit 背书过的清单就此消失,而清单的全部意义就是那个背书。"""
    root, src = repo
    (src / "doc_list.json").write_text("a", encoding="utf-8")
    (src / "metrics.json").write_text("b", encoding="utf-8")
    freeze_evidence.freeze("r1", "plan", [src / "doc_list.json"])
    freeze_evidence.freeze("r1", "arms", [src / "metrics.json"])
    plan = (root / "docs/evidence/r1/plan/MANIFEST.sha256").read_text(encoding="utf-8")
    arms = (root / "docs/evidence/r1/arms/MANIFEST.sha256").read_text(encoding="utf-8")
    assert "doc_list.json" in plan and "metrics.json" not in plan
    assert "metrics.json" in arms and "doc_list.json" not in arms


def test_refreezing_the_same_stage_is_refused(repo):
    """同一阶段冻结两次 = 想改写历史。哪怕内容一模一样也拒绝:
    通过了就等于承认这个阶段可以再写一次。"""
    root, src = repo
    (src / "a.json").write_text("a", encoding="utf-8")
    freeze_evidence.freeze("r1", "plan", [src / "a.json"])
    with pytest.raises(SystemExit, match="已冻结"):
        freeze_evidence.freeze("r1", "plan", [src / "a.json"])


def test_manifest_records_the_bytes_that_were_copied(repo):
    """清单里的哈希必须是落盘副本自己的哈希 —— 不然它证明不了任何事。"""
    root, src = repo
    (src / "a.json").write_text("hello", encoding="utf-8")
    freeze_evidence.freeze("r1", "plan", [src / "a.json"])
    stage = root / "docs/evidence/r1/plan"
    digest, name = (stage / "MANIFEST.sha256").read_text(
        encoding="utf-8").split()
    assert name == "a.json"
    assert digest == hashlib.sha256((stage / "a.json").read_bytes()).hexdigest()


def test_a_missing_artifact_blocks(repo):
    """要冻的东西不在 = 上一步没跑成。半份证据比没有更糟。"""
    root, src = repo
    with pytest.raises(SystemExit, match="不存在"):
        freeze_evidence.freeze("r1", "plan", [src / "nope.json"])
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_freeze_evidence.py -x -q
```
预期:`ModuleNotFoundError: No module named 'freeze_evidence'`

- [ ] **Step 3: 写 `scripts/freeze_evidence.py`**

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_freeze_evidence.py -q
```
预期:`4 passed`

- [ ] **Step 5: 确认 `runs/` 的确进不了仓库(这是本任务存在的理由)**

```bash
ls -la runs | head -1
grep -n '^runs$' .gitignore
git ls-files runs/ | wc -l
```
预期:`runs -> ../invoiceloop-data/runs`;`.gitignore` 第 10 行是 `runs`;tracked 文件数 `0`。

- [ ] **Step 6: 提交**

```bash
git add scripts/freeze_evidence.py tests/test_freeze_evidence.py
git commit -m "Add a stage-immutable evidence freezer: runs/ is a gitignored symlink, and a second freeze must never rewrite a manifest an earlier commit already endorsed."
```

---

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
        """池里混进一份跑过的文档 = 「未曝光」这个头条主张直接是假的。

        三个曝光集**都必须是冻结的**:活查 discover_dual_mode() 在 Task 4
        之后必然自打嘴巴 —— 那 200 份提取完就有了双模式响应,却仍在池里。
        冻结时的盘上快照由 cmd_plan_qual 写进 doc_list.json。
        """
        pool = set(heldout.qual_pool())
        manifest = {
            e["doc_id"] for e in json.loads(
                (REPO / "docs" / "development_exposure_manifest.json")
                .read_text(encoding="utf-8"))["doc_ids"]}
        sealed4 = set(json.loads(
            (REPO / "docs" / "sealed4_doc_list.json")
            .read_text(encoding="utf-8"))["doc_ids"])
        assert not pool & manifest, "开发期曝光清单里的文档进了资格池"
        assert not pool & sealed4, "SEALED-4 已抽的 100 份进了资格池"

    def test_frozen_list_never_touched_anything_on_disk_at_freeze_time(self):
        """冻结那一刻盘上有双模式响应的文档,一份都不在名单里。

        名单落盘后这条永远为真(两边都是冻结值);Task 3 另有一条**活查**
        的闸,那才是提取前的实时把关。名单还没落盘就跳过。
        """
        path = REPO / "docs" / "qual_narrow_doc_list.json"
        if not path.is_file():
            pytest.skip("名单尚未冻结(Task 3 之前)")
        spec = json.loads(path.read_text(encoding="utf-8"))
        touched = set(spec["dual_mode_on_disk_at_freeze"])
        assert touched, "冻结时的盘上快照不能是空的 —— 空集让这条测试无话可说"
        assert not set(spec["doc_ids"]) & touched

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
    assert payload["dual_mode_on_disk_at_freeze"], "盘上快照必须落盘,否则复算时无从判断"
    assert not set(ids) & set(payload["dual_mode_on_disk_at_freeze"])
    assert not list((tmp_path / "raw").glob("*.json")), "plan 阶段不许有任何响应"
```

- [ ] **Step 2: 跑测试确认失败,并核实池大小**

```bash
.venv/bin/python -m pytest tests/test_qualify.py -x -q
```
预期:`AttributeError: module 'invoiceloop.heldout' has no attribute 'qual_pool'`(6 条全红)

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
    # 冻结这一刻「盘上已有双模式响应」的快照。活查这件事只在提取之前有意义:
    # 提取一跑完,本轮 200 份自己就有响应了,再活查就是自打嘴巴。
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from doctouch_arms import discover_dual_mode  # noqa: E402

    touched = sorted(discover_dual_mode())
    leaked = sorted(set(ids) & set(touched))
    if leaked:
        raise RuntimeError(
            f"名单里有 {len(leaked)} 份盘上已有双模式响应 —— 「未曝光」不成立:"
            f"{leaked[:5]}")
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
        "dual_mode_on_disk_at_freeze": touched,
        "dual_mode_on_disk_sha256": doc_ids_line_digest(touched),
        "doc_ids": ids,
    }
    (workspace / "doc_list.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"pool={payload['pool_size']}  qual n={n}  context={context}")
    print(f"冻结时盘上双模式 {len(touched)} 份,与名单交集 0")
    print(f"pool_sha256={payload['pool_sha256']}")
    print(f"doc_ids_sha256={payload['doc_ids_sha256']}")
    print(f"名单已落盘:{workspace / 'doc_list.json'} —— 先提交,再调用")
    return ids
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_qualify.py -q
```
预期:`5 passed, 1 skipped`(名单尚未冻结,`test_frozen_list_...` skip)

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
预期:打印 `pool=4831  qual n=3  context=qual-narrow-v1`、`冻结时盘上双模式 660 份,与名单交集 0`、两行 sha256、名单落盘路径。

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

再把臂循环里 `if not arm_dir.exists():` 那段换成带身份核对的版本 —— 原写法只看目录在不在,
**换了策略跑进同一个 out 目录会静默复用上一次的结果**:

```python
    for arm in ("HAR-0001", "HAR-0021", "HAR-0023"):
        arm_dir = out / "arms" / arm
        active = active_for(arm)
        identity = {
            "harness_id": arm,
            "policy_digest": active["policy_digest"],
            "policy_sha256": active["policy_sha256"],
            "schema_sha256": active["schema_sha256"],
            "doc_ids_sha256": hashlib.sha256(
                "\n".join(sorted(doc_ids)).encode("utf-8")).hexdigest(),
        }
        id_path = arm_dir / "arm_identity.json"
        if arm_dir.exists():
            prior = json.loads(id_path.read_text(encoding="utf-8")) \
                if id_path.is_file() else None
            if prior != identity:
                raise SystemExit(json.dumps({
                    "fatal": "臂目录已存在,但策略/schema/名单与本次不同 —— "
                             "复用它会把上一次的结果当成这一次的",
                    "arm": arm, "dir": str(arm_dir),
                    "prior": prior, "now": identity,
                }, ensure_ascii=False, indent=1))
            print(f"复用 {arm}(身份一致)", flush=True)
        else:
            print(f"跑 {arm}…", flush=True)
            with _corpus_environment(ws), frozen_harness(active):
                pipeline.run(doc_ids, arm_dir, render_crops=False,
                             include_vision=False, out_of_calibration=True)
            id_path.write_text(
                json.dumps(identity, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
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

臂身份那段没有单测:它的失败面是「换策略重跑同一个 out 目录」,构造这个场景要跑两次完整流水线,
成本远高于收益。执行 Task 5 时目录是空的,走的是新建分支;真要复用时那条 SystemExit 会当场报出来。

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
预期:`pool=4831  qual n=200  context=qual-narrow-v1`、`冻结时盘上双模式 660 份,与名单交集 0`、`pool_sha256=…`、`doc_ids_sha256=…`、名单落盘路径。**把两个 sha256 抄进下一步的协议正文。** 交集非 0 会直接 RuntimeError,提取跑不起来。

```bash
cp runs/qual-narrow-2026-08-22/doc_list.json docs/qual_narrow_doc_list.json
.venv/bin/python scripts/freeze_evidence.py \
  --round qual-narrow-2026-08-22 --stage plan \
  runs/qual-narrow-2026-08-22/doc_list.json
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
- **预算要给够。** 实测 ~27 credits/次,400 次 ≈ 10,800;`cmd_extract` 的默认
  `budget=6000` 会在第 222 次熔断(2026-08-23 实测)。给 15000。熔断本身不是故障,
  断点续跑重发同一命令即可 —— 但它会让"一轮跑完"变成两段,记进日志。

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
| P6 | D 臂 `silent_wrong` ≤ B 臂 `silent_wrong` | 窄放行只减少**打开张数**,不该让错值更多地静默通过。这是本轮的安全终点,与 P4 的真静默分开报 |

零触达率按二项分布报 95% Wilson 区间(n=200,点估计 ±7 个百分点量级)。
**区间与点估计一起进对外句子** —— 200 份的一个百分数看起来比它实际的精度高。

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
git add docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md \
        docs/qual_narrow_doc_list.json \
        docs/evidence/qual-narrow-2026-08-22/plan/
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
  --workspace runs/qual-narrow-2026-08-22 --budget 15000 \
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
.venv/bin/python scripts/freeze_evidence.py \
  --round qual-narrow-2026-08-22 --stage extract \
  runs/qual-narrow-2026-08-22/extract_summary.json
git add docs/evidence/qual-narrow-2026-08-22/extract/
git commit -m "Record the qualification-round extraction summary: 400 dual-mode calls over the 200 never-touched documents."
```

`raw/`(400 份响应,约数十 MB)留在 `runs/` 不入库,与 sealed4 同待遇;
`extract_summary.json` 里的 `done/failed/spent_estimate` 加上 `doc_list.json` 的
`doc_ids_sha256` 就足以复算「跑了哪 200 份、成没成」。

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

- [ ] **Step 4: 算零触达率的 95% 区间与 P6**

```bash
.venv/bin/python -c "
import json, math, pathlib
m = json.loads(pathlib.Path(
    'runs/qual-narrow-2026-08-22/doctouch/doctouch_metrics.json').read_text())
def wilson(k, n, z=1.96):
    if not n: return (None, None)
    ph = k / n; d = 1 + z*z/n
    c = (ph + z*z/(2*n)) / d
    h = z*math.sqrt(ph*(1-ph)/n + z*z/(4*n*n)) / d
    return (round(100*(c-h), 1), round(100*(c+h), 1))
for arm, rec in m['arms'].items():
    a = rec['metrics'].get('ALL', {})
    lo, hi = wilson(a.get('zero_touch_docs', 0), a.get('docs', 0))
    print(f\"{arm:36s} 零触达 {a.get('zero_touch_pct')}% [95% CI {lo}–{hi}]  \"
          f\"silent_wrong {a.get('silent_wrong')}\")
"
```
预期:四行,每行带点估计、Wilson 区间与 `silent_wrong`。
D 臂的 `silent_wrong` ≤ B 臂即 P6 成立。

- [ ] **Step 5: 写结果文档**

新建 `docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md`,骨架如下,方括号处填 Step 1–3 的实测值。**先写预测栏,再填实测栏,不许回改预测。**

```markdown
# QUALIFICATION_NARROW_2026-08-22 结果(未曝光资格集,n=200)

协议:`docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md`(冻结于提取之前)
数据:`docs/evidence/qual-narrow-2026-08-22/arms/doctouch_metrics.json`
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
| P6 | D 臂 `silent_wrong` ≤ B 臂 | [填] | [成立 / 不成立] |

[逐条一句话说明。预测错了照登,不改预测、不补理由把它说圆。]

## 3. 四臂 × 三层

| 臂 | 闸 | 层 | 文档数 | 零触达 | 未决放行槽 | QA 探针槽 | 人队列槽 | 真静默 | 口径争议 |
|---|---|---|---|---|---|---|---|---|---|
[从 doctouch_metrics.json 逐行填,strong/weak/none/ALL 四层都要有]

## 4. 可以对外说的一句话

**升级为「产品能力」的闸有四条,全过才准写,P2 只是其中一条:**

1. 无阻断:`extract_summary.json` 的 `failures` 为空。
2. 样本完整:四臂各测满 200 份,`--doc-list` 无缺件。
3. 安全:P4(真静默 ≤ 3)与 P6(D 臂 `silent_wrong` ≤ B 臂)都成立。
4. 效果:P2 成立。

任何一条不过,数字照登,措辞退回 08-18 的限定句。**猜中预测和产品安全是两回事** ——
零触达率再好看,若 D 臂让更多错值静默通过,那就不是能力是隐患。

[四条全过时:「在 200 份此前从未被本项目接触过的 DocILE 发票上,窄放行契约
(invoice_number / seller_name / amount_due 三字段)让 [X]%(95% CI [lo]–[hi])的文档
在路由阶段无需任何人打开。」后面必须跟 ARCHITECTURE §8 的三条限定。
**区间不能省** —— 200 份的一个百分数看起来比它实际的精度高。]

[P2 不成立时:保留 08-18 §6 的限定句原文,并写明本轮实测值与它的关系。]

## 5. 这句话证明不了什么

- 不是「抽取更准了」。零触达是**路由时属性**,与抽取正确性无关。
- 不是「这三个字段一定是对的」。窄放行只承诺:这三个字段在本策略下达到了
  免复核的证据门槛;其余字段照旧进支持矩阵。
- DocILE 是一个语料。换域名、换版式、换语言,这个数字不迁移。
```

- [ ] **Step 6: 提交**

```bash
.venv/bin/python scripts/freeze_evidence.py \
  --round qual-narrow-2026-08-22 --stage arms \
  runs/qual-narrow-2026-08-22/doctouch/doctouch_metrics.json \
  runs/qual-narrow-2026-08-22/doctouch/arms/HAR-0023/routing_report.json
git add docs/evidence/qual-narrow-2026-08-22/arms/ \
        docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md
git commit -m "Report the qualification round on 200 never-touched documents against its five pre-registered predictions."
```

---

## Phase B —— ADK×HITL 协议内行走(ATA 头牌)

一句话:agent(Gemini,走 ADK)以**协议内一等公民**身份参与人工行走 —— 建议从第一槽就在场、每条账本行带完整溯源、**零权威**(不能 accept / reject / 改任何闸)。

Task 6–7 是代码,Task 8–10 是跑轮。

### Task 6: 溯源由服务端导出并与账本对账

**Files:**
- Create: `invoiceloop/suggest_provenance.py`
- Modify: `invoiceloop/adjudicate.py:94-152`(校验与导出)、`:256-282`(entry)
- Test: `tests/test_suggest_provenance.py`

**设计要点(与本计划第一版不同)**:溯源**不经过浏览器**。
`suggestion_artifact_sha256` 与 `suggestion_model` 是 `(run, doc, field)` 加冻结建议表的
纯函数,`append_adjudication` 自己查得到。让页面把它们发上来,等于让旧标签页或改过的请求
决定证据身份,而后端只查了格式。所以:

- 页面只发 `suggestion_seen`(它必须来自渲染 —— 记的是人当时看见了什么,后端事后推不出来)。
- 后端查冻结表导出两个溯源字段,**并与 `suggestion_seen` 三向对账**:
  表里有 / 账本说没看见 → 阻断;表里没有 / 账本说看见了 → 阻断;
  `agree:<值>` 的值与表里冻结的 `displayed_value` 不符 → 阻断。
- 没有冻结表的 run(demo、旧轮)一切照旧,两个字段不出现。
- **冻结表本身也要被核。** 只信盘上那份 JSON 是不够的:走中途多注入一个 reader,
  页面可能显示 `split`,而 `derive` 照样把原 reader 的哈希记进账本;把 TSV 和 JSON
  一起改掉,两边又自洽。所以 `load()` 每次都重算 —— live TSV 的 sha 必须等于冻结的
  `artifact_sha256`、`invoice_read.json` 必须等于 `upstream_sha256`、
  `build_slots()` 的全量结果必须与冻结 `slots` **逐槽相等**;并且当走前副本已经
  提交进 `docs/evidence/<round>/prewalk/` 时,盘上这份 JSON 必须等于那份副本。

第三条对账正是 P1 覆盖率的**写时**保障:「整套隐藏字段丢失」这种故障在落账那一刻就被挡住,
不必等到事后统计 —— 而事后统计的分母若取自账本自己,恰恰会让这种故障从分母里消失。

- [ ] **Step 1: 写失败的测试**

新建 `tests/test_suggest_provenance.py`:

```python
"""建议工件溯源:账本每槽能不能说清「当时屏幕上那条建议出自哪份工件」,
以及说不清的时候会不会阻断。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoiceloop import suggest_provenance

SHA_A = "a" * 64
MODEL = "gemini-3.7-flash"


def _map(**over):
    base = {
        "round": "test-round",
        "frozen_at": "2026-08-25T09:00:00+00:00",
        "prompt_digest": "p" * 64,
        "schema_digest": "s" * 64,
        "readers": {"adk-invoice": {
            "model": MODEL, "artifact": "vision/answers6.adk-invoice.tsv",
            "artifact_sha256": SHA_A}},
        "slots": {"doc1|invoice_number": {
            "tag": "adk-invoice", "displayed_value": "INV-1",
            "row_sha256": "r" * 64, "reading_sha256": "d" * 64}},
    }
    base.update(over)
    return base


class TestDerive:
    def test_returns_the_artifact_and_model_for_a_frozen_slot(self):
        assert suggest_provenance.derive(
            _map(), "doc1", "invoice_number", "agree:INV-1") == (SHA_A, MODEL)

    def test_a_slot_the_reviewer_saw_but_the_map_never_froze_blocks(self):
        """走中途补生成的建议会长这样 —— 废臂条款点名的那条,写时就该挡。"""
        with pytest.raises(ValueError, match="冻结表里没有"):
            suggest_provenance.derive(
                _map(), "doc2", "invoice_number", "agree:INV-9")

    def test_a_frozen_slot_the_ledger_claims_nobody_saw_blocks(self):
        """P1 覆盖率最该发现的故障:该展示建议的槽,账本却一个字都没记。
        取自账本的分母会让它消失,所以要在写时挡。"""
        with pytest.raises(ValueError, match="冻结表里有"):
            suggest_provenance.derive(_map(), "doc1", "invoice_number", None)

    def test_a_displayed_value_that_drifted_from_the_frozen_row_blocks(self):
        """TSV 在冻结之后被改过 —— 人看见的与工件里的不是同一条。"""
        with pytest.raises(ValueError, match="与冻结值不符"):
            suggest_provenance.derive(
                _map(), "doc1", "invoice_number", "agree:INV-CHANGED")

    def test_split_and_blind_need_no_value_match(self):
        """读者分歧/全弃权时屏幕上没有可比的值,只要槽在表里就算对得上。"""
        assert suggest_provenance.derive(
            _map(), "doc1", "invoice_number", "split") == (SHA_A, MODEL)

    def test_no_frozen_map_means_no_provenance_and_no_blocking(self):
        """demo 与旧轮没有冻结表,必须照常能裁决。"""
        assert suggest_provenance.derive(None, "doc1", "invoice_number",
                                         "agree:INV-1") is None
        assert suggest_provenance.derive(None, "doc1", "invoice_number",
                                         None) is None


class TestLoadVerifiesTheLiveArtifacts:
    """冻结表说了什么不重要,盘上此刻是什么才重要。"""

    @staticmethod
    def _run(tmp_path: Path) -> Path:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import suggest_provenance_freeze

        run_dir = tmp_path / "run-0001"
        (run_dir / "vision").mkdir(parents=True)
        (run_dir / "vision" / "answers6.adk-invoice.tsv").write_text(
            "doc\tfield\tvalue\tprinted_label\tnote\n"
            "doc1\tinvoice_number\tINV-1\tNONE\tgemini-3.7-flash\n",
            encoding="utf-8")
        (run_dir / "vision" / "invoice_read.json").write_text(json.dumps({
            "advisory": True, "source": "adk_invoice_read",
            "model": MODEL,
            "docs": {"doc1": {"invoice_number": "INV-1", "model": MODEL}},
            "failed": [],
        }), encoding="utf-8")
        suggest_provenance_freeze.freeze(
            run_dir, tag="adk-invoice", round_name="t",
            frozen_at="2026-08-25T09:00:00+00:00")
        return run_dir

    def test_a_clean_run_loads(self, tmp_path):
        run_dir = self._run(tmp_path)
        prov = suggest_provenance.load(run_dir, repo_root=tmp_path)
        assert prov["slots"]["doc1|invoice_number"]["displayed_value"] == "INV-1"

    def test_a_second_reader_injected_after_the_freeze_blocks(self, tmp_path):
        """走中途多注入一个 tag:页面会因读者分歧显示 split,而按 slot 查表
        仍查得到原 tag 的哈希 —— 账本会记下一份指错工件的完整溯源。"""
        run_dir = self._run(tmp_path)
        (run_dir / "vision" / "answers6.other.tsv").write_text(
            "doc\tfield\tvalue\tprinted_label\tnote\n"
            "doc1\tseller_name\tACME\tNONE\tsomething-else\n",
            encoding="utf-8")
        with pytest.raises(ValueError, match="冻结之后变过"):
            suggest_provenance.load(run_dir, repo_root=tmp_path)

    def test_an_edited_display_row_blocks(self, tmp_path):
        run_dir = self._run(tmp_path)
        tsv = run_dir / "vision" / "answers6.adk-invoice.tsv"
        tsv.write_text(tsv.read_text(encoding="utf-8").replace("INV-1", "INV-2"),
                       encoding="utf-8")
        with pytest.raises(ValueError, match="冻结之后变过"):
            suggest_provenance.load(run_dir, repo_root=tmp_path)

    def test_tsv_and_map_edited_together_still_blocks_against_the_repo_copy(
            self, tmp_path):
        """两边一起改就自洽了 —— 仓库里那份走前副本是唯一改不动的锚。"""
        run_dir = self._run(tmp_path)
        live = run_dir / "vision" / suggest_provenance.FILENAME
        stage = tmp_path / "docs" / "evidence" / "t" / "prewalk"
        stage.mkdir(parents=True)
        import hashlib

        (stage / "MANIFEST.sha256").write_text(
            f"{hashlib.sha256(live.read_bytes()).hexdigest()}  "
            f"{suggest_provenance.FILENAME}\n", encoding="utf-8")
        tsv = run_dir / "vision" / "answers6.adk-invoice.tsv"
        tsv.write_text(tsv.read_text(encoding="utf-8").replace("INV-1", "INV-2"),
                       encoding="utf-8")
        prov = json.loads(live.read_text(encoding="utf-8"))
        prov["slots"]["doc1|invoice_number"]["displayed_value"] = "INV-2"
        prov["slots"]["doc1|invoice_number"]["row_sha256"] = hashlib.sha256(
            b"adk-invoice\tdoc1\tinvoice_number\tINV-2\tNONE\t"
            b"gemini-3.7-flash").hexdigest()
        prov["readers"]["adk-invoice"]["artifact_sha256"] = hashlib.sha256(
            tsv.read_bytes()).hexdigest()
        live.write_text(json.dumps(prov, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError, match="走前副本不符|冻结之后变过"):
            suggest_provenance.load(run_dir, repo_root=tmp_path)


def test_build_map_reads_every_injected_tag(tmp_path):
    """冻结的必须是**人真正看见的那一行** —— 裁决页的建议来自
    answers6.<tag>.tsv,不是 invoice_read.json。inject 会 skip 已有行、
    也会 drop 坏行,两者能漂开。"""
    vision = tmp_path / "vision"
    vision.mkdir()
    (vision / "answers6.adk-invoice.tsv").write_text(
        "doc\tfield\tvalue\tprinted_label\tnote\n"
        "doc1\tinvoice_number\tINV-1\tNONE\tgemini-3.7-flash role=payee\n"
        "doc1\tseller_name\tACME\tNONE\tgemini-3.7-flash role=payee\n",
        encoding="utf-8")
    slots = suggest_provenance.build_slots(tmp_path)
    assert sorted(slots) == ["doc1|invoice_number", "doc1|seller_name"]
    assert slots["doc1|invoice_number"]["displayed_value"] == "INV-1"
    assert slots["doc1|invoice_number"]["tag"] == "adk-invoice"
    assert len(slots["doc1|invoice_number"]["row_sha256"]) == 64
    assert slots["doc1|invoice_number"]["row_sha256"] != \
        slots["doc1|seller_name"]["row_sha256"]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_suggest_provenance.py -x -q
```
预期:`ModuleNotFoundError: No module named 'invoiceloop.suggest_provenance'`

- [ ] **Step 3: 写 `invoiceloop/suggest_provenance.py`**

```python
"""建议工件溯源:每槽记「人看见的那条建议出自哪份工件、哪个模型」。

建议本身是显示层的东西(`vision/answers6.<tag>.tsv`),它不进冻结账本 ——
这是宪章一(单一写者)。溯源要解决的是另一个问题:一年后回看某条裁决,
能不能重算出当时屏幕上那条建议。所以记的是**工件的哈希**,不是建议的值:
值能从工件复算,哈希能证明工件没被改过。

两条设计约束,都是踩过的:

1. **冻结 TSV,不是冻结读法。** 裁决页显示的建议来自 answers6.<tag>.tsv
   (workbench._vision_state ← ctx.vision ← dws.load_vision_answers)。
   invoice_read.json 只是它的上游 —— suggest_inject.inject 会跳过已有
   (doc, field)、也会丢掉坏行,两者能漂开。冻结上游等于冻结了一份
   人没看过的东西。
2. **导出在服务端,不在浏览器。** 工件哈希与模型 id 是 (run, doc, field)
   加冻结表的纯函数,append_adjudication 自己查得到。让页面用隐藏字段
   发上来,旧标签页和改过的请求就能决定证据身份。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

FILENAME = "suggestion_provenance.json"
HEADER_COLS = 5


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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_suggest_provenance.py -q
```
预期:`11 passed`(其中 `TestLoadVerifiesTheLiveArtifacts` 依赖 Task 7 的
`suggest_provenance_freeze`,先写 Task 7 的脚本再回来跑,或让这 4 条暂时红着 ——
两个任务本来就是一体的,分开只为 commit 粒度)

- [ ] **Step 5: 接进 `append_adjudication`**

`invoiceloop/adjudicate.py` 的 `append_adjudication` **不加任何新参数**。
在 `manifest = json.loads(...)` 那一行之前插入:

```python
    # 建议溯源:服务端导出,不收调用方给的值。三向对账不过 = 一行都不写。
    from .suggest_provenance import derive, load as load_provenance

    # load 会重算 live TSV / upstream / 全量 slots,并与仓库里的走前副本对锚。
    # 任何一处对不上抛 ValueError —— 与其他校验同路,一行都不写。
    provenance = derive(load_provenance(run_dir), doc_id, field, suggestion_seen)
```

在 entry 的 `if suggestion_seen is not None:` 之后追加:

```python
            if provenance is not None:
                entry["suggestion_artifact_sha256"] = provenance[0]
                entry["suggestion_model"] = provenance[1]
```

docstring 末尾追加:

```python
    suggestion_seen 之外的两个溯源字段(suggestion_artifact_sha256 /
    suggestion_model)**不接受调用方传入**:它们由 suggest_provenance.derive
    从 run 目录里走前冻结的建议表导出,并与 suggestion_seen 三向对账。
    浏览器只能提交裁决,不能提交证据身份。
```

- [ ] **Step 6: 确认旧账本与工作台没坏**

```bash
.venv/bin/python -m pytest tests/test_adjudicate.py tests/test_workbench.py \
  tests/test_narrow_round.py tests/test_suggest_provenance.py -q
```
预期:全绿。没有冻结表的 run(demo、旧轮)`derive` 返回 None,行为一字不变。

- [ ] **Step 7: 提交**

```bash
git add invoiceloop/suggest_provenance.py invoiceloop/adjudicate.py \
        tests/test_suggest_provenance.py
git commit -m "Derive suggestion provenance server-side from the frozen display rows and refuse any ledger row that disagrees with them."
```

---

### Task 7: 走前冻结建议工件

**Files:**
- Create: `scripts/suggest_provenance_freeze.py`
- Test: `tests/test_suggest_provenance.py`(追加)

**工作台不改。** 第一版打算加两个隐藏字段,现在溯源由服务端导出,
`suggestion_seen` 的渲染逻辑一行不动 —— 少一处客户端信任面,也少一处要维护的代码。

- [ ] **Step 1: 写失败的测试(追加到 `tests/test_suggest_provenance.py` 末尾)**

```python
def _run_with_suggestions(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run-0001"
    (run_dir / "vision").mkdir(parents=True)
    (run_dir / "vision" / "answers6.adk-invoice.tsv").write_text(
        "doc\tfield\tvalue\tprinted_label\tnote\n"
        "doc1\tinvoice_number\tINV-1\tNONE\tgemini-3.7-flash role=payee\n"
        "doc2\tseller_name\tBETA\tNONE\tgemini-3.7-flash role=payee\n",
        encoding="utf-8")
    (run_dir / "vision" / "invoice_read.json").write_text(json.dumps({
        "advisory": True, "source": "adk_invoice_read",
        "model": "gemini-3.7-flash",
        "docs": {"doc1": {"invoice_number": "INV-1", "model": "gemini-3.7-flash"},
                 "doc2": {"seller_name": "BETA", "model": "gemini-3.7-flash"}},
        "failed": [],
    }), encoding="utf-8")
    return run_dir


def _freeze_module():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import suggest_provenance_freeze

    return suggest_provenance_freeze


def test_freeze_covers_every_row_the_reviewer_can_see(tmp_path):
    """P1 的分母就是这张表。表里漏一行,那一槽的裁决会在写时被 derive 挡下,
    但更早的失败是这里 —— 所以冻结的是 TSV 全量,不是读法全量。"""
    run_dir = _run_with_suggestions(tmp_path)
    _freeze_module().freeze(run_dir, tag="adk-invoice", round_name="t",
                            frozen_at="2026-08-25T09:00:00+00:00")
    prov = json.loads((run_dir / "vision" / suggest_provenance.FILENAME)
                      .read_text(encoding="utf-8"))
    assert sorted(prov["slots"]) == ["doc1|invoice_number", "doc2|seller_name"]
    assert prov["readers"]["adk-invoice"]["model"] == "gemini-3.7-flash"
    assert len(prov["readers"]["adk-invoice"]["artifact_sha256"]) == 64
    assert prov["prompt_digest"] and prov["schema_digest"]
    assert prov["slots"]["doc1|invoice_number"]["reading_sha256"] != \
        prov["slots"]["doc2|seller_name"]["reading_sha256"]


def test_freeze_refuses_to_overwrite(tmp_path):
    """覆盖冻结表 = 账本里已有的哈希对不上了,而前一个 commit 已经背书过旧版。"""
    run_dir = _run_with_suggestions(tmp_path)
    freeze = _freeze_module().freeze
    freeze(run_dir, tag="adk-invoice", round_name="t",
           frozen_at="2026-08-25T09:00:00+00:00")
    with pytest.raises(SystemExit, match="拒绝覆盖"):
        freeze(run_dir, tag="adk-invoice", round_name="t",
               frozen_at="2026-08-25T10:00:00+00:00")


def test_freeze_blocks_when_a_displayed_row_has_no_reading_behind_it(tmp_path):
    """TSV 里有一行、读法里没有对应文档 —— 人看得见,却指不出它从哪来。"""
    run_dir = _run_with_suggestions(tmp_path)
    with (run_dir / "vision" / "answers6.adk-invoice.tsv").open(
            "a", encoding="utf-8") as fh:
        fh.write("doc9\tamount_due\t$1.00\tNONE\tstray\n")
    with pytest.raises(SystemExit, match="没有对应读法"):
        _freeze_module().freeze(run_dir, tag="adk-invoice", round_name="t",
                                frozen_at="2026-08-25T09:00:00+00:00")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/bin/python -m pytest tests/test_suggest_provenance.py -x -q -k freeze
```
预期:`ModuleNotFoundError: No module named 'suggest_provenance_freeze'`

- [ ] **Step 3: 写 `scripts/suggest_provenance_freeze.py`**

```python
#!/usr/bin/env python3
"""建议预生成之后冻结 —— 走前跑一次,走中途不跑。

冻结的是**人真正会看见的那些行**:vision/answers6.<tag>.tsv 的每一行,
连同它背后那份读法的摘要。整表 sha256 作为工件哈希进账本。

已存在则拒绝覆盖:溯源表被改写过,账本里已有的哈希就对不上了 ——
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
    INVOICE_READ_SYSTEM, READ_USER_PROMPT, SUGGEST_TAG, InvoiceReading,
)


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def freeze(run_dir: Path, *, tag: str, round_name: str,
           frozen_at: str) -> Path:
    run_dir = Path(run_dir)
    out = run_dir / "vision" / suggest_provenance.FILENAME
    if out.exists():
        raise SystemExit(json.dumps({
            "fatal": "溯源表已存在,拒绝覆盖 —— 账本里已有的哈希会对不上。"
                     "要重来就换一个 run。",
            "path": str(out),
        }, ensure_ascii=False, indent=1))

    tsv = run_dir / "vision" / f"answers6.{tag}.tsv"
    packed = json.loads((run_dir / "vision" / "invoice_read.json")
                        .read_text(encoding="utf-8"))
    top_model = str(packed.get("model") or "")
    readings = packed.get("docs") or {}

    slots = suggest_provenance.build_slots(run_dir)
    orphans = sorted(k for k in slots if k.split("|")[0] not in readings)
    if orphans:
        raise SystemExit(json.dumps({
            "fatal": "有展示行没有对应读法 —— 人看得见,却指不出它从哪来",
            "slots": orphans,
        }, ensure_ascii=False, indent=1))
    for key, slot in slots.items():
        slot["reading_sha256"] = suggest_provenance.record_digest(
            readings[key.split("|")[0]])

    if packed.get("failed"):
        print(json.dumps({
            "warning": "有读法失败的文档 —— 它们没有工件,也不会有展示行。"
                       "结果文档必须写出失败数,不能当成 100% 覆盖。",
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
            "artifact": f"vision/answers6.{tag}.tsv",
            "artifact_sha256": hashlib.sha256(tsv.read_bytes()).hexdigest(),
            "upstream": "vision/invoice_read.json",
            "upstream_sha256": hashlib.sha256(
                (run_dir / "vision" / "invoice_read.json").read_bytes()).hexdigest(),
        }},
        "slots": slots,
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
        "frozen_slots": len(prov["slots"]),
        "artifact_sha256": prov["readers"][args.tag]["artifact_sha256"][:16] + "…",
        "prompt_digest": prov["prompt_digest"][:16] + "…",
        "schema_digest": prov["schema_digest"][:16] + "…",
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
.venv/bin/python -m pytest tests/test_suggest_provenance.py -q
```
预期:`14 passed`

- [ ] **Step 5: 提交**

```bash
git add scripts/suggest_provenance_freeze.py tests/test_suggest_provenance.py
git commit -m "Freeze the display rows the reviewer will actually see, not the upstream readings they were derived from."
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
from invoiceloop.release_profile import parse_release_profile  # noqa: E402

SALT = "invoiceloop-qual-adk-walk-v1"
AUTO = ("auto_accept", "auto_absent")


def queue_slots(routes: list[dict], policy: dict) -> list[tuple[str, str]]:
    """工作台**真的会排进队列**的 (doc_id, field)。

    不能用「任意非 auto 路由」:HAR-0023 带 release_profile,工作台走的是
    workbench._walk_release_profile —— 只有 gating 字段的待裁决槽和 QA 探针
    进队列。按非 auto 抽,会抽到打开之后队列是空的文档。
    这里复用同一个谓词,改了那边这里必须跟着改。

    Task 10 的完整性闸也吃这个函数:「该走的槽走完了没有」与「该抽哪些文档」
    必须是同一个定义,两处各写一遍迟早会分叉。
    """
    profile = parse_release_profile(policy or {})
    gate = profile["fields"] if profile else None
    out = set()
    for row in routes:
        codes = [str(c) for c in (row.get("reason_codes") or [])]
        is_qa = any(c.startswith("QA_SAMPLE") for c in codes)
        in_q = row.get("in_human_queue", row.get("requires_adjudication"))
        if in_q is None:
            in_q = row.get("route") not in AUTO
        if is_qa or (in_q and (gate is None or row["field"] in gate)):
            out.add((str(row["doc_id"]), str(row["field"])))
    return sorted(out)


def eligible(routes: list[dict], policy: dict) -> list[str]:
    """队列槽 ≥1 的文档。"""
    return sorted({doc for doc, _ in queue_slots(routes, policy)})


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

    report = json.loads(args.routing_report.read_text(encoding="utf-8"))
    pool = eligible(report["routes"], report.get("policy") or {})
    ids = pick(pool, args.n)
    payload = {
        "round": "qual-adk-walk",
        "n": args.n,
        "source": str(args.routing_report),
        "eligibility": "臂 D(HAR-0023)下 workbench._walk_release_profile 会排进队列的槽 ≥1(gating 字段待裁决 或 QA 探针)",
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

加一条回归测试 `tests/test_qual_walk_plan.py`,把「抽到空队列文档」这个失败钉住:

```python
"""行走集抽样必须与工作台队列同一个谓词 —— 否则会抽到打开后无槽可走的文档。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import qual_walk_plan  # noqa: E402

NARROW = {"release_profile": {"id": "payment_required_v1",
                              "fields": ["invoice_number", "seller_name",
                                         "amount_due"]}}


def test_a_document_whose_only_review_slot_is_non_gating_is_not_eligible():
    """date_due 进不了 payment_required_v1 的行走队列 —— 抽中它,
    复核者打开会看到一个空队列。"""
    routes = [{"doc_id": "d1", "field": "date_due", "route": "review",
               "in_human_queue": True, "reason_codes": []}]
    assert qual_walk_plan.eligible(routes, NARROW) == []


def test_a_gating_review_slot_is_eligible():
    routes = [{"doc_id": "d1", "field": "invoice_number", "route": "review",
               "in_human_queue": True, "reason_codes": []}]
    assert qual_walk_plan.eligible(routes, NARROW) == ["d1"]


def test_a_qa_probe_is_eligible_even_on_a_non_gating_field():
    """QA 探针无视闸字段集进队列(document_touch_metrics 也是这么算的)。"""
    routes = [{"doc_id": "d1", "field": "date_due", "route": "review",
               "in_human_queue": True, "reason_codes": ["QA_SAMPLE_ABSENT"]}]
    assert qual_walk_plan.eligible(routes, NARROW) == ["d1"]


def test_census_policy_keeps_every_review_slot():
    """普查策略没有 release_profile,工作台不裁剪队列。"""
    routes = [{"doc_id": "d1", "field": "date_due", "route": "review",
               "in_human_queue": True, "reason_codes": []}]
    assert qual_walk_plan.eligible(routes, {}) == ["d1"]
```

```bash
.venv/bin/python -m pytest tests/test_qual_walk_plan.py -q
```
预期:`4 passed`

注意 `doc_ids_sha256` 用的是 `"\n".join(ids)` 的 sha256 —— 与 `hitl_narrow_setup._load_docs` 的校验口径一致(那里也是 `"\n".join(doc_ids)`),不是 `doc_ids_line_digest`。两个口径在这里恰好同值(ids 已排序),但校验方读的是前者,所以就按前者写。

- [ ] **Step 2: 抽名单**

```bash
.venv/bin/python scripts/qual_walk_plan.py \
  --routing-report runs/qual-narrow-2026-08-22/doctouch/arms/HAR-0023/routing_report.json \
  --out docs/qual_adk_walk_doc_list.json --n 20
```
预期:一段 JSON(`n` 20、两个 sha256),然后 `→ docs/qual_adk_walk_doc_list.json`。
`eligible_n` 是**队列口径**的合格数,会明显小于「非 auto 路由的文档数」——
两者相等说明谓词没生效,停下来查。

- [ ] **Step 3: 定模型并做真实探针(必须在协议冻结之前)**

协议 §3 要写死模型名,所以模型必须在这条 commit 之前定完、并且**真的调通过**。
第一版把这一步排在 Task 9,那时协议已经冻结了 —— 顺序自相矛盾。

代码默认是 `gemini-3.7-flash`(`invoiceloop/agents/runtime.py:27`),ATA 的 08-07
存证用的是 `gemini-3.6-flash`。**用默认的 3.7**:硬性要求只说 Gemini 3.5+,3.7 满足;
跟着代码默认走可以少一处「文档说 A、代码跑 B」的裂缝。

探针必须是**一次真实调用**,不是打印常量。用仓库内嵌样本,不碰资格集
(资格集的任何一份在行走轮开始前都不许被模型看过):

```bash
set -a && . ./.env && set +a && \
.venv/bin/python -m invoiceloop demo --out /tmp/adk-probe >/dev/null && \
.venv/bin/python -c "
import json, pathlib, sys
sys.path.insert(0, '.')
from invoiceloop.agents.invoice_read import load_page_images, make_invoice_reader
from invoiceloop.agents.runtime import DEFAULT_GEMINI_MODEL
run = sorted(pathlib.Path('/tmp/adk-probe/runs').glob('run-*'))[-1]
doc = sorted({r['doc_id'] for r in json.loads(
    (run / 'support_matrix.json').read_text())['rows']})[0]
read = make_invoice_reader(model=DEFAULT_GEMINI_MODEL, workspace=pathlib.Path('/tmp/adk-probe'))
out = read(doc, load_page_images(run, doc))
print('model', DEFAULT_GEMINI_MODEL, '| confidence', out.confidence,
      '| seller', (out.seller_name or out.station_or_publication)[:40])
"
```
预期:一行,含 `model gemini-3.7-flash` 与一个非空读法。**调不通就停在这里** ——
把 `DEFAULT_GEMINI_MODEL` 换成能调通的那个,写进协议 §3,再往下走。冻结之后不许换。

```bash
rm -rf /tmp/adk-probe
```

- [ ] **Step 4: 写行走协议正文**

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
- 合格条件:臂 D 下 `workbench._walk_release_profile` 会排进队列的槽 ≥1 ——
  即 **gating 字段(invoice_number / seller_name / amount_due)的待裁决槽,或 QA 探针**。
  用「任意非 auto 路由」会抽到打开后队列为空的文档。合格 [填] 份,`eligible_sha256` = `<抄 Step 2>`
- 抽样:最小哈希,盐 `invoiceloop-qual-adk-walk-v1`,取 20 份。
- 名单:`docs/qual_adk_walk_doc_list.json`,`doc_ids_sha256` = `<抄 Step 2>`
- **顺序**:资格集零触达已在 `docs/QUALIFICATION_NARROW_RESULTS_2026-08-23.md`
  里算完并提交,人才碰这 20 份。行走不回写、不污染路由指标。
- 两轮独立记账,数字不拼接。

## 3. 建议:走前冻结,不走中途

修掉 HITL-narrow 自认混淆里的两条(中途注入、中途改协议)。

1. 20 份的建议在**任何裁决开始之前**全部生成完毕。
0. 模型在本协议冻结之前定完并真实调通:**`gemini-3.7-flash`**
   (`invoiceloop/agents/runtime.py::DEFAULT_GEMINI_MODEL`)。探针用仓库内嵌样本,
   不碰资格集。冻结之后换模型 = 废臂。
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
| P1 | **走前冻结表**里的槽,凡裁决过的 100% 带 `suggestion_seen` + 两个溯源字段 | 「有机结合」的结构性主张,可测试。分母取自冻结表而非账本 —— 取自账本会让「整套字段丢失」自己从分母消失 |
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

- [ ] **Step 5: 提交 —— 这一条 commit 必须先于任何裁决**

```bash
git add scripts/qual_walk_plan.py tests/test_qual_walk_plan.py \
        docs/qual_adk_walk_doc_list.json \
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
    active = _har0023_active()
    identity = {
        "harness_id": active["harness_id"],
        "policy_digest": active["policy_digest"],
        "policy_sha256": active["policy_sha256"],
        "schema_sha256": active["schema_sha256"],
        "doc_ids_sha256": hashlib.sha256(
            "\n".join(doc_ids).encode("utf-8")).hexdigest(),
        "protocol": "docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md",
    }
    id_path = run_dir / "run_identity.json"
    if run_dir.exists():
        # 「目录在就重放」会把上一次用别的策略/名单跑出来的东西当成这一次的。
        # doctouch_arms 的臂目录踩过同一个坑,这里同样处理。
        prior = json.loads(id_path.read_text(encoding="utf-8")) \
            if id_path.is_file() else None
        if prior != identity:
            raise SystemExit(json.dumps({
                "fatal": "run 已存在,但策略/schema/名单与本次不同 —— "
                         "复用它会把上一次的结果当成这一次的",
                "prior": prior, "now": identity,
            }, ensure_ascii=False, indent=1))
        print(f"run 已存在且身份一致,重放:{run_dir}")
    else:
        with _corpus_environment(ws), frozen_harness(active):
            pipeline.run(doc_ids, run_dir,
                         render_crops=not args.no_crops,
                         include_vision=False, out_of_calibration=True)
        id_path.write_text(
            json.dumps(identity, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

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

- [ ] **Step 2: 先提交 setup 脚本,再跑它**

`snapshot._code_revision` 跑的是 `git status --porcelain --untracked-files=no`
(`invoiceloop/snapshot.py:62-64`)—— **未跟踪的文件不算脏**。所以拿一个还没提交的
`qual_adk_walk_setup.py` 起 run,`input_manifest` 里会盖一个干干净净的 HEAD sha,
而「这批数字是哪份代码产生的」这个指纹于是是假的。顺序必须是先提交后跑。

```bash
.venv/bin/python -m pytest tests/test_qual_walk_plan.py tests/test_freeze_evidence.py \
  tests/test_suggest_provenance.py -q
git add scripts/qual_adk_walk_setup.py
git commit -m "Add the ADK walk setup: assemble from the qualification corpus and run HAR-0023 frozen."
git status --porcelain --untracked-files=no
```
预期:测试全绿;最后一条**无输出**(工作树干净),否则 run 会被盖上假指纹。

- [ ] **Step 3: 装配并跑流水线**

```bash
.venv/bin/python scripts/qual_adk_walk_setup.py
```
预期:一段 JSON,`docs: 20`、`harness_id: "HAR-0023"`、`touch` 里 `docs: 20`、以及两条 next 命令。

- [ ] **Step 4: 写 `scripts/writeset.py` 与它的测试**

P5「零权威」原先只查了三件事,其中最实的一条是「没有裁决署名是模型名」——
那只证明没人把模型名填进 `adjudicator`,证明不了 agent 没动过别的东西。
真要证的是:模型那一趟**只碰了 `vision/` 与 `agent_calls/`**,账本、门禁报告、
快照一个字节没动。

新建 `scripts/writeset.py`:

```python
#!/usr/bin/env python3
"""run 目录的文件哈希快照与差集 —— 用来证明某一趟只动了该动的东西。

snapshot 存一份 {相对路径: sha256};diff 拿旧快照与当前状态比,
输出新增/删除/改动的相对路径。零依赖,不读墙钟。
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
    ap.add_argument("--before", type=Path,
                    help="diff 用:之前那份快照")
    args = ap.parse_args()
    if args.command == "snapshot":
        payload = snapshot(args.run_dir)
    else:
        if args.before is None:
            raise SystemExit("diff 需要 --before")
        payload = diff(json.loads(args.before.read_text(encoding="utf-8")),
                       snapshot(args.run_dir))
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps(payload if args.command == "diff"
                     else {"files": len(payload)},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
```

新建 `tests/test_writeset.py`:

```python
"""写集:证明某一趟只动了该动的东西。改了账本却报"干净"是这里唯一要挡的失败。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import writeset  # noqa: E402


def test_a_modified_ledger_shows_up_as_changed(tmp_path):
    """agent 那一趟若碰了 adjudication_ledger.jsonl,P5 必须看得见。"""
    (tmp_path / "vision").mkdir()
    ledger = tmp_path / "adjudication_ledger.jsonl"
    ledger.write_text("{}\n", encoding="utf-8")
    before = writeset.snapshot(tmp_path)
    ledger.write_text("{}\n{}\n", encoding="utf-8")
    (tmp_path / "vision" / "answers6.adk-invoice.tsv").write_text(
        "x\n", encoding="utf-8")
    d = writeset.diff(before, writeset.snapshot(tmp_path))
    assert "adjudication_ledger.jsonl" in d["modified"]
    assert "vision/answers6.adk-invoice.tsv" in d["added"]
    assert [x for x in d["changed"] if not x.startswith("vision/")] == \
        ["adjudication_ledger.jsonl"]


def test_a_deleted_artifact_is_not_silently_clean(tmp_path):
    """只比"现在有什么"会把删除当成没发生。"""
    (tmp_path / "gate_report.json").write_text("{}", encoding="utf-8")
    before = writeset.snapshot(tmp_path)
    (tmp_path / "gate_report.json").unlink()
    assert writeset.diff(before, writeset.snapshot(tmp_path))["removed"] == \
        ["gate_report.json"]
```

```bash
.venv/bin/python -m pytest tests/test_writeset.py -q
git add scripts/writeset.py tests/test_writeset.py
git commit -m "Record what a run directory looked like before and after, so zero authority can be shown as a write-set rather than an absent signature."
```
预期:`2 passed`

- [ ] **Step 5: 记录 ADK 跑之前的写集**

```bash
.venv/bin/python scripts/writeset.py snapshot \
  --run-dir runs/qual-adk-walk/runs/run-0001 \
  --out runs/qual-adk-walk/writeset_before.json
```
预期:`{"files": <数百>}`

- [ ] **Step 6: 预生成 20 份建议(唯一的 Gemini 花费,模型已在 Task 8 Step 3 冻结)**

不传 `--model`,让它走 `DEFAULT_GEMINI_MODEL` —— 写死一个字符串就是再造一处会漂的真相。

```bash
set -a && . ./.env && set +a && \
.venv/bin/python scripts/hitl_adk_invoice_read.py \
  --run-dir runs/qual-adk-walk/runs/run-0001 2>&1 | tail -30
```
预期:逐份打印 `[i/20] <doc_id>`,末尾一段 JSON 含 `"docs": 20`、`"failed": []`、`"injected"`。
`failed` 非空则退出码为 1 —— 把失败明细带进结果文档,**不要为了凑满 20 而重跑换模型**(换模型 = 废臂)。

- [ ] **Step 7: 算 ADK 那一趟的写集**

```bash
.venv/bin/python scripts/writeset.py diff \
  --run-dir runs/qual-adk-walk/runs/run-0001 \
  --before runs/qual-adk-walk/writeset_before.json \
  --out runs/qual-adk-walk/runs/run-0001/agent_writeset.json
```
预期:`changed` 里**每一项**都以 `vision/` 或 `agent_calls/` 开头。
出现别的路径就停下来 —— 那是 P5 的实证反例,不是噪声。

- [ ] **Step 8: 冻结溯源工件**

```bash
.venv/bin/python scripts/suggest_provenance_freeze.py \
  --run-dir runs/qual-adk-walk/runs/run-0001 \
  --round qual-adk-walk-2026-08-25 \
  --frozen-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```
预期:一段 JSON,`frozen_slots` 约 40–80(20 份 × 每份 1–4 个字段)、`model: "gemini-3.7-flash"`、工件哈希与两个 digest 前缀。

- [ ] **Step 9: 提交冻结状态 —— 这一条 commit 必须先于第一条裁决**

```bash
.venv/bin/python scripts/freeze_evidence.py \
  --round qual-adk-walk-2026-08-25 --stage prewalk \
  runs/qual-adk-walk/runs/run-0001/vision/invoice_read.json \
  runs/qual-adk-walk/runs/run-0001/vision/suggestion_provenance.json \
  runs/qual-adk-walk/runs/run-0001/vision/answers6.adk-invoice.tsv \
  runs/qual-adk-walk/runs/run-0001/agent_writeset.json
git add docs/evidence/qual-adk-walk-2026-08-25/prewalk/
git commit -m "Pre-generate and freeze all twenty ADK readings before a single slot is adjudicated."
```

`runs/` 是 gitignored symlink,直接 `git add runs/...` 不成立 —— 必须走 `freeze_evidence.py`
把副本放进 `docs/evidence/`,这条 commit 才真的是「裁决前的冻结锚点」。

- [ ] **Step 10: 走**

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
预期:有建议的槽三个字段齐全;没建议的槽三个都缺。

三个字段不会「只缺一两个」—— `append_adjudication` 的三向对账在落账那一刻就挡住了:
表里有而账本没记、账本记了而表里没有、值对不上,三种都直接 ValueError,一行都不写。
所以真出问题的表现是**提交被拒**,而不是账本里出现半份溯源。被拒了就停下来查,别绕过去。

3. 协议不许中途改。想改 = 停下来,按废臂条款声明。

- [ ] **Step 11: 提交账本**

```bash
.venv/bin/python scripts/freeze_evidence.py \
  --round qual-adk-walk-2026-08-25 --stage postwalk \
  runs/qual-adk-walk/runs/run-0001/adjudication_ledger.jsonl
git add docs/evidence/qual-adk-walk-2026-08-25/postwalk/
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
import qual_walk_plan  # noqa: E402
from invoiceloop import suggest_provenance  # noqa: E402
from invoiceloop.fields import FIELD_KINDS, normalise  # noqa: E402


def exposure_sets(run_dir: Path, prov: dict, entries: list[dict]) -> dict:
    """四类曝光分开数 —— 混在一起就会把「agent 参与了」说得比事实大。

    HITL-narrow 实测(2026-08-14 那一轮,本计划写作时复算):
    队列槽 32,其中**只有 19 个有字段级建议**,13 个没有;而 16 份队列文档
    **全部**显示了文档级 ADK 卡片。所以「文档卡曝光」和「字段建议曝光」是
    两个数,「agent 在每个槽都发言」是假的。
    """
    routing = json.loads(
        (run_dir / "routing_report.json").read_text(encoding="utf-8"))
    expected = {f"{d}|{f}" for d, f in
                qual_walk_plan.queue_slots(routing["routes"],
                                           routing.get("policy") or {})}
    reading = json.loads((run_dir / "vision" / "invoice_read.json")
                         .read_text(encoding="utf-8"))
    card_docs = set(reading.get("docs") or {})
    field_slots = set(prov.get("slots") or {})
    adjudicated = {f"{e['doc_id']}|{e['field']}" for e in entries}
    return {
        "expected_queue_slots": len(expected),
        "expected_queue_docs": len({k.split("|")[0] for k in expected}),
        "document_card_docs": len(card_docs),
        "queue_docs_with_a_card": len(
            {k.split("|")[0] for k in expected} & card_docs),
        "field_suggestion_slots": len(field_slots),
        "queue_slots_with_a_field_suggestion": len(expected & field_slots),
        "queue_slots_without_a_field_suggestion": sorted(expected - field_slots),
        "adjudicated_slots": len(adjudicated),
        "queue_slots_not_adjudicated": sorted(expected - adjudicated),
        "adjudicated_outside_the_queue": sorted(adjudicated - expected),
        "walk_complete": not (expected - adjudicated),
        "_expected": sorted(expected),
        "_adjudicated": sorted(adjudicated),
    }


def provenance_coverage(entries: list[dict], prov: dict, sets: dict) -> dict:
    """P1:该走的槽走完之后,其中有建议的每一槽是不是都带**正确**的溯源。

    两处与第一版不同,都是被挑出来的:

    1. **先过完整性闸。** 分母取 frozen ∩ adjudicated 的话,没走完的槽会
       自己从分母消失 —— 走一半也能得 100%。所以 walk_complete 为假时
       coverage 照算但 P1 **不可评**,不许写成成立。
    2. **逐槽精确相等,不是非空。** 三个字段填着别的哈希一样"非空"。
       期望值由 suggest_provenance.derive 重新导出,与账本逐字节比。
    """
    frozen = prov.get("slots") or {}
    latest: dict[str, dict] = {}
    for entry in sorted(entries, key=lambda e: e["seq"]):
        latest[f"{entry['doc_id']}|{entry['field']}"] = entry
    denom_keys = [k for k in sets["_expected"]
                  if k in frozen and k in latest]
    exact = 0
    gaps = []
    for key in denom_keys:
        entry = latest[key]
        doc_id, field = key.split("|", 1)
        want = suggest_provenance.derive(
            prov, doc_id, field, entry.get("suggestion_seen"))
        got = (entry.get("suggestion_artifact_sha256"),
               entry.get("suggestion_model"))
        if want is not None and got == want:
            exact += 1
        else:
            gaps.append({"decision_id": entry["decision_id"], "slot": key,
                         "want": want, "got": got})
    return {
        "walk_complete": sets["walk_complete"],
        "evaluable": sets["walk_complete"] and bool(denom_keys),
        "denominator": "预期队列槽 ∩ 冻结建议槽 ∩ 已裁决槽",
        "denominator_n": len(denom_keys),
        "with_exact_provenance": exact,
        "coverage": round(exact / len(denom_keys), 4) if denom_keys else None,
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
    # 写集:ADK 跑之前/之后 run 目录的文件哈希差集(Task 9 Step 4 记的)。
    # 只查署名字符串证明不了「agent 没有权威」—— 它只证明没人把模型名填进
    # adjudicator。真正要证的是:模型那一趟只碰了 vision/ 与 agent_calls/,
    # 账本、门禁报告、快照一个字节没动。
    ws_path = run_dir / "agent_writeset.json"
    writeset_ok = None
    unexpected_writes: list[str] = []
    if ws_path.is_file():
        ws = json.loads(ws_path.read_text(encoding="utf-8"))
        allowed = ("vision/", "agent_calls/")
        unexpected_writes = sorted(
            path for path in (ws.get("changed") or [])
            if not path.startswith(allowed))
        writeset_ok = not unexpected_writes
    return {
        "decisions_signed_by_a_model": signed_by_model,
        "suggestion_paths_in_snapshot_contract": suggestion_in_contract,
        "claims_drafted_by_the_agent": claims_drafted_by_agent,
        "agent_writeset_recorded": writeset_ok is not None,
        "agent_writeset_clean": writeset_ok,
        "unexpected_writes": unexpected_writes,
        "clean": not (signed_by_model or suggestion_in_contract
                      or claims_drafted_by_agent or unexpected_writes)
                 and writeset_ok is True,
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
    sets = exposure_sets(run_dir, prov, entries)
    print(json.dumps({
        **base,
        "exposure": {k: v for k, v in sets.items() if not k.startswith("_")},
        "P1_provenance": provenance_coverage(entries, prov, sets),
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
e = a['exposure']
print('队列槽', e['expected_queue_slots'], '| 走完了吗', e['walk_complete'],
      '| 没走的', len(e['queue_slots_not_adjudicated']))
print('文档卡', e['queue_docs_with_a_card'], '/', e['expected_queue_docs'], '份文档',
      '| 字段建议', e['queue_slots_with_a_field_suggestion'], '/',
      e['expected_queue_slots'], '槽')
print('P1 精确溯源', a['P1_provenance']['with_exact_provenance'], '/',
      a['P1_provenance']['denominator_n'], '=', a['P1_provenance']['coverage'],
      '| 可评', a['P1_provenance']['evaluable'])
print('P2 采纳', a['P2_adoption']['adopted'], '/',
      a['P2_adoption']['agree_slots'], '=', a['P2_adoption']['adoption_rate'])
print('P3 中位', a['P3_timing']['median_seconds'], 's  (n_timed',
      a['P3_timing']['n_timed'], ')')
print('P4 模型异议被采纳', a['P4_model_dissent_adopted']['n'])
print('P5 零权威', a['P5_authority']['clean'])
"
```
预期:七行。`walk_complete` 必须为 `True`(队列没走完 → P1 不可评,不许写成成立);
P1 `coverage` 应当是 `1.0` 且 `evaluable` 为 `True`;P5 `clean` 为 `True`。

**「字段建议 / 队列槽」这一行不会是 1:1。** HITL-narrow 实测 19/32 ——
41% 的队列槽没有字段级建议,而 16/16 份队列文档都显示了文档级 ADK 卡片。
本轮大概率同样。这个数照登,它正是「文档卡曝光 ≠ 字段建议曝光」的证据。

P2/P3/P4 是实测,好坏都照登。P1 不是 1.0 就把 `gaps` 明细贴进结果文档 §0,按阻断处理。

- [ ] **Step 3: 写结果文档**

新建 `docs/QUAL_ADK_WALK_RESULTS_2026-08-25.md`:

```markdown
# QUAL_ADK_WALK_2026-08-24 结果(n=20 文档)

协议:`docs/QUAL_ADK_WALK_PROTOCOL_2026-08-24.md`(冻结于第一条裁决之前)
数据:`docs/evidence/qual-adk-walk-2026-08-25/analysis/walk_analysis.json`
走前工件:`docs/evidence/qual-adk-walk-2026-08-25/prewalk/`(冻结先于第一条裁决)
账本:`runs/qual-adk-walk/runs/run-0001/adjudication_ledger.jsonl`(sha256 见分析输出)
复算:零 API。

## 0. 臂干净吗

[没有触发废臂条款就写:协议正文、模型、建议工件、HAR-0023 策略在裁决期间均未改动。
触发了就照 HITL-narrow 先例,把改了什么、什么时候改的、影响哪些槽全写出来。]

读法失败 [填] 份。[非 0 时:那些文档没有工件,它们的槽不计入 P1 分母,也不能算进覆盖率。]

## 1. 预注册对照

| # | 预测 | 实测 | 判定 |
|---|---|---|---|
| P1 | 冻结建议槽 ∩ 已裁决槽 100% 带完整溯源(分母取自冻结表) | [填] | [成立 / 不成立] |
| P2 | agree 采纳率 ≥ 60% | [填] | [成立 / 不成立] |
| P3 | 中位耗时 ≤ 60s | [填] | [成立 / 不成立] |
| P4 | 模型异议被采纳 ≥ 1 槽 | [填] | [成立 / 不成立] |
| P5 | 零权威违反 | [填] | [成立 / 不成立] |

## 1b. 曝光分层(三个数不是一个数)

| | 数 |
|---|---|
| 预期队列槽(HAR-0023 下工作台真会排的) | [填] |
| 其中有**字段级**建议的槽 | [填] |
| 其中没有字段级建议的槽 | [填] |
| 队列文档 / 其中显示了**文档级** ADK 卡片的 | [填] / [填] |

HITL-narrow(2026-08-14)同口径复算:队列槽 32,有字段建议的 19,没有的 13;
队列文档 16 份**全部**显示了文档卡。所以「agent 在每个槽都发言」不成立,
成立的是「agent 在每份文档上都发言,在约六成的槽上给到了字段级建议」。
本轮按同样的分层报,不合并。

## 2. 「有机结合」到底证明了什么

**证明了**:一个模型可以在一条人工审批流程里**从第一槽就在场**(文档级卡片覆盖
全部队列文档)、**凡它出过字段级建议的槽**都在账本上留下可复算且精确匹配的溯源
(哪份工件、哪个模型、什么时候冻结的),而**完全不持有任何权威** —— 它不能接受、不能拒绝、不能改闸,它的输出连 review_snapshot
的 components 都进不去。P1 与 P5 是这句话的两条可测证据 —— P1 的分母是**预期队列槽 ∩ 冻结建议槽 ∩ 已裁决槽**
且队列必须走完,P5 靠 ADK 那一趟的写集(只碰 `vision/` 与 `agent_calls/`)而不是署名字符串。

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
.venv/bin/python scripts/freeze_evidence.py \
  --round qual-adk-walk-2026-08-25 --stage analysis \
  runs/qual-adk-walk/walk_analysis.json
git add scripts/qual_walk_analyze.py \
        docs/evidence/qual-adk-walk-2026-08-25/analysis/ \
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
**Where this mechanism generalises.** Parts of this system are invoice-specific
and parts are not, and the distinction is the whole point. Invoice-specific:
the field schema, the amount identity (net + tax = gross), the cross-document
duplicate-invoice-number check, and the document-type gate. Domain-neutral: the
*binding* core — the rule that
an independent reading of that page must contain it, and that two independent extraction modes
must agree. Porting to another domain means keeping the binding core and
rewriting the domain checks. That core applies wherever the support relation is
geometric — where "is this true?" reduces to "is this on the page, here?"
Receipts, purchase orders, bills of lading, remittance advices, and delivery
notes all *appear* to fall inside it: each is a page with printed values whose
provenance is a rectangle. Contracts and correspondence appear to fall outside
it, because their claims live in prose and their support relation is semantic,
not geometric. The line is not "invoice vs not-invoice"; it is "can a rectangle
carry the proof."

**NOT MEASURED.** Every domain named in this paragraph is an argument about
where the mechanism *should* transfer, not a result. This system has been
measured on one corpus — DocILE invoices — and on nothing else. No receipt, no
purchase order, no bill of lading has been run through these gates. Treat the
paragraph as a design claim to be tested, and do not cite it as evidence of
cross-domain performance.
```

「本项目不说工件证明不了的话」在这里的具体含义:rubric H 项要的是一段**设计主张**,
给了;但主张里点名的领域一个都没测过,所以紧跟一段 NOT MEASURED。两者都留着,
读的人才知道哪句是论证、哪句是结果。

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

Everything below runs on the sample documents vendored in this repository.
No API key, nothing billed, no external dataset.

```bash
git clone https://github.com/Stahl-G/invoiceloop && cd invoiceloop
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 1. Run the pipeline end to end on the vendored samples
.venv/bin/python -m invoiceloop demo --out /tmp/invoiceloop-demo

# 2. Open the review workbench on what it produced
.venv/bin/python -m invoiceloop workbench --workspace /tmp/invoiceloop-demo --port 8793

# 3. Run the test suite
.venv/bin/python -m pytest tests/ -q
```

**What step 3 does and does not cover.** The suite runs green on a clean clone,
but the tests that recompute the research numbers are skipped there: they need
the DocILE calibration archive, which is not distributed with this repository
(see `DISCLOSURE.md`). Pytest prints those as `skipped`. The research figures in
this README are recomputable from saved responses at zero API cost **by anyone
holding the archive** — that is a weaker claim than "recomputable from a clean
clone", and it is the one we make.
````

三处与第一版不同,都是核实过的:`pip install -e .` 不装 pytest(`dev = ["pytest>=8"]`
是 optional extra);`invoiceloop run` 属 research 路径,要 sibling 校准档案,
`invoiceloop demo` 才是「内嵌示例语料 → 完整 run(零 API、零外部数据)」;
`runs/demo` 落在 gitignored 的 symlink 里,换成 `/tmp`。

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
| 8/22 D1 | 0–4 | 证据落盘助手 + 抽样器 + 名单过滤 + 冻结协议 → 后台启动 400 次提取(~1.5h) |
| 8/23 D2 | 5 | 四臂跑完,写资格集结果文档(P1–P5 对照) |
| 8/24 D3 | 6–8 | 溯源导出与对账 + 冻结工件脚本 + 抽行走集 + 冻结行走协议 |
| 8/25 D4 | 9 | 提交 setup → 装配 → 写集快照 → 预生成 20 份建议 → 写集差集 → 冻结工件 → 走完队列 |
| 8/26 D5 | 10 | 行走结果 P1–P5,写结果文档 |
| 8/27 D6 | 11 | lint 回归 + 便宜分 + 诚实重跑自评 |
| 8/28 D7 | 12 | 录制、剪辑、表单、README、披露刷新 |
| 8/29–30 | — | 缓冲;**8/30 前交 ATA** |
| 9/1 | — | **交 Nutrient** |

## 全程纪律

- 提取失败 = blocking 记录,不跳过、不补抽、不缩样本。
- 协议文本冻结后不改;改了 = 臂不干净,照登。
- 预测错了照登,不回改预测。
- **带测试的是会静默出错的东西**,每条测试钉住一个用户可见的失败:抽样器可复算
  (`test_qualify`)、名单缺件阻断(`test_doctouch_arms_doclist`)、冻结清单不被改写
  (`test_freeze_evidence`)、溯源三向对账与 live 核验(`test_suggest_provenance`)、
  行走集与队列同谓词(`test_qual_walk_plan`)、写集看得见账本被动过(`test_writeset`)、
  放行契约不被机器改宽(`test_lint_release_profile`)。
  **没有单测的是编排脚本**(`qual_adk_walk_setup.py`、`qual_walk_analyze.py`)——
  它们只跑一次、失败即刻可见,给它们造 fixture 的成本高于收益。不写"所有新代码带测试"
  这种兑现不了的话。
- 任何对外数字带 `ARCHITECTURE.md` §8 三条限定;不说工件证明不了的话。
- 凭证只在 `.env`(gitignored):不进仓库、不进 run 目录、不进 bundle、不进日志、
  不写进任何文档。
- **冻结要能在 git 里看见。** `runs/` 是 gitignored 的 symlink,任何「冻结先于结果」的
  主张都必须靠 `scripts/freeze_evidence.py` 把副本落进 `docs/evidence/<round>/` 才算数。
- **证据身份不经过浏览器。** 页面只提交裁决与 `suggestion_seen`;工件哈希与模型 id 由
  `append_adjudication` 从冻结表导出,对不上就一行都不写。

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
| 走的时候提交被拒(三向对账不过) | 这是设计意图不是故障:说明冻结表与屏幕不一致。查是哪一边漂了,**不要绕过对账**;必要时按废臂条款声明后重开一个 run |
| P1 < 1.0 | 按阻断处理,`gaps` 明细进结果文档 §0。覆盖率是结构性主张,打折的结构性主张等于没有 |
