#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
PROGRESS="$LOGS/avds-poisoning-progress.log"
until [ -f "$LOGS/avds-kalman-progress.log" ] && grep -q "KALMAN RUN DONE" "$LOGS/avds-kalman-progress.log"; do sleep 60; done
: > "$PROGRESS"
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start $ds" >> "$PROGRESS"
  .venv/Scripts/python.exe -m smart_city_security.integration.avds_poisoning --datasets "$ds" \
    --seeds $(seq -s ' ' 4 13) --rates 0.10 --jobs "${JOBS:-4}" \
    --output "results/ml/avds-poisoning-$ds.json" > "$LOGS/avds-poisoning-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $ds" >> "$PROGRESS"
done
echo "$(date '+%F %H:%M') POISONING RUN DONE" >> "$PROGRESS"
