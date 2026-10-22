#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
P="$LOGS/novel-progress.log"; : > "$P"
NOVEL="stuck_at time_shift position_spoof"
for search in gradient grid; do
  for ds in sumo ngsim pneuma; do
    echo "$(date '+%F %H:%M') start unsupervised $search $ds" >> "$P"
    .venv/Scripts/python.exe -m smart_city_security.integration.avds_experiment --datasets "$ds" \
      --attack-mode replace --attacker-search "$search" --seeds 4 5 6 7 8 --attacks $NOVEL \
      --jobs "${JOBS:-4}" --output "results/ml/novel-unsup-$search-$ds.json" \
      > "$LOGS/novel-unsup-$search-$ds.log" 2>&1 || echo "$(date '+%F %H:%M') FAILED $search $ds" >> "$P"
  done
done
for ds in sumo ngsim pneuma; do
  echo "$(date '+%F %H:%M') start forest $ds" >> "$P"
  .venv/Scripts/python.exe -m smart_city_security.integration.avds_full --datasets "$ds" --seeds 4 5 6 7 8 \
    --novel-attacks $NOVEL --skip-unseen --jobs "${JOBS:-4}" --output "results/ml/novel-rf-$ds.json" \
    > "$LOGS/novel-rf-$ds.log" 2>&1 || echo "$(date '+%F %H:%M') FAILED forest $ds" >> "$P"
done
echo "$(date '+%F %H:%M') NOVEL RUN DONE" >> "$P"
