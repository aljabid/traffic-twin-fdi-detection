#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
REPORT="$LOGS/post-run-report.txt"
export OQS_INSTALL_PATH="${OQS_INSTALL_PATH:?set OQS_INSTALL_PATH to your liboqs install}"
PY=.venv/Scripts/python.exe
TMP="${TMPDIR:-$LOGS}/pytest-post-run"

until grep -q "AVDS FULL RUN DONE" "$LOGS/avds-full-progress.log" 2>/dev/null \
   || grep -qE "Traceback|MemoryError" "$LOGS"/avds-*.log 2>/dev/null; do
  sleep 120
done

{
  echo "=== post-run report, started $(date '+%F %H:%M')"
  echo "--- run progress log"; cat "$LOGS/avds-full-progress.log"
  echo "--- errors in run logs (empty = none)"; grep -lE "Traceback|MemoryError" "$LOGS"/avds-*.log
  echo; echo "--- ten further pNEUMA sessions"
  $PY scripts/avds_summary.py results/ml/avds-pneuma-2018*.json 2>&1 | grep -v faulthandler
  echo; echo "--- reinstall package (registers smart-city-link-budget)"
  $PY -m pip install -q -e . --no-deps 2>&1 | tail -3; ls .venv/Scripts/smart-city-link-budget.exe
  echo; echo "--- Figure 4"
  $PY scripts/make_avds_figure.py 2>&1 | tail -3
  echo; echo "--- full test suite"
  $PY -m pytest -q -p no:cacheprovider -W ignore --basetemp="$TMP" 2>&1 | tail -5
  echo; echo "--- ruff"; .venv/Scripts/ruff.exe check src tests scripts 2>&1 | tail -3
  echo; echo "--- mypy"; .venv/Scripts/mypy.exe src 2>&1 | tail -2
  echo "=== finished $(date '+%F %H:%M')"
} > "$REPORT" 2>&1
echo "POST-RUN DONE $REPORT"
