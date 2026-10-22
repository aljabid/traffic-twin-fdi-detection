#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS="${SCS_DATA_DIR:-./datasets}/logs"
until [ -f "$LOGS/coupled-progress.log" ] && grep -q "COUPLED DONE" "$LOGS/coupled-progress.log"; do sleep 60; done
P="$LOGS/plus-followups-progress.log"
run() {
  local name="$1" module="$2" ds="$3"; shift 3
  [ -s "results/ml/plus-$name-$ds.json" ] && { echo "$(date '+%F %H:%M') skip $name $ds (done)" >> "$P"; return; }
  echo "$(date '+%F %H:%M') start $name $ds" >> "$P"
  .venv/Scripts/python.exe -m "smart_city_security.integration.$module" --datasets "$ds" "$@" \
    --jobs "${JOBS:-4}" --output "results/ml/plus-$name-$ds.json" > "$LOGS/plus-$name-$ds.log" 2>&1 \
    || echo "$(date '+%F %H:%M') FAILED $name $ds" >> "$P"
}
for ds in sumo ngsim pneuma; do
  run network hybrid_robustness "$ds" --mode network
  run poisoning hybrid_robustness "$ds" --mode poisoning
  run episodes episode_detection "$ds"
  run tradeoff alarm_tradeoff "$ds"
done
echo "$(date '+%F %H:%M') PLUS FOLLOWUPS DONE" >> "$P"
