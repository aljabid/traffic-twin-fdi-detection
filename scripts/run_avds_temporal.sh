#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
PROGRESS="$LOGS/avds-temporal-progress.log"
until [ -f "$LOGS/network-progress.log" ] && grep -q "NETWORK RUN DONE" "$LOGS/network-progress.log"; do sleep 60; done
: > "$PROGRESS"
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start $ds" >> "$PROGRESS"
  .venv/Scripts/python.exe -m smart_city_security.integration.avds_experiment --datasets "$ds" \
    --feature-history 5 --models autoencoder isolation_forest --seeds $(seq -s ' ' 4 13) \
    --attacks congestion_spoof clear_road_spoof drift_congestion replay_stale --jobs "${JOBS:-4}" \
    --output "results/ml/avds4-temporal-$ds.json" > "$LOGS/avds-temporal-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $ds" >> "$PROGRESS"
done
echo "$(date '+%F %H:%M') TEMPORAL RUN DONE" >> "$PROGRESS"
