#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
PROGRESS="$LOGS/baselines-replace-progress.log"
until [ -f "$LOGS/avds-replace-progress.log" ] && grep -q "REPLACE RUN DONE" "$LOGS/avds-replace-progress.log"; do sleep 60; done
: > "$PROGRESS"
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start $ds" >> "$PROGRESS"
  .venv/Scripts/python.exe -m smart_city_security.integration.avds_baselines --datasets "$ds" \
    --attack-mode replace --seeds $(seq -s ' ' 4 13) --jobs "${JOBS:-4}" \
    --output "results/ml/avds-baselines-replace-$ds.json" > "$LOGS/baselines-replace-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $ds" >> "$PROGRESS"
done
echo "$(date '+%F %H:%M') BASELINES REPLACE DONE" >> "$PROGRESS"
