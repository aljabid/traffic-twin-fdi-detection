#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

JOBS="${JOBS:-4}"
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
PY=.venv/Scripts/python.exe
ATTACKS="congestion_spoof clear_road_spoof drift_congestion replay_stale"
SEEDS=$(seq -s ' ' 4 13)
PROGRESS="$LOGS/avds4-progress.log"
mkdir -p "$LOGS" results/ml
: > "$PROGRESS"

for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start $ds" >> "$PROGRESS"
  $PY -m smart_city_security.integration.avds_experiment --datasets "$ds" --seeds $SEEDS \
    --attacks $ATTACKS --jobs "$JOBS" --output "results/ml/avds4-$ds.json" > "$LOGS/avds4-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $ds" >> "$PROGRESS"
done
echo "$(date '+%F %H:%M') AVDS4 RUN DONE" >> "$PROGRESS"

{
  echo "=== AVDS4 report $(date '+%F %H:%M')"
  cat "$PROGRESS"
  echo "--- errors (empty = none)"; grep -lE "Traceback|MemoryError" "$LOGS"/avds4-*.log
  $PY scripts/avds_summary.py results/ml/avds4-sumo.json results/ml/avds4-ngsim.json results/ml/avds4-pneuma.json \
    --exp5 sumo=results/ml/real-data-sumo-30seed.json ngsim=results/ml/real-data-ngsim-30seed.json \
           pneuma=results/ml/real-data-pneuma-30seed.json 2>&1 | grep -v faulthandler
} > "$LOGS/avds4-report.txt" 2>&1
echo "AVDS4 REPORT WRITTEN"
