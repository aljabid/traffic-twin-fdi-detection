from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

NAMES = {0: "genuine", 1: "congestion spoof", 2: "clear-road spoof", 3: "time shift", 4: "identity spoof"}
PERIOD_S = 0.1


def load(paths: list[Path]) -> list[tuple[int, int, float]]:
    rows = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            rows += [(int(r[1]), int(r[2]), float(r[3])) for r in csv.reader(handle) if len(r) == 4]
    return rows


def summarise(rows: list[tuple[int, int, float]]) -> dict[str, object]:
    codes = np.array([r[0] for r in rows])
    alarms = np.array([r[1] for r in rows])
    latency = np.array([r[2] for r in rows])
    out: dict[str, object] = {"messages": len(rows), "host_latency_ms_median": float(np.median(latency)),
                              "host_latency_ms_p95": float(np.quantile(latency, 0.95))}
    benign = alarms[codes == 0]
    if len(benign):
        persist = np.convolve(benign.astype(float), np.ones(5), "valid") >= 3
        out["benign"] = {"messages": len(benign), "false_alarm_rate": float(benign.mean()),
                         "false_alarm_rate_3of5": float(persist.mean()) if len(persist) else None}
    for code in sorted(set(codes.tolist()) - {0}):
        mask = codes == code
        episodes, start = [], None
        for i, on in enumerate(mask.tolist() + [False]):
            if on and start is None:
                start = i
            elif not on and start is not None:
                episodes.append((start, i))
                start = None
        delays = []
        for a, b in episodes:
            hits = np.flatnonzero(alarms[a:b])
            delays.append(hits[0] * PERIOD_S if len(hits) else None)
        found = [d for d in delays if d is not None]
        out[NAMES.get(code, str(code))] = {
            "messages": int(mask.sum()), "per_message_detection": float(alarms[mask].mean()),
            "episodes": len(episodes), "episodes_detected": len(found),
            "median_delay_s": float(np.median(found)) if found else None,
        }
    return out


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or sorted(Path("results/hardware").glob("live_*.csv"))
    print(json.dumps(summarise(load(paths)), indent=2))
