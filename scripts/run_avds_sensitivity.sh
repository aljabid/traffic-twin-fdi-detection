#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
PROGRESS="$LOGS/avds-sensitivity-progress.log"
until [ -f "$LOGS/avds-poisoning-progress.log" ] && grep -q "POISONING RUN DONE" "$LOGS/avds-poisoning-progress.log"; do sleep 60; done
: > "$PROGRESS"
declare -A VARIANTS=(
  [val25]="--inner-fraction 0.35"   [val10]="--inner-fraction 0.50"
  [str03]="--strength 0.3"          [str09]="--strength 0.9"
  [fpr01]="--target-fpr 0.01"       [fpr10]="--target-fpr 0.10"
  [ratio05]="--attack-ratio 0.05"   [ratio30]="--attack-ratio 0.30"
)
for name in val25 val10 str03 str09 fpr01 fpr10 ratio05 ratio30; do
  for ds in sumo ngsim pneuma; do
    echo "$(date '+%F %H:%M') start $name $ds" >> "$PROGRESS"
    .venv/Scripts/python.exe -m smart_city_security.integration.avds_experiment --datasets "$ds" \
      ${VARIANTS[$name]} --seeds 4 5 6 7 8 \
      --attacks congestion_spoof clear_road_spoof drift_congestion replay_stale --jobs "${JOBS:-4}" \
      --output "results/ml/avds4-sens-$name-$ds.json" > "$LOGS/avds-sens-$name-$ds.log" 2>&1 \
      || echo "$(date '+%F %H:%M') FAILED $name $ds" >> "$PROGRESS"
  done
done
echo "$(date '+%F %H:%M') SENSITIVITY RUN DONE" >> "$PROGRESS"
