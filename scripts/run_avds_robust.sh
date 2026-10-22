#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
PROGRESS="$LOGS/avds-robust-progress.log"
until [ -f "$LOGS/avds-strong-progress.log" ] && grep -q "STRONG RUN DONE" "$LOGS/avds-strong-progress.log"; do sleep 60; done
: > "$PROGRESS"
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start $ds" >> "$PROGRESS"
  .venv/Scripts/python.exe -m smart_city_security.integration.avds_experiment --datasets "$ds" \
    --divergence-transform log1p --seeds $(seq -s ' ' 4 13) \
    --attacks congestion_spoof clear_road_spoof drift_congestion replay_stale --jobs "${JOBS:-4}" \
    --output "results/ml/avds4-log1p-$ds.json" > "$LOGS/avds-robust-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $ds" >> "$PROGRESS"
done
echo "$(date '+%F %H:%M') ROBUST RUN DONE" >> "$PROGRESS"
