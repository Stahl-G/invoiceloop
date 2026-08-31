#!/usr/bin/env bash
# Live Nutrient DWS path: extraction -> gates -> review -> bundle -> verify.
#
#   DWS_API_KEY=... bash scripts/live_dws_demo.sh [--non-interactive] [workspace]
#
# Unlike `invoiceloop demo`, this script calls DWS live. The API key is read
# only from the environment and is never written to a run artifact.
set -euo pipefail

NON_INTERACTIVE=0
WS="live-demo-ws"
for arg in "$@"; do
  case "$arg" in
    --non-interactive) NON_INTERACTIVE=1 ;;
    -h|--help)
      echo "Usage: DWS_API_KEY=... bash scripts/live_dws_demo.sh [--non-interactive] [workspace]"
      exit 0
      ;;
    -*) echo "Unknown option: $arg" >&2; exit 2 ;;
    *) WS="$arg" ;;
  esac
done
PORT="${PORT:-8765}"

command -v pdftotext >/dev/null || { echo "Missing poppler: brew install poppler (macOS) or apt install poppler-utils (Linux)"; exit 1; }
[ -n "${DWS_API_KEY:-}" ] || { echo "Missing DWS_API_KEY. Export it in the environment; do not write it to a file."; exit 1; }
[ ! -e "$WS" ] || { echo "$WS already exists. Start the live demo with a new workspace."; exit 1; }

echo "1/6 Prepare three vendored DocILE invoices"
mkdir -p "$WS/input/pdfs"
cp invoiceloop/samples/pdfs/*.pdf "$WS/input/pdfs/"
ls "$WS/input/pdfs/"

echo
echo "2/6 Run local independent OCR and live Nutrient DWS extraction"
python3 -m invoiceloop ingest --workspace "$WS"

echo
echo "3/6 Freeze evidence, run six gates, and render the support matrix"
python3 -m invoiceloop run --workspace "$WS" --crops
RUN="$WS/runs/$(python3 -c "import json;print(json.load(open('$WS/runs/current.json'))['run'])")"
echo "   run:   $RUN"
echo "   panel: $RUN/support_panel.html"

if [[ "$NON_INTERACTIVE" -eq 0 ]]; then
  echo
  echo "4/6 Open the Workbench: http://127.0.0.1:$PORT"
  echo "   Record any human decisions in the browser, then return here."
  python3 -m invoiceloop workbench --workspace "$WS" --port "$PORT" &
  WB=$!
  trap 'kill $WB 2>/dev/null || true' EXIT
  read -r -p "   Press Enter to stop the Workbench and continue to bundle + verify ..."
  kill "$WB" 2>/dev/null || true
  wait "$WB" 2>/dev/null || true
  trap - EXIT
else
  echo
  echo "4/6 Skip interactive review (--non-interactive)"
fi

echo
echo "5/6 Build the self-contained audit bundle"
python3 -m invoiceloop bundle --run "$RUN"

echo
echo "6/6 Verify the bundle offline"
python3 -m invoiceloop verify "$RUN/audit_bundle.zip"

echo
if command -v sha256sum >/dev/null; then
  sha256sum "$RUN/audit_bundle.zip"
else
  shasum -a 256 "$RUN/audit_bundle.zip"
fi
echo "Complete. Publish this sha256 beside the bundle as its out-of-band integrity anchor."
