#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
P="$LOGS/lofo-progress.log"
: > "$P"
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start $ds" >> "$P"
  .venv/Scripts/python.exe -m smart_city_security.integration.leave_one_out --datasets "$ds" \
    --jobs "${JOBS:-4}" --output "results/ml/leave-one-out-$ds.json" > "$LOGS/lofo-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $ds" >> "$P"
done
echo "$(date '+%F %H:%M') LOFO DONE" >> "$P"
