"""第二梯队鲁棒性测试:现在这套测试抓不到的缺口,各钉一条。

#3 一份文档缺 OCR 不许 crash 全批(宪章四:这份阻断,其余照常)
#4 确定性必须跨进程成立(同进程重跑的热缓存可能掩盖序依赖)
#5 panel 的 crop 链接必须全部可解析;恶意输入必须被转义
#6 多页文档的引用页码不能有 off-by-one(38/160 是多页)
#7 0.8 阈值边界与 §8b 退化 token 是**已声明行为**,钉死防静默漂移
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from invoiceloop import freeze, ocr
from invoiceloop.pipeline import run
from tests.conftest import pin_corpus

REPO = Path(__file__).resolve().parent.parent
from invoiceloop.ocr import corpus_available

REAL_CORPUS = corpus_available()


def _record(doc_id: str, mode: str, data: dict) -> dict:
    return {
        "doc_id": doc_id, "document": f"{doc_id}.pdf", "mode": mode, "http_status": 200,
        "body": {"output": {"data": data, "metadata": {},
                            "pages": [{"page": 1, "width": 1000, "height": 1000}]}},
    }


@pytest.fixture
def two_doc_corpus(tmp_path, monkeypatch):
    """doc-a 有响应有 OCR;doc-ghost 有响应没 OCR。"""
    root = tmp_path / "derisk"
    (root / "raw").mkdir(parents=True)
    (root / "data" / "docile" / "ocr").mkdir(parents=True)
    for doc, data in (("doc-a", {"invoice_number": "INV-42"}),
                      ("doc-ghost", {"invoice_number": "GHOST-9"})):
        for mode in ("understand", "agentic"):
            (root / "raw" / f"{doc}.{mode}.json").write_text(
                json.dumps(_record(doc, mode, data)), encoding="utf-8")
    word = {"value": "INV-42", "confidence": 0.99,
            "geometry": [[0.1, 0.1], [0.2, 0.13]], "snapped_geometry": [[0.1, 0.1], [0.2, 0.13]]}
    page = {"page_idx": 0, "dimensions": [1000, 800],
            "orientation": {"value": None, "confidence": None},
            "language": {"value": "en", "confidence": None},
            "blocks": [{"geometry": [[0, 0], [1, 1]], "artefacts": [],
                        "lines": [{"geometry": [[0, 0], [1, 1]], "words": [word]}]}]}
    (root / "data" / "docile" / "ocr" / "doc-a.json").write_text(
        json.dumps({"pages": [page]}), encoding="utf-8")
    pin_corpus(monkeypatch, root)
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()
    yield root
    ocr.load_ocr.cache_clear()
    ocr.doc_tokens.cache_clear()


class TestMissingOcrBlocksOneDocNotTheBatch:
    def test_run_completes_and_marks_the_gap(self, two_doc_corpus):
        out = two_doc_corpus.parent / "run"
        paths = run(["doc-a", "doc-ghost"], out, include_vision=False)

        events = [json.loads(x) for x in paths["events"].read_text().splitlines()]
        blocked = [e for e in events if e["event"] == "doc_blocked"]
        assert [e["doc_id"] for e in blocked] == ["doc-ghost"]
        assert blocked[0]["blocking"] is True

        matrix = json.loads(paths["matrix"].read_text())
        ghost_rows = [r for r in matrix["rows"] if r["doc_id"] == "doc-ghost"]
        assert ghost_rows, "被阻断的文档也得在矩阵里有行 —— 缺口不能被隐藏"
        assert all(r["support_strength"] == "unsupported" for r in ghost_rows)
        assert all("ocr_unavailable_pipeline_blocked" in r["limitations"] for r in ghost_rows)
        assert all(r["requires_adjudication"] for r in ghost_rows)

        ledger = json.loads(paths["ledger"].read_text())
        docs_in_ledger = {c["doc_id"] for c in ledger["claims"]}
        assert "doc-a" in docs_in_ledger and "doc-ghost" not in docs_in_ledger


@pytest.mark.skipif(not REAL_CORPUS, reason="存盘证据不在")
class TestCrossProcessDeterminism:
    """同进程重跑会带热缓存;两个冷进程产出同字节,才算确定性。"""

    DOCS = ["046e0c4924044de09f6d9e7b", "00134dd365a24343b35b78c6"]
    ARTIFACTS = ["run_manifest.json", "artifact_registry.json", "field_ledger.json",
                 "gate_report.json", "support_matrix.json", "support_panel.html",
                 "event_log.jsonl", "field_drafts.json", "evidence_span_registry.json",
                 "field_claim_graph.json"]

    def test_two_cold_processes_produce_identical_bytes(self, tmp_path):
        for name in ("pa", "pb"):
            subprocess.run(
                [sys.executable, "-m", "invoiceloop", "run",
                 "--doc-ids", *self.DOCS, "--out", str(tmp_path / name)],
                cwd=REPO, check=True, capture_output=True,
            )
        for artifact in self.ARTIFACTS:
            a = (tmp_path / "pa" / artifact).read_bytes()
            b = (tmp_path / "pb" / artifact).read_bytes()
            assert a == b, f"{artifact} 跨进程不确定"


@pytest.mark.skipif(not REAL_CORPUS, reason="存盘证据不在")
class TestPanelLinks:
    def test_every_crop_link_in_panel_resolves(self, tmp_path):
        out = tmp_path / "run"
        run(["00136a27c7774c1e8dc6b2f2"], out, render_crops=True, include_vision=False)
        panel = (out / "support_panel.html").read_text(encoding="utf-8")
        links = set(re.findall(r'(?:src|href)="(crops/[^"]+)"', panel))
        assert links, "这份文档有引用框,panel 应当嵌了裁剪图"
        for link in links:
            assert (out / link).exists(), f"死链:{link}"


class TestPanelEscapesHostileInput:
    def test_script_in_value_is_escaped(self, tmp_path):
        from invoiceloop.panel import render_panel

        evil = "<script>alert(1)</script>"
        support = {
            "summary": {"docs": 1, "slots": 1,
                        "by_strength": {"unsupported": 1, "single_source": 0, "corroborated": 0},
                        "requires_adjudication": 1, "applicability_disputed": 0,
                        "blocking_findings": 0, "claims_admitted": 0, "drafts_rejected": 1,
                        "rejected_by_drafter": {"dws_understand": 1}},
            "rows": [{
                "doc_id": "doc-a", "field": "seller_name", "value": evil, "claim_id": None,
                "support_strength": "unsupported", "source_tiers": [],
                "applicability": "matches", "limitations": [evil],
                "requires_adjudication": True, "gate_verdicts": {}, "span_ids": [],
                "rejections": [{"reason": "binding", "doc_id": "doc-a", "field": "seller_name",
                                "value": evil, "drafted_by": "dws_understand", "coverage": 0.0}],
                "blocking_findings": [],
            }],
        }
        spans = [{"span_id": "ES-0001", "doc_id": "doc-a", "field": "seller_name",
                  "page": 1, "bbox_rel": [0, 0, 0.1, 0.1], "ocr_text": evil,
                  "printed_label": evil, "source": "dws_source_bbox",
                  "crop": None, "crop_sha256": None}]
        support["rows"][0]["cited_span_ids"] = ["ES-0001"]
        render_panel(tmp_path, support=support,
                     gate_report={"findings": [], "evaluations": {}},
                     spans=spans, ledger={"claims": [], "sha256": "x"}, artifact_digest="y")
        panel = (tmp_path / "support_panel.html").read_text(encoding="utf-8")
        assert "<script>alert" not in panel
        # 值、限制、拒绝、片段 OCR、片段标签 —— 五处全部要转义
        assert panel.count("&lt;script&gt;") >= 5


class TestPanelShowsReviewEvidence:
    """人类验收 T1 实测抓出的缺陷:被拒的行没有图,复核者看不懂。"""

    def _render(self, tmp_path, row, spans, make_pages=False):
        from invoiceloop.panel import render_panel

        support = {
            "summary": {"docs": 1, "slots": 1,
                        "by_strength": {"unsupported": 1, "single_source": 0, "corroborated": 0},
                        "requires_adjudication": 1, "applicability_disputed": 0,
                        "blocking_findings": 0, "claims_admitted": 0, "drafts_rejected": 1,
                        "rejected_by_drafter": {}},
            "rows": [row],
        }
        if make_pages:
            (tmp_path / "pages").mkdir(parents=True)
            (tmp_path / "pages" / f"{row['doc_id']}-1.png").write_bytes(b"\x89PNG")
        render_panel(tmp_path, support=support,
                     gate_report={"findings": [], "evaluations": {}},
                     spans=spans, ledger={"claims": [], "sha256": "x"}, artifact_digest="y")
        return (tmp_path / "support_panel.html").read_text(encoding="utf-8")

    REJECTED_ROW = {
        "doc_id": "doc-a", "field": "amount_due", "value": "21,900.66", "claim_id": None,
        "support_strength": "unsupported", "source_tiers": [],
        "applicability": "matches", "limitations": ["draft_rejected_at_freeze"],
        "requires_adjudication": True, "gate_verdicts": {}, "span_ids": [],
        "cited_span_ids": ["ES-0003"],
        "rejections": [{"reason": "binding", "doc_id": "doc-a", "field": "amount_due",
                        "value": "21,900.66", "drafted_by": "dws_understand", "coverage": 0.33}],
        "blocking_findings": [],
    }
    CITED_SPAN = [{"span_id": "ES-0003", "doc_id": "doc-a", "field": "amount_due",
                   "page": 1, "bbox_rel": [0, 0, 0.1, 0.1], "ocr_text": "21,000.00",
                   "printed_label": "TOTAL AMOUNT DUE", "source": "dws_source_bbox",
                   "crop": "ES-0003-1.png", "crop_sha256": "x"}]

    def test_rejected_row_shows_where_dws_pointed(self, tmp_path):
        (tmp_path / "crops").mkdir()
        (tmp_path / "crops" / "ES-0003-1.png").write_bytes(b"\x89PNG")
        panel = self._render(tmp_path, self.REJECTED_ROW, self.CITED_SPAN)
        assert "DWS 指向这里(复核用)" in panel
        assert "crops/ES-0003-1.png" in panel
        assert "21,000.00" in panel  # 引用区的独立 OCR,复核者要对照的就是它

    def test_row_without_any_citation_gets_full_page_link(self, tmp_path):
        row = {**self.REJECTED_ROW, "cited_span_ids": []}
        panel = self._render(tmp_path, row, [], make_pages=True)
        assert "看整页" in panel and f"pages/{row['doc_id']}-1.png" in panel


@pytest.mark.skipif(not REAL_CORPUS, reason="存盘证据不在")
class TestMultiPagePath:
    """00136a27 是两页文档,invoice_number 引用在第 2 页(pageIndex 1)。"""

    DOC = "00136a27c7774c1e8dc6b2f2"

    def test_span_page_and_region_words_come_from_page_two(self):
        from invoiceloop import dws, evidence

        u = dws.load_response(self.DOC, "understand")
        assert u is not None and len(u.pages) == 2
        spans = evidence.SpanBuilder(self.DOC, u).build()
        inv = next(s for s in spans if s["field"] == "invoice_number")
        assert inv["page"] == 2, "pageIndex(0 基)→ page(1 基)的换算错了"
        assert "280" in inv["ocr_text"] or inv["ocr_text"], "第 2 页的取词不应为空"
        # 同一文档第 1 页的词不得混入第 2 页的片段
        page1_words = {w for idx, w, _ in ocr.iter_words(self.DOC) if idx == 0}
        span_words = set(inv["ocr_text"].split())
        if "INVOICE" in page1_words:
            assert "INVOICE" not in span_words or "INVOICE" in {
                w for idx, w, _ in ocr.iter_words(self.DOC) if idx == 1}


class TestThresholdBoundary:
    """0.8 是预注册阈值;边界两侧的行为钉死,谁改阈值谁改测试。"""

    def test_four_of_five_admits_three_of_five_rejects(self, monkeypatch):
        tokens = frozenset({"aa", "bb", "cc", "dd", "zz"})
        monkeypatch.setattr(freeze, "doc_tokens", lambda doc_id: tokens)
        assert freeze.binds_to_document("any", "aa bb cc dd ee") is True   # 4/5 = 0.80,在界上
        assert freeze.binds_to_document("any", "aa bb cc ee ff") is False  # 3/5 = 0.60


class TestDegenerateTokensAreDocumentedBehavior:
    """§8b:$0.00 这类值切成 ['0','00'],几乎匹配任何文档。

    这不是 bug 是已声明的边界(改它的净收益实测为负)—— 但必须有测试钉着,
    免得语料一换它悄悄放大而没人发现。
    """

    def test_zero_amount_binds_even_where_never_printed(self, monkeypatch):
        tokens = frozenset({"invoice", "total", "100", "0", "00"})
        monkeypatch.setattr(freeze, "doc_tokens", lambda doc_id: tokens)
        assert freeze.binds_to_document("any", "$0.00") is True

    def test_strict_tokenizer_alternative_is_not_secretly_adopted(self):
        # 如果有人"修好"了分词(金额整体保留),这条会先红 —— 改判据必须先改测试
        assert ocr.normalise_tokens("$8,500.00") == ["8", "500", "00"]
