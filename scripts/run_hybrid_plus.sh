#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
P="$LOGS/hybridplus-progress.log"
: > "$P"
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start design $ds" >> "$P"
  .venv/Scripts/python.exe -m smart_city_security.integration.hybrid_plus --datasets "$ds" \
    --seeds 4 5 6 7 8 9 10 11 12 13 --detectors hybrid_plus forest_plus \
    --jobs "${JOBS:-4}" --output "results/ml/hybrid-plus-$ds.json" > "$LOGS/hybridplus-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED design $ds" >> "$P"
done
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start confirm $ds" >> "$P"
  .venv/Scripts/python.exe -m smart_city_security.integration.hybrid_plus --datasets "$ds" \
    --seeds 14 15 16 17 18 19 20 21 22 23 --detectors hybrid hybrid_plus forest_plus plausibility_knn \
    --jobs "${JOBS:-4}" --output "results/ml/hybrid-plus-confirm-$ds.json" > "$LOGS/hybridplus-confirm-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED confirm $ds" >> "$P"
done
echo "$(date '+%F %H:%M') HYBRIDPLUS DONE" >> "$P"
