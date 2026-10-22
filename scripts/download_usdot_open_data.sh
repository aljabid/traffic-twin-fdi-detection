#!/usr/bin/env bash
set -uo pipefail
ROOT="${SCS_DATA_DIR:-./datasets}/usdot"
LOG="$ROOT/download.log"
mkdir -p "$ROOT"
PAGE=1000000
fetch() {
  local name="$1" id="$2" max="$3" offset=0 page=0
  mkdir -p "$ROOT/$name"
  while [ "$offset" -lt "$max" ]; do
    local out="$ROOT/$name/part-$(printf '%03d' "$page").csv"
    if [ ! -s "$out" ]; then
      curl -s -A "Mozilla/5.0" --retry 3 --max-time 3600 -o "$out.tmp" \
        "https://data.transportation.gov/resource/$id.csv?\$order=:id&\$limit=$PAGE&\$offset=$offset" \
        && mv "$out.tmp" "$out" || { echo "$(date '+%F %H:%M') FAILED $name page $page" >> "$LOG"; return; }
    fi
    local rows=$(( $(wc -l < "$out") - 1 ))
    echo "$(date '+%F %H:%M') $name page $page rows $rows" >> "$LOG"
    [ "$rows" -lt "$PAGE" ] && break
    offset=$((offset + PAGE)); page=$((page + 1))
  done
}
fetch tgsim-foggy-bottom      brzy-6zfh  3000000
fetch tgsim-i395              97n2-kuqi  5000000
fetch tgsim-i90-i94-stationary 9uas-hf8b 5000000
fetch tgsim-i90-i94-moving    6a6e-vfvi  2000000
fetch tgsim-i294-l1           7zjf-a4zf  2000000
fetch tgsim-i294-l2           tpsq-zrwa  1000000
fetch mmitss-trajectories     rh2j-ihhy  1000000
fetch inflo-bsm               wz7m-693m  1000000
fetch mmitss-bsm              5tsh-j288  3000000
fetch udot-panasonic-bsm      ev64-jn8c  5000000
fetch amcd-bsm                eezi-v4pm  3000000
fetch utah-bsm-trajectories   e9cn-jdnu  3000000
fetch utah-spat               j7k2-8r24  3000000
fetch adas-two-vehicle-ohio   vhz2-exyi  3000000
echo "$(date '+%F %H:%M') USDOT DONE" >> "$LOG"
