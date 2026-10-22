#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
PROGRESS="$LOGS/network-progress.log"
until [ -f "$LOGS/avds-robust-progress.log" ] && grep -q "ROBUST RUN DONE" "$LOGS/avds-robust-progress.log"; do sleep 60; done
: > "$PROGRESS"
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start $ds" >> "$PROGRESS"
  .venv/Scripts/python.exe -m smart_city_security.integration.network_impairment --datasets "$ds" \
    --jobs "${JOBS:-4}" --output "results/ml/network-$ds.json" > "$LOGS/network-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $ds" >> "$PROGRESS"
done
echo "$(date '+%F %H:%M') NETWORK RUN DONE" >> "$PROGRESS"
