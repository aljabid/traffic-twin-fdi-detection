from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

import numpy as np

from smart_city_security.digital_twin.kalman_twin import make_twin
from smart_city_security.evaluation import calculate_ml_metrics, paired_compare
from smart_city_security.evaluation.real_datasets import (
    data_root,
    ngsim_rows_to_telemetry,
    pneuma_lines_to_telemetry,
    sumo_fcd_rows_to_telemetry,
)
from smart_city_security.iot_sim.adversary import ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import AnomalyDetector, FeatureBuilder, train_detector
from smart_city_security.ml_detection.calibration import DetectorCalibrator
from smart_city_security.schemas import Telemetry

DEFAULT_MODELS = ("isolation_forest", "autoencoder", "lof", "mahalanobis", "ewma_residual")
DEFAULT_ATTACKS = ("congestion_spoof", "clear_road_spoof")
DEFAULT_SEEDS = (1, 2, 3, 4, 5)
_METRICS = ("precision", "recall", "f1", "false_positive_rate", "accuracy")


@dataclass(frozen=True, slots=True)
class Dataset:
    name: str
    telemetry: list[Telemetry]


def load_dataset(name: str, *, path: str | Path | None = None, max_messages: int = 40_000) -> Dataset:
    root = data_root()
    if name == "ngsim":
        src = Path(path or root / "ngsim" / "ngsim_full.csv")
        with src.open(newline="", encoding="utf-8") as handle:
            rows = sorted(
                csv.DictReader(handle),
                key=lambda r: (r["location"], int(r["vehicle_id"]), int(r["frame_id"])),
            )
        stream = list(ngsim_rows_to_telemetry(rows))
    elif name == "pneuma":
        src = Path(path or root / "pneuma" / "session.csv")
        with src.open(encoding="utf-8") as handle:
            stream = list(pneuma_lines_to_telemetry(handle))
    elif name == "sumo":
        src = Path(path or root / "sumo" / "sumo_fcd_full.csv")
        with src.open(newline="", encoding="utf-8") as handle:
            stream = list(sumo_fcd_rows_to_telemetry(csv.DictReader(handle)))
    else:
        raise ValueError(f"unknown dataset: {name}")
    stream.sort(key=lambda t: (t.timestamp, t.device_id, t.sequence_number))
    if len(stream) > max_messages:
        stream = stream[:max_messages]
    return Dataset(name, stream)


def _temporal_split(stream: Sequence[Telemetry], train_fraction: float) -> tuple[list[Telemetry], list[Telemetry]]:
    cut = int(len(stream) * train_fraction)
    return list(stream[:cut]), list(stream[cut:])


def _train_features(
    train: Sequence[Telemetry], *, twin_window: int, include_divergence: bool, twin_kind: str = "window",
    divergence_transform: str = "none",
    feature_history: int = 1,
) -> np.ndarray:
    twin = make_twin(twin_kind, twin_window)
    builder = FeatureBuilder(include_divergence, divergence_transform, feature_history)
    rows = [builder.build(m, twin.observe(m)).values for m in train]
    return np.vstack(rows) if rows else np.empty((0, len(builder.feature_names)))


def fit_detector(
    train: Sequence[Telemetry],
    *,
    model: str,
    include_divergence: bool,
    contamination: float,
    seed: int,
    twin_window: int = 8,
    calibrate: bool = False,
    target_fpr: float = 0.05,
    twin_kind: str = "window",
    divergence_transform: str = "none",
    feature_history: int = 1,
) -> tuple[AnomalyDetector, float]:
    features = _train_features(train, twin_window=twin_window, include_divergence=include_divergence,
                               twin_kind=twin_kind, divergence_transform=divergence_transform,
                               feature_history=feature_history)
    if calibrate:
        calibrator = DetectorCalibrator(model, target_false_positive_rate=target_fpr, seed=seed)
        for row in features:
            calibrator.add(row)
        detector, calib = calibrator.fit()
        return detector, calib.contamination
    return train_detector(model, features, contamination=contamination, seed=seed), contamination


