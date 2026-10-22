from __future__ import annotations

import argparse
import json
from collections import deque
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.integration.avds_experiment import _parse_dataset, _split
from smart_city_security.integration.hybrid_robustness import build
from smart_city_security.iot_sim.adversary import ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import AnomalyDetector, FeatureBuilder
from smart_city_security.schemas import Telemetry

WINDOW_S = 10.0
ATTACKS_TESTED = ("congestion_spoof", "replay_stale", "position_spoof")


def _persistent(messages: Sequence[Telemetry], flags: Sequence[bool], k: int = 2, n: int = 3) -> list[bool]:
    recent: dict[str, deque[bool]] = {}
    out = []
    for m, f in zip(messages, flags, strict=True):
        window = recent.setdefault(m.device_id, deque(maxlen=n))
        window.append(f)
        out.append(sum(window) >= k)
    return out


def _alarms(detector: AnomalyDetector, divergence: bool, train: Sequence[Telemetry],
            messages: Sequence[Telemetry]) -> list[bool]:
    twin = TrafficDigitalTwin(8)
    for m in train:
        twin.observe(m)
    builder = FeatureBuilder(divergence)
    matrix = np.vstack([builder.build(m, twin.observe(m)).values for m in messages])
    flags, _ = detector.predict(matrix)
    return [bool(f) for f in flags]


def episode_metrics(messages: Sequence[Telemetry], flags: Sequence[bool], attacked: set[str],
                    episodes: Sequence[tuple[str, float, float]]) -> dict[str, float]:
    first_alarm: dict[int, float] = {}
    for m, f in zip(messages, flags, strict=True):
        if not f or m.message_id not in attacked:
            continue
        for i, (device, start, end) in enumerate(episodes):
            if m.device_id == device and start <= m.timestamp <= end and i not in first_alarm:
                first_alarm[i] = m.timestamp - start
    windows: dict[tuple[str, int], list[bool]] = {}
    for m, f in zip(messages, flags, strict=True):
        cell = windows.setdefault((m.device_id, int(m.timestamp // WINDOW_S)), [False, False])
        cell[0] |= m.message_id in attacked
        cell[1] |= f
    tp = sum(1 for pos, alarm in windows.values() if pos and alarm)
    fp = sum(1 for pos, alarm in windows.values() if not pos and alarm)
    fn = sum(1 for pos, alarm in windows.values() if pos and not alarm)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "episode_detection_rate": len(first_alarm) / len(episodes) if episodes else 0.0,
        "median_delay_s": median(first_alarm.values()) if first_alarm else float("nan"),
        "window_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def false_alarms_per_hour(messages: Sequence[Telemetry], flags: Sequence[bool]) -> float:
    last: dict[str, float] = {}
    events = 0
    for m, f in zip(messages, flags, strict=True):
        if f:
            if m.device_id not in last or m.timestamp - last[m.device_id] > WINDOW_S:
                events += 1
            last[m.device_id] = m.timestamp
    hours = (max(m.timestamp for m in messages) - min(m.timestamp for m in messages)) / 3600.0
    return events / hours if hours > 0 else float("nan")


def run_unit(stream: Sequence[Telemetry], *, seed: int, strength: float = 0.6) -> dict[str, Any]:
    inner, _, train, test = _split(stream, 0.45, 0.6)
    detectors = build(inner, seed, strength)
    out: dict[str, Any] = {"seed": seed, "detectors": {}}
    clean = sorted(test, key=lambda m: (m.timestamp, m.message_id))
    for name, (detector, divergence) in detectors.items():
        raw = _alarms(detector, divergence, train, clean)
        row: dict[str, Any] = {
            "false_alarms_per_hour": {"raw": false_alarms_per_hour(clean, raw),
                                      "persist_2of3": false_alarms_per_hour(clean, _persistent(clean, raw))},
        }
        for attack in ATTACKS_TESTED:
            for adaptive in (False, True):
                twin = TrafficDigitalTwin(8)
                for m in train:
                    twin.observe(m)
                campaign = AdversarialCampaign(seed, search="grid").run(
                    list(test), attack=ATTACKS[attack], strength=strength, adaptive=adaptive,
                    detector=detector if adaptive else None,
                    feature_builder=FeatureBuilder(divergence) if adaptive else None,
                    predict_twin_state=twin.predict if adaptive else None,
                    mode="replace", schedule="episodes",
                )
                attacked = {mid for mid, g in campaign.labels.items() if g.label == "attack"}
                flags = _alarms(detector, divergence, train, campaign.messages)
                key = f"{attack}/{'adaptive' if adaptive else 'static'}"
                row[key] = {
                    "raw": episode_metrics(campaign.messages, flags, attacked, campaign.episodes),
                    "persist_2of3": episode_metrics(campaign.messages, _persistent(campaign.messages, flags),
                                                    attacked, campaign.episodes),
                }
        out["detectors"][name] = row
    return out


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[4, 5, 6, 7, 8])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="results/ml/episodes.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": "episode_detection", "generated_at": datetime.now(UTC).isoformat(),
                              "seeds": args.seeds, "window_s": WINDOW_S, "attacks": list(ATTACKS_TESTED),
                              "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"seed": s} for s in args.seeds]
        if args.jobs > 1:
            with ProcessPoolExecutor(max_workers=args.jobs) as pool:
                units = list(pool.map(_task, [(dataset.telemetry, k) for k in kwargs]))
        else:
            units = [run_unit(dataset.telemetry, **k) for k in kwargs]
        report["datasets"][dataset.name] = {"units": units}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
