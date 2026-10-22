#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
P="$LOGS/followups-progress.log"
until [ -f "$LOGS/novel2-progress.log" ] && grep -q "NOVEL2 DONE" "$LOGS/novel2-progress.log"; do sleep 60; done
: > "$P"
for ds in sumo ngsim pneuma; do
  for mode in network poisoning; do
    echo "$(date '+%F %H:%M') start $mode $ds" >> "$P"
    .venv/Scripts/python.exe -m smart_city_security.integration.hybrid_robustness --datasets "$ds" --mode "$mode" \
      --jobs "${JOBS:-4}" --output "results/ml/hybrid-$mode-$ds.json" > "$LOGS/hybrid-$mode-$ds.log" 2>&1 \
      || echo "$(date '+%F %H:%M') FAILED $mode $ds" >> "$P"
  done
  echo "$(date '+%F %H:%M') start episodes $ds" >> "$P"
  .venv/Scripts/python.exe -m smart_city_security.integration.episode_detection --datasets "$ds" \
    --jobs "${JOBS:-4}" --output "results/ml/episodes-$ds.json" > "$LOGS/episodes-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED episodes $ds" >> "$P"
done
echo "$(date '+%F %H:%M') FOLLOWUPS DONE" >> "$P"
