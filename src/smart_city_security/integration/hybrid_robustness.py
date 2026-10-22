from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.evaluation import calculate_ml_metrics
from smart_city_security.integration.avds_experiment import _parse_dataset, _split
from smart_city_security.integration.avds_full import _inner_attack_features
from smart_city_security.integration.hybrid_detector import HybridDetector
from smart_city_security.integration.hybrid_plus import HybridPlus, PlausibleForest
from smart_city_security.integration.network_impairment import PRESETS, impair
from smart_city_security.integration.real_data_experiment import _train_features, fit_detector
from smart_city_security.integration.supervised_baseline import TARGET_FPR, SupervisedDetector
from smart_city_security.iot_sim.adversary import ATTACKS, REHEARSAL_ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import AnomalyDetector, FeatureBuilder
from smart_city_security.schemas import Telemetry

ATTACKS_TESTED = ("congestion_spoof", "replay_stale", "position_spoof")
NETWORK_PRESETS = ("hrllc", "lossy", "degraded", "severe")


def build(inner: Sequence[Telemetry], seed: int, strength: float,
          poison_rate: float = 0.0, poison_attack: str = "congestion_spoof"
          ) -> dict[str, tuple[AnomalyDetector, bool]]:
    training = list(inner)
    if poison_rate > 0.0:
        training = AdversarialCampaign(seed + 50_000).run(
            training, attack=ATTACKS[poison_attack], attack_ratio=poison_rate, strength=strength,
            mode="replace",
        ).messages
    benign_full = _train_features(training, twin_window=8, include_divergence=True)
    base_dims = _train_features(training[:2], twin_window=8, include_divergence=False).shape[1]
    attack_rows = np.vstack([_inner_attack_features(inner, a, seed, strength) for a in REHEARSAL_ATTACKS])
    forest = SupervisedDetector(benign_full, attack_rows, seed)
    lof, _ = fit_detector(training, model="lof", include_divergence=False, contamination=TARGET_FPR,
                          seed=seed, calibrate=True)
    hybrid = HybridDetector(forest, lof, benign_full, base_dims)
    forest_plus = PlausibleForest(benign_full, attack_rows, seed)
    hybrid_plus = HybridPlus(forest_plus, lof, benign_full, base_dims)
    return {"forest": (forest, True), "lof": (lof, False), "hybrid": (hybrid, True),
            "hybrid_plus": (hybrid_plus, True)}


def evaluate(detector: AnomalyDetector, divergence: bool, train: Sequence[Telemetry],
             test: Sequence[Telemetry], *, attack: str | None, seed: int, strength: float,
             preset: str = "hrllc", search: str = "gradient", adaptive: bool = False) -> dict[str, float]:
    twin = TrafficDigitalTwin(8)
    for m in train:
        twin.observe(m)
    builder = FeatureBuilder(divergence)
    if attack is None:
        messages, attacked = list(test), set()
    else:
        campaign = AdversarialCampaign(seed, search=search).run(
            list(test), attack=ATTACKS[attack], attack_ratio=0.15, strength=strength, adaptive=adaptive,
            detector=detector if adaptive else None, feature_builder=builder if adaptive else None,
            predict_twin_state=twin.predict if adaptive else None, mode="replace",
        )
        messages = campaign.messages
        attacked = {mid for mid, g in campaign.labels.items() if g.label == "attack"}
    loss, delay, dup = PRESETS[preset]
    arrived = impair(messages, loss=loss, max_delay=delay, duplicate=dup, seed=seed + 20_000)
    truth = [m.message_id.removesuffix("-dup") in attacked for m in arrived]
    matrix = np.vstack([builder.build(m, twin.observe(m)).values for m in arrived])
    flags, scores = detector.predict(matrix)
    metrics = calculate_ml_metrics(truth, [bool(f) for f in flags],
                                   [float(s) if np.isfinite(s) else 1e6 for s in scores])
    return {"f1": metrics.f1, "false_positive_rate": metrics.false_positive_rate}


def worst_case(detector: AnomalyDetector, divergence: bool, train: Sequence[Telemetry],
               test: Sequence[Telemetry], attack: str, seed: int, strength: float, preset: str) -> float:
    common: dict[str, Any] = {"attack": attack, "seed": seed, "strength": strength, "preset": preset}
    return min(
        evaluate(detector, divergence, train, test, **common)["f1"],
        evaluate(detector, divergence, train, test, adaptive=True, search="gradient", **common)["f1"],
        evaluate(detector, divergence, train, test, adaptive=True, search="grid", **common)["f1"],
    )


def run_unit(stream: Sequence[Telemetry], *, seed: int, mode: str, poison_rates: Sequence[float] = (0.05, 0.10),
             strength: float = 0.6) -> dict[str, Any]:
    inner, _, train, test = _split(stream, 0.45, 0.6)
    out: dict[str, Any] = {"seed": seed}
    if mode == "network":
        detectors = build(inner, seed, strength)
        out["network"] = {
            preset: {
                name: {
                    "benign_fpr": evaluate(det, div, train, test, attack=None, seed=seed, strength=strength,
                                           preset=preset)["false_positive_rate"],
                    **{a: worst_case(det, div, train, test, a, seed, strength, preset) for a in ATTACKS_TESTED},
                }
                for name, (det, div) in detectors.items()
            }
            for preset in NETWORK_PRESETS
        }
    else:
        out["poisoning"] = {}
        for rate in (0.0, *poison_rates):
            detectors = build(inner, seed, strength, poison_rate=rate)
            out["poisoning"][str(rate)] = {
                name: {a: worst_case(det, div, train, test, a, seed, strength, "ideal") for a in ATTACKS_TESTED}
                for name, (det, div) in detectors.items()
            }
    return out


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--mode", choices=("network", "poisoning"), required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[4, 5, 6, 7, 8])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="results/ml/hybrid-robustness.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": f"hybrid_robustness_{args.mode}",
                              "generated_at": datetime.now(UTC).isoformat(), "seeds": args.seeds,
                              "attacks": list(ATTACKS_TESTED), "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"seed": s, "mode": args.mode} for s in args.seeds]
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
