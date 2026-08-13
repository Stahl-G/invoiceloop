"""doctor:产品路径硬依赖缺失必须非零退出;研究数据缺失只报告不阻断。"""

from __future__ import annotations

import json
import shutil

from invoiceloop.doctor import cmd_doctor


def test_report_shape_and_research_is_informational(capsys):
    rc = cmd_doctor()
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    by_name = {c["check"]: c for c in report["checks"]}
    research = by_name["research:dws-derisk 存盘证据"]
    assert research["required"] is False, "研究数据永远不许阻断产品路径"
    adk = by_name["optional:google-adk"]
    assert adk["required"] is False, "顾问层 extra 不许阻断产品路径"
    assert rc == 0


def test_missing_poppler_fails_product_path(monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda tool: None)
    rc = cmd_doctor()
    report = json.loads(capsys.readouterr().out)
    assert rc == 1 and report["ok"] is False
    poppler = [c for c in report["checks"] if c["check"].startswith("poppler:")]
    assert all(c["required"] and not c["ok"] for c in poppler)
