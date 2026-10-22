from __future__ import annotations

import argparse
import json
import random
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from smart_city_security.digital_twin.kalman_twin import make_twin
from smart_city_security.evaluation import calculate_ml_metrics
from smart_city_security.integration.avds_experiment import _parse_dataset
from smart_city_security.integration.real_data_experiment import (
    DEFAULT_MODELS,
    _temporal_split,
    fit_detector,
)
from smart_city_security.iot_sim.adversary import ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import AnomalyDetector, FeatureBuilder
from smart_city_security.schemas import Telemetry

PRESETS: dict[str, tuple[float, float, float]] = {
    "ideal": (0.0, 0.0, 0.0),
    "hrllc": (1e-5, 0.01, 0.0),
    "lossy": (0.01, 0.5, 0.005),
    "degraded": (0.05, 2.0, 0.01),
    "severe": (0.10, 5.0, 0.02),
}


def impair(messages: Sequence[Telemetry], *, loss: float, max_delay: float, duplicate: float,
           seed: int) -> list[Telemetry]:
    if loss == max_delay == duplicate == 0.0:
        return list(messages)
    rng = random.Random(seed)
    arrivals: list[tuple[float, int, Telemetry]] = []
    for i, m in enumerate(messages):
        if rng.random() < loss:
            continue
        arrivals.append((m.timestamp + rng.uniform(0.0, max_delay), i, m))
        if rng.random() < duplicate:
            arrivals.append((m.timestamp + rng.uniform(0.0, max_delay), i,
                             replace(m, message_id=f"{m.message_id}-dup")))
    arrivals.sort(key=lambda t: (t[0], t[1]))
    return [m for _, _, m in arrivals]


def _evaluate(detector: AnomalyDetector, train: Sequence[Telemetry], test: Sequence[Telemetry], *,
              divergence: bool, attack: str | None, adaptive: bool, preset: str, seed: int) -> dict[str, float]:
    twin = make_twin("window", 8)
    for m in train:
        twin.observe(m)
    builder = FeatureBuilder(divergence)
    if attack is None:
        messages, attacked = list(test), set()
    else:
        campaign = AdversarialCampaign(seed).run(
            list(test), attack=ATTACKS[attack], attack_ratio=0.15, strength=0.6, adaptive=adaptive,
            detector=detector if adaptive else None, feature_builder=builder if adaptive else None,
            predict_twin_state=twin.predict if adaptive else None,
        )
        messages = campaign.messages
        attacked = {mid for mid, label in campaign.labels.items() if label.label == "attack"}
    loss, delay, dup = PRESETS[preset]
    arrived = impair(messages, loss=loss, max_delay=delay, duplicate=dup, seed=seed + 20_000)
    truth = [m.message_id.removesuffix("-dup") in attacked for m in arrived]
    matrix = np.vstack([builder.build(m, twin.observe(m)).values for m in arrived])
    flags, scores = detector.predict(matrix)
    metrics = calculate_ml_metrics(truth, [bool(f) for f in flags],
                                   [float(s) if np.isfinite(s) else 1e6 for s in scores])
    return {"f1": metrics.f1, "false_positive_rate": metrics.false_positive_rate}


def run_unit(stream: Sequence[Telemetry], *, model: str, seed: int, attacks: Sequence[str],
             presets: Sequence[str]) -> dict[str, Any]:
    train, test = _temporal_split(stream, 0.6)
    out: dict[str, Any] = {"model": model, "seed": seed, "results": {}}
    for div in (False, True):
        detector, _ = fit_detector(train, model=model, include_divergence=div, contamination=0.05,
                                   seed=seed, calibrate=True)
        for preset in presets:
            key = f"divergence={str(div).lower()}/{preset}"
            row: dict[str, Any] = {"benign_fpr": _evaluate(
                detector, train, test, divergence=div, attack=None, adaptive=False, preset=preset, seed=seed,
            )["false_positive_rate"]}
            for attack in attacks:
                f1 = {mode: _evaluate(detector, train, test, divergence=div, attack=attack,
                                      adaptive=mode == "adaptive", preset=preset, seed=seed)["f1"]
                      for mode in ("static", "adaptive")}
                row[attack] = {**f1, "worst_case": min(f1.values())}
            out["results"][key] = row
    return out


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--attacks", nargs="+", default=["congestion_spoof", "replay_stale"])
    parser.add_argument("--presets", nargs="+", default=list(PRESETS))
    parser.add_argument("--seeds", type=int, nargs="+", default=[4, 5, 6, 7, 8])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="results/ml/network-impairment.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": "network_impairment", "generated_at": datetime.now(UTC).isoformat(),
                              "presets": {p: PRESETS[p] for p in args.presets}, "seeds": args.seeds,
                              "attacks": args.attacks, "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"model": m, "seed": s, "attacks": args.attacks, "presets": args.presets}
                  for m in args.models for s in args.seeds]
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
