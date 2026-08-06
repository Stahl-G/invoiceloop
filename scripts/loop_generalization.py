"""docs/LOOP_GENERALIZATION_2026-08-06.md 的复算脚本(零 API)。

用法:INVOICELOOP_CORPUS=runs/sealed1-workspace python3 scripts/loop_generalization.py
"""
import json, os, sys, pathlib
os.environ.setdefault("INVOICELOOP_CORPUS", "runs/sealed1-workspace")
sys.path.insert(0, "scripts")
home = str(pathlib.Path.home())
from heldout_metrics import truth  # noqa: E402
from invoiceloop import harness, routing  # noqa: E402
from invoiceloop.fields import TIER1, FIELD_KINDS  # noqa: E402
from invoiceloop.matrix import derive_document_records, facts_of  # noqa: E402
from invoiceloop.dws import load_response  # noqa: E402
from invoiceloop.eval_norm import eval_normalise as norm  # noqa: E402

hitl = {p.stem for p in pathlib.Path("runs/hitl-sealed/input/pdfs").glob("*.pdf")}
gate = json.load(open("runs/sealed1/gate_report.json"))
claims = json.load(open("runs/sealed1/field_ledger.json"))["claims"]
ids = json.load(open("docs/sealed1_doc_list.json"))["doc_ids"]
unseen = [d for d in ids if d not in hitl]
print(f"未人工文档:{len(unseen)} 份")

h4 = json.load(open("runs/hitl-sealed/harnesses/HAR-0004/routing_policy.json"))
absent_fields = {c["field"] for c in h4.get("absent_expected_cohorts", [])}

facts = {}
for doc in ids:
    u = load_response(doc, "understand")
    blocking = [f for f in gate["findings"]
                if f.get("blocking") and f.get("doc_id") == doc
                and not (f.get("gate_id") == "extraction_present"
                         and f.get("field") in absent_fields)]
    recs = derive_document_records(
        doc,
        doc_claims=[c for c in claims if c["doc_id"] == doc],
        doc_rejections=[],
        gate_evaluations=gate["evaluations"].get(doc, {}),
        doc_blocking_findings=blocking,
        understand_data=u.data if u else None)
    facts[doc] = [facts_of(r) for r in recs]


def apply_policy(policy, doc):
    fs = routing.apply_absent_expected(facts[doc], policy)
    return routing.route_slots(fs, policy,
                               tier_of=lambda f: "TIER1" if f in TIER1 else "TIER2")


h1 = harness._builtin_policy()
h2 = json.load(open("runs/evo-workspace/harnesses/HAR-0002/routing_policy.json"))

for name, pol in (("HAR-0001", h1), ("HAR-0002", h2), ("HAR-0004", h4)):
    n = review = 0
    docs_touched = set()
    silent_absent = absent_hits = silent_wrong = value_hits = 0
    for doc in unseen:
        u = load_response(doc, "understand")
        for r in apply_policy(pol, doc):
            n += 1
            if r["route"] not in ("auto_accept", "auto_absent"):
                review += 1
                docs_touched.add(doc)
                continue
            t = truth(doc).get(r["field"])
            if r["route"] == "auto_absent":
                absent_hits += 1
                if t is not None:
                    silent_absent += 1
            elif t is not None and u is not None:
                got = norm(u.data.get(r["field"]), FIELD_KINDS[r["field"]])
                value_hits += 1
                if got != norm(t, FIELD_KINDS[r["field"]]):
                    silent_wrong += 1
    print(f"{name}: 复核负载 {review/n:.1%}  文档触达 {len(docs_touched)}/{len(unseen)}  "
          f"| auto_absent 静默缺席错 {silent_absent}/{absent_hits}  "
          f"auto_accept 静默错值 {silent_wrong}/{value_hits}")
