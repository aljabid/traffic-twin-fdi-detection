#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
P="$LOGS/grid-progress.log"; : > "$P"
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start supervised $ds" >> "$P"
  .venv/Scripts/python.exe -m smart_city_security.integration.supervised_baseline --datasets "$ds" \
    --attacker-search grid --seeds $(seq -s ' ' 4 13) --jobs "${JOBS:-4}" \
    --output "results/ml/supervised-grid-$ds.json" > "$LOGS/supervised-grid-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED supervised $ds" >> "$P"
done
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start avds $ds" >> "$P"
  .venv/Scripts/python.exe -m smart_city_security.integration.avds_experiment --datasets "$ds" \
    --attack-mode replace --attacker-search grid --seeds 4 5 6 7 8 \
    --attacks congestion_spoof clear_road_spoof drift_congestion replay_stale --jobs "${JOBS:-4}" \
    --output "results/ml/avds4-replace-grid-$ds.json" > "$LOGS/avds-grid-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED avds $ds" >> "$P"
done
echo "$(date '+%F %H:%M') GRID RUN DONE" >> "$P"
