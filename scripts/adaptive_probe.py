"""L1 adaptive 离线实测复算(零 API)。

对 SEALED-1 的 88 份未人工文档:模拟 diagnose_risk → 跳过 agentic,
对照现有双模式 gate 里 cross_mode FAIL 槽的真值对错。

用法:
  INVOICELOOP_CORPUS=runs/sealed1-workspace python3 scripts/adaptive_probe.py

口径:truth / eval_norm 与 safety_metrics 同函数,不许另写规范化。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("INVOICELOOP_CORPUS", "runs/sealed1-workspace")
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from invoiceloop.adaptive import diagnose_risk  # noqa: E402
from invoiceloop.dws import load_response  # noqa: E402
from invoiceloop.eval_norm import eval_normalise as norm  # noqa: E402
from invoiceloop.fields import FIELD_KINDS  # noqa: E402
from invoiceloop.safety_metrics import truth  # noqa: E402


def main() -> None:
    hitl = {p.stem for p in Path("runs/hitl-sealed/input/pdfs").glob("*.pdf")}
    ids = json.loads(Path("docs/sealed1_doc_list.json").read_text())["doc_ids"]
    unseen = [d for d in ids if d not in hitl]
    gate = json.loads(Path("runs/sealed1/gate_report.json").read_text())

    clean = escalated = 0
    dual_calls = 2 * len(unseen)
    adaptive_calls = 0
    lost_cross_mode = 0  # clean 文档上现有 cross_mode=fail 的槽
    lost_with_truth = 0
    lost_understand_wrong = 0

    for doc in unseen:
        u = load_response(doc, "understand")
        udata = u.data if u else None
        reasons = diagnose_risk(udata)
        adaptive_calls += 1  # understand always
        if reasons:
            escalated += 1
            adaptive_calls += 1  # agentic
            continue
        clean += 1
        evals = gate.get("evaluations", {}).get(doc, {})
        tmap = truth(doc)
        for field, verdicts in evals.items():
            if verdicts.get("cross_mode_agreement") != "fail":
                continue
            lost_cross_mode += 1
            tv = tmap.get(field)
            if tv is None or udata is None:
                continue
            lost_with_truth += 1
            kind = FIELD_KINDS[field]
            got = norm(udata.get(field), kind)
            want = norm(tv, kind)
            if got != want:
                lost_understand_wrong += 1

    # 双模式分歧有真值拆分(全 88 份,不限 clean)
    agree_u = agree_a = both_wrong = 0
    for doc in unseen:
        u = load_response(doc, "understand")
        a = load_response(doc, "agentic")
        if not u or not a:
            continue
        tmap = truth(doc)
        for field, verdicts in gate.get("evaluations", {}).get(doc, {}).items():
            if verdicts.get("cross_mode_agreement") != "fail":
                continue
            tv = tmap.get(field)
            if tv is None:
                continue
            kind = FIELD_KINDS[field]
            want = norm(tv, kind)
            gu = norm(u.data.get(field), kind)
            ga = norm(a.data.get(field), kind)
            u_ok = gu == want
            a_ok = ga == want
            if u_ok and not a_ok:
                agree_u += 1
            elif a_ok and not u_ok:
                agree_a += 1
            elif not u_ok and not a_ok:
                both_wrong += 1

    print(f"未人工文档:{len(unseen)}")
    print(f"diagnose_risk: clean={clean} escalated={escalated}")
    print(f"DWS 调用: dual={dual_calls} adaptive={adaptive_calls} "
          f"saved={dual_calls - adaptive_calls} "
          f"({(dual_calls - adaptive_calls) / dual_calls:.1%})")
    print(f"clean 文档上失去的 cross_mode=fail 槽:{lost_cross_mode}")
    print(f"其中有真值:{lost_with_truth}  understand 错:{lost_understand_wrong}/"
          f"{lost_with_truth}")
    total_split = agree_u + agree_a + both_wrong
    print(f"全量 cross_mode=fail 有真值拆分(n={total_split}): "
          f"understand对={agree_u} agentic对={agree_a} 都错={both_wrong}")


if __name__ == "__main__":
    main()
