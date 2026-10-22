#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

JOBS="${JOBS:-4}"
PNEUMA_DIR="${SCS_DATA_DIR:-./datasets}/pneuma/extracted/pNEUMA_dataset"
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
EXE=.venv/Scripts/smart-city-avds-experiment.exe
SEEDS30=$(seq -s ' ' 4 33)
SEEDS10=$(seq -s ' ' 1 10)
mkdir -p "$LOGS" results/ml

for ds in sumo ngsim pneuma; do
  echo "$(date +%F\ %H:%M) start $ds"
  "$EXE" --datasets "$ds" --seeds $SEEDS30 --jobs "$JOBS" \
    --output "results/ml/avds-$ds-30seed.json" > "$LOGS/avds-$ds.log" 2>&1
done

SESSIONS=(
  20181024_d1_0830_0900 20181029_d2_0900_0930 20181030_d3_0930_1000
  20181101_d4_1000_1030 20181024_d5_1030_1100 20181029_d6_0830_0900
  20181030_d7_0900_0930 20181101_d8_0930_1000 20181024_d9_1000_1030
  20181029_d10_1000_1030
)
for s in "${SESSIONS[@]}"; do
  echo "$(date +%F\ %H:%M) start pneuma:$s"
  "$EXE" --datasets "pneuma=$PNEUMA_DIR/$s.csv" --seeds $SEEDS10 --jobs "$JOBS" \
    --output "results/ml/avds-pneuma-$s.json" > "$LOGS/avds-pneuma-$s.log" 2>&1
done
echo "$(date +%F\ %H:%M) AVDS FULL RUN DONE"
