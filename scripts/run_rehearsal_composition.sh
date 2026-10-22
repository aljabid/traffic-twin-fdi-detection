#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
P="$LOGS/composition-progress.log"
R="congestion_spoof clear_road_spoof drift_congestion replay_stale"
run() {
  local name="$1" ds="$2"; shift 2
  local out="results/ml/composition-$name-$ds.json"
  [ -s "$out" ] && { echo "$(date '+%F %H:%M') skip $name $ds" >> "$P"; return; }
  echo "$(date '+%F %H:%M') start $name $ds" >> "$P"
  .venv/Scripts/python.exe -m smart_city_security.integration.hybrid_plus --datasets "$ds" \
    --detectors hybrid_plus forest_plus --train-families "$@" \
    --jobs "${JOBS:-4}" --output "$out" > "$LOGS/composition-$name-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $name $ds" >> "$P"
}
for ds in sumo ngsim pneuma; do
  run plus-hard "$ds" $R time_shift backdate position_spoof identity_spoof
  run plus-easy "$ds" $R noise_injection stuck_at
done
echo "$(date '+%F %H:%M') COMPOSITION DONE" >> "$P"
