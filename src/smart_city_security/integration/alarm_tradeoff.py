from __future__ import annotations

import argparse
import json
import math
from collections import deque
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

import numpy as np

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.integration.avds_experiment import _parse_dataset, _split
from smart_city_security.integration.avds_full import _inner_attack_features
from smart_city_security.integration.episode_detection import WINDOW_S, episode_metrics
from smart_city_security.integration.hybrid_detector import HybridDetector
from smart_city_security.integration.hybrid_plus import HybridPlus, PlausibleForest
from smart_city_security.integration.real_data_experiment import _train_features, fit_detector
from smart_city_security.integration.supervised_baseline import SupervisedDetector
from smart_city_security.iot_sim.adversary import ATTACKS, REHEARSAL_ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import AnomalyDetector, FeatureBuilder
from smart_city_security.schemas import Telemetry

BUDGETS = (0.05, 0.02, 0.01, 0.005)
RULES = ((1, 1), (2, 3), (3, 5), (4, 5))
ATTACKS_TESTED = ("congestion_spoof", "replay_stale", "position_spoof")


class QuantileThreshold:

    def __init__(self, detector: AnomalyDetector, benign: np.ndarray, target_fpr: float) -> None:
        self.detector, self.name = detector, f"{detector.name}@q"
        self.threshold = float(np.quantile(self._scores(benign), 1.0 - target_fpr))

    def _scores(self, features: np.ndarray) -> np.ndarray:
        _, scores = self.detector.predict(features)
        cleaned: np.ndarray = np.nan_to_num(np.asarray(scores, dtype=float), nan=np.inf, posinf=np.inf)
        return cleaned

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        scores = self._scores(features)
        return scores > self.threshold, scores


def k_of_n(messages: Sequence[Telemetry], flags: Sequence[bool], k: int, n: int) -> list[bool]:
    recent: dict[str, deque[bool]] = {}
    out = []
    for m, f in zip(messages, flags, strict=True):
        window = recent.setdefault(m.device_id, deque(maxlen=n))
        window.append(f)
        out.append(sum(window) >= k)
    return out


def alarms_per_vehicle_hour(messages: Sequence[Telemetry], flags: Sequence[bool]) -> float:
    last: dict[str, float] = {}
    span: dict[str, tuple[float, float]] = {}
    events = 0
    for m, f in zip(messages, flags, strict=True):
        a, b = span.get(m.device_id, (m.timestamp, m.timestamp))
        span[m.device_id] = (min(a, m.timestamp), max(b, m.timestamp))
        if f:
            if m.device_id not in last or m.timestamp - last[m.device_id] > WINDOW_S:
                events += 1
            last[m.device_id] = m.timestamp
    vehicle_hours = sum(b - a for a, b in span.values()) / 3600.0
    return events / vehicle_hours if vehicle_hours > 0 else math.nan


def _flags(detector: AnomalyDetector, divergence: bool, train: Sequence[Telemetry],
           messages: Sequence[Telemetry]) -> list[bool]:
    twin = TrafficDigitalTwin(8)
    for m in train:
        twin.observe(m)
    builder = FeatureBuilder(divergence)
    matrix = np.vstack([builder.build(m, twin.observe(m)).values for m in messages])
    flags, _ = detector.predict(matrix)
    return [bool(f) for f in flags]


def run_unit(stream: Sequence[Telemetry], *, seed: int, strength: float = 0.6) -> dict[str, Any]:
    inner, _, train, test = _split(stream, 0.45, 0.6)
    benign_full = _train_features(inner, twin_window=8, include_divergence=True)
    benign_base = _train_features(inner, twin_window=8, include_divergence=False)
    attack_rows = np.vstack([_inner_attack_features(inner, a, seed, strength) for a in REHEARSAL_ATTACKS])
    lof_raw, _ = fit_detector(inner, model="lof", include_divergence=False, contamination=0.01,
                              seed=seed, calibrate=False)
    clean = sorted(test, key=lambda m: (m.timestamp, m.message_id))
    out: dict[str, Any] = {"seed": seed, "budgets": {}}
    for budget in BUDGETS:
        forest = SupervisedDetector(benign_full, attack_rows, seed, target_fpr=budget)
        detectors: dict[str, tuple[AnomalyDetector, bool]] = {
            "forest": (forest, True),
            "lof": (QuantileThreshold(lof_raw, benign_base, budget), False),
            "hybrid": (HybridDetector(forest, lof_raw, benign_full, benign_base.shape[1], target_fpr=budget), True),
            "hybrid_plus": (HybridPlus(
                PlausibleForest(benign_full, attack_rows, seed, target_fpr=budget),
                lof_raw, benign_full, benign_base.shape[1], target_fpr=budget), True),
        }
        per_detector: dict[str, Any] = {}
        for name, (det, div) in detectors.items():
            clean_flags = _flags(det, div, train, clean)
            attacked_runs = []
            for attack in ATTACKS_TESTED:
                for adaptive in (False, True):
                    twin = TrafficDigitalTwin(8)
                    for m in train:
                        twin.observe(m)
                    campaign = AdversarialCampaign(seed, search="grid").run(
                        list(test), attack=ATTACKS[attack], strength=strength, adaptive=adaptive,
                        detector=det if adaptive else None,
                        feature_builder=FeatureBuilder(div) if adaptive else None,
                        predict_twin_state=twin.predict if adaptive else None,
                        mode="replace", schedule="episodes",
                    )
                    attacked = {mid for mid, g in campaign.labels.items() if g.label == "attack"}
                    attacked_runs.append((campaign, attacked, _flags(det, div, train, campaign.messages)))
            rules: dict[str, Any] = {}
            for k, n in RULES:
                metrics = [episode_metrics(c.messages, k_of_n(c.messages, f, k, n), att, c.episodes)
                           for c, att, f in attacked_runs]
                delays = [m["median_delay_s"] for m in metrics if not math.isnan(m["median_delay_s"])]
                rules[f"{k}of{n}"] = {
                    "detection_rate": fmean(m["episode_detection_rate"] for m in metrics),
                    "median_delay_s": fmean(delays) if delays else math.nan,
                    "false_alarms_per_vehicle_hour": alarms_per_vehicle_hour(clean, k_of_n(clean, clean_flags, k, n)),
                }
            per_detector[name] = rules
        out["budgets"][str(budget)] = per_detector
    return out


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[4, 5, 6, 7, 8])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="results/ml/alarm-tradeoff.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": "alarm_tradeoff", "generated_at": datetime.now(UTC).isoformat(),
                              "seeds": args.seeds, "budgets": list(BUDGETS),
                              "rules": [f"{k}of{n}" for k, n in RULES], "datasets": {}}
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
