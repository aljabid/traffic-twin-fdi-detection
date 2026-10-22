#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
until [ -f "$LOGS/avds-temporal-progress.log" ] && grep -q "TEMPORAL RUN DONE" "$LOGS/avds-temporal-progress.log"; do sleep 60; done
echo "$(date '+%F %H:%M') start" > "$LOGS/importance-progress.log"
.venv/Scripts/python.exe scripts/feature_importance.py > "$LOGS/importance.log" 2>&1 \
  && echo "$(date '+%F %H:%M') IMPORTANCE DONE" >> "$LOGS/importance-progress.log" \
  || echo "$(date '+%F %H:%M') FAILED" >> "$LOGS/importance-progress.log"
