#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
until [ -f "$LOGS/coupled-progress.log" ] && grep -q "COUPLED DONE" "$LOGS/coupled-progress.log"; do sleep 60; done
P="$LOGS/loco-progress.log"
for ds in sumo ngsim pneuma; do
  [ -s "results/ml/leave-category-out-$ds.json" ] && { echo "$(date '+%F %H:%M') skip $ds (done)" >> "$P"; continue; }
  echo "$(date '+%F %H:%M') start $ds" >> "$P"
  .venv/Scripts/python.exe -m smart_city_security.integration.leave_one_out --by-category --datasets "$ds" \
    --jobs "${JOBS:-4}" --output "results/ml/leave-category-out-$ds.json" > "$LOGS/loco-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $ds" >> "$P"
done
echo "$(date '+%F %H:%M') LOCO DONE" >> "$P"
bash scripts/run_hybrid_plus_followups.sh