def evaluate_once(
    train: Sequence[Telemetry],
    test: Sequence[Telemetry],
    *,
    model: str,
    include_divergence: bool,
    contamination: float,
    attack_name: str,
    strength: float,
    adaptive: bool,
    seed: int,
    twin_window: int = 8,
    attack_ratio: float = 0.15,
    calibrate: bool = False,
    target_fpr: float = 0.05,
    fitted: tuple[AnomalyDetector, float] | None = None,
    twin_kind: str = "window",
    attacker_steps: int = 8,
    divergence_transform: str = "none",
    feature_history: int = 1,
    attack_mode: str = "inject",
    attacker_search: str = "gradient",
) -> dict[str, Any]:
    detector, chosen_contamination = fitted or fit_detector(
        train, model=model, include_divergence=include_divergence, contamination=contamination,
        seed=seed, twin_window=twin_window, calibrate=calibrate, target_fpr=target_fpr,
        twin_kind=twin_kind, divergence_transform=divergence_transform, feature_history=feature_history,
    )

    twin = make_twin(twin_kind, twin_window)
    for m in train:
        twin.observe(m)
    builder = FeatureBuilder(include_divergence, divergence_transform, feature_history)

    campaign = AdversarialCampaign(seed, search_steps=attacker_steps, search=attacker_search).run(
        list(test),
        attack=ATTACKS[attack_name],
        attack_ratio=attack_ratio,
        strength=strength,
        adaptive=adaptive,
        detector=detector if adaptive else None,
        feature_builder=builder if adaptive else None,
        predict_twin_state=twin.predict if adaptive else None,
        mode=attack_mode,
    )

    truth = [campaign.labels[m.message_id].label == "attack" for m in campaign.messages]
    matrix = np.vstack(
        [builder.build(m, twin.observe(m)).values for m in campaign.messages]
    )
    labels_out, scores_out = detector.predict(matrix)
    predictions = [bool(v) for v in labels_out]
    scores = [float(s) if np.isfinite(s) else 1e6 for s in scores_out]

    metrics = calculate_ml_metrics(truth, predictions, scores)
    result = metrics.to_dict()
    result.update(
        {
            "seed": seed,
            "chosen_contamination": chosen_contamination,
            "attacker_backoff_fraction": campaign.evaded_fraction,
            "mean_strength_used": campaign.mean_strength_used,
            "n_test": len(test),
            "n_attacks": sum(truth),
        }
    )
    return result


def run_experiment(
    datasets: Sequence[Dataset],
    *,
    models: Sequence[str] = DEFAULT_MODELS,
    attacks: Sequence[str] = DEFAULT_ATTACKS,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    strength: float = 0.6,
    contamination: float = 0.05,
    calibrate: bool = True,
    train_fraction: float = 0.6,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "experiment": "real_data_detection",
        "generated_at": datetime.now(UTC).isoformat(),
        "seeds": list(seeds),
        "strength": strength,
        "calibrated": calibrate,
        "results": {},
        "significance": {},
    }
    for dataset in datasets:
        train, test = _temporal_split(dataset.telemetry, train_fraction)
        by_config: dict[tuple[str, bool, str, bool], list[dict[str, Any]]] = {}
        for model in models:
            for include_divergence in (False, True):
                for attack_name in attacks:
                    for adaptive in (False, True):
                        runs = [
                            evaluate_once(
                                train, test,
                                model=model, include_divergence=include_divergence,
                                contamination=contamination, attack_name=attack_name,
                                strength=strength, adaptive=adaptive, seed=seed,
                                calibrate=calibrate,
                            )
                            for seed in seeds
                        ]
                        by_config[(model, include_divergence, attack_name, adaptive)] = runs
                        key = (
                            f"{dataset.name}/{model}/divergence={str(include_divergence).lower()}"
                            f"/{attack_name}/adaptive={str(adaptive).lower()}"
                        )
                        report["results"][key] = {
                            "runs": runs,
                            "mean": {m: fmean(r[m] for r in runs) for m in _METRICS},
                            "std": {m: pstdev(r[m] for r in runs) for m in _METRICS},
                            "mean_attacker_backoff": fmean(r["attacker_backoff_fraction"] for r in runs),
                            "mean_strength_used": fmean(r["mean_strength_used"] for r in runs),
                        }

        for model in models:
            for attack_name in attacks:
                for adaptive in (False, True):
                    runs_off = by_config[(model, False, attack_name, adaptive)]
                    runs_on = by_config[(model, True, attack_name, adaptive)]
                    key = f"{dataset.name}/{model}/{attack_name}/adaptive={str(adaptive).lower()}/divergence_effect"
                    report["significance"][key] = {
                        m: paired_compare(
                            [r[m] for r in runs_off], [r[m] for r in runs_on], metric=m
                        ).to_dict()
                        for m in ("f1", "false_positive_rate", "recall")
                    }
                for include_divergence in (False, True):
                    runs_static = by_config[(model, include_divergence, attack_name, False)]
                    runs_adaptive = by_config[(model, include_divergence, attack_name, True)]
                    key = (
                        f"{dataset.name}/{model}/{attack_name}"
                        f"/divergence={str(include_divergence).lower()}/adaptive_effect"
                    )
                    report["significance"][key] = {
                        m: paired_compare(
                            [r[m] for r in runs_static], [r[m] for r in runs_adaptive], metric=m
                        ).to_dict()
                        for m in ("f1", "false_positive_rate", "recall")
                    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--attacks", nargs="+", default=list(DEFAULT_ATTACKS))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--strength", type=float, default=0.6)
    parser.add_argument("--max-messages", type=int, default=40_000)
    parser.add_argument("--no-calibrate", action="store_true")
    parser.add_argument("--output", default="results/ml/real-data-detection.json")
    args = parser.parse_args(argv)

    datasets = [load_dataset(name, max_messages=args.max_messages) for name in args.datasets]
    report = run_experiment(
        datasets, models=args.models, attacks=args.attacks, seeds=args.seeds,
        strength=args.strength, calibrate=not args.no_calibrate,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
