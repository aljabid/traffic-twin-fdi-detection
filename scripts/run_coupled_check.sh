#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
until [ -f "$LOGS/lofo-progress.log" ] && grep -q "LOFO DONE" "$LOGS/lofo-progress.log"; do sleep 60; done
P="$LOGS/coupled-progress.log"
echo "$(date '+%F %H:%M') start coupled pneuma" > "$P"
.venv/Scripts/python.exe -m smart_city_security.integration.hybrid_plus --datasets pneuma \
  --detectors hybrid hybrid_plus forest_plus plausibility_knn \
  --attacks congestion_spoof clear_road_spoof congestion_coupled clear_road_coupled \
  --jobs "${JOBS:-4}" --output results/ml/coupled-check-pneuma.json > "$LOGS/coupled-pneuma.log" 2>&1 \
  || echo "$(date '+%F %H:%M') FAILED coupled" >> "$P"
echo "$(date '+%F %H:%M') COUPLED DONE" >> "$P"
