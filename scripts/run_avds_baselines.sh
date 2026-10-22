#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
PROGRESS="$LOGS/avds-baselines-progress.log"
mkdir -p "$LOGS" results/ml
: > "$PROGRESS"
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start $ds" >> "$PROGRESS"
  .venv/Scripts/python.exe -m smart_city_security.integration.avds_baselines --datasets "$ds" \
    --seeds $(seq -s ' ' 4 13) --jobs "${JOBS:-4}" --output "results/ml/avds-baselines-$ds.json" \
    > "$LOGS/avds-baselines-$ds.log" 2>&1 || echo "$(date '+%F %H:%M') FAILED $ds" >> "$PROGRESS"
done
echo "$(date '+%F %H:%M') BASELINES RUN DONE" >> "$PROGRESS"
