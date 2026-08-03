#!/usr/bin/env bash
# 评委视角的安装验证:clean clone → venv → pip install → doctor
#   → 产品路径 E2E(零 API:fixture PDF + 合成存盘响应)
#   → 裁决 → panel 投影 → bundle → verify → 重放 → pytest
#
# 从本地 git clone,只反映**已提交**内容 —— 跑之前先 commit。
# 用法:scripts/fresh_venv_check.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== clean clone + venv + pip install =="
git clone -q "$REPO" "$WORK/clone"
cd "$WORK/clone"
python3 -m venv .venv
VENV=./.venv/bin
"$VENV/pip" install -q ".[dev]"

echo "== doctor =="
"$VENV/python" -m invoiceloop doctor > /dev/null || { echo "doctor 未过"; exit 1; }

echo "== 产品路径 E2E:ingest(本地 OCR)→ 合成存盘响应 → run =="
WS="$WORK/ws"
mkdir -p "$WS/input/pdfs"
cp tests/fixtures/mini-invoice.pdf "$WS/input/pdfs/acme-001.pdf"
"$VENV/python" -m invoiceloop ingest --workspace "$WS" --no-extract > /dev/null
"$VENV/python" - "$WS" <<'PY'
import json, sys
from pathlib import Path

ws = Path(sys.argv[1])
raw = ws / "raw"
raw.mkdir(exist_ok=True)

def record(mode):
    return {"doc_id": "acme-001", "document": "acme-001.pdf", "mode": mode,
            "http_status": 200,
            "body": {"output": {
                "data": {"invoice_number": "INV-42", "total_gross": "100.00"},
                "metadata": {},
                "pages": [{"page": 1, "width": 612, "height": 792}]}}}

for mode in ("understand", "agentic"):
    (raw / f"acme-001.{mode}.json").write_text(json.dumps(record(mode)))
PY
"$VENV/python" -m invoiceloop run --workspace "$WS" --no-vision > /dev/null
RUN="$WS/runs/run-0001"
test -f "$RUN/support_panel.html"
grep -q "输入不在校准集内" "$RUN/support_panel.html"
test -f "$RUN/review_snapshot.json" && test -f "$RUN/input_manifest.json"

echo "== 裁决 → panel 投影(闭环)=="
CLAIM=$("$VENV/python" -c "import json; print(next(c['claim_id'] for c in json.load(open('$RUN/field_ledger.json'))['claims'] if c['field'] == 'total_gross'))")
"$VENV/python" -m invoiceloop adjudicate --run "$RUN" --doc acme-001 --field total_gross \
  --claim-id "$CLAIM" --decision correct --corrected-value "100.00" \
  --rationale "独立 OCR 与纸面一致" --adjudicator fresh-venv \
  --decided-at 2026-08-03T00:00:00 | grep -q '"panel_refreshed": true'
grep -q "人工修正" "$RUN/support_panel.html"
grep -q "100.00" "$RUN/support_panel.html"

echo "== bundle → verify =="
"$VENV/python" -m invoiceloop bundle --run "$RUN" > /dev/null
"$VENV/python" -m invoiceloop verify "$RUN/audit_bundle.zip" | grep -q '"ok": true'

echo "== 同输入重跑 = 重放,不开新代 =="
"$VENV/python" -m invoiceloop run --workspace "$WS" --no-vision | grep -q '"replayed": true'
test ! -d "$WS/runs/run-0002"

echo "== demo 命令:内嵌语料(wheel 里的 samples)跑通全流程 =="
"$VENV/python" -m invoiceloop demo --out "$WORK/demo-ws" > /dev/null
DEMO_RUN="$WORK/demo-ws/runs/run-0001"
test -f "$DEMO_RUN/support_panel.html"
grep -q "输入不在校准集内" "$DEMO_RUN/support_panel.html"
"$VENV/python" - "$DEMO_RUN" <<'PY'
import json, sys
from pathlib import Path

gate = json.loads((Path(sys.argv[1]) / "gate_report.json").read_text())
assert any(f["gate_id"] == "visual_corroboration" for f in gate["findings"]), \
    "demo 的读图门 warning(买卖双方抽反)必须在"
PY

echo "== pytest(研究数据缺失时研究测试自动跳过,产品路径不受影响)=="
INVOICELOOP_DWS_DERISK=/nonexistent "$VENV/python" -m pytest -q

echo "fresh-venv check OK"
