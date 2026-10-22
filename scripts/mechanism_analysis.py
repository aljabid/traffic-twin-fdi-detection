from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.evaluation import calculate_ml_metrics
from smart_city_security.integration.real_data_experiment import (
    _temporal_split,
    _train_features,
    load_dataset,
)
from smart_city_security.iot_sim.adversary import ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import FeatureBuilder
from smart_city_security.ml_detection.calibration import DetectorCalibrator

ROOT = Path(__file__).resolve().parents[1]


def _auc(truth: list[bool], values: np.ndarray) -> float:
    auc = float(roc_auc_score(truth, values))
    return max(auc, 1.0 - auc)


def analyse(train, test, *, model: str, divergence: bool, attack: str, adaptive: bool, seed: int):
    features = _train_features(train, twin_window=8, include_divergence=divergence)
    calibrator = DetectorCalibrator(model, target_false_positive_rate=0.05, seed=seed)
    for row in features:
        calibrator.add(row)
    detector, _ = calibrator.fit()

    twin = TrafficDigitalTwin(8)
    for m in train:
        twin.observe(m)
    builder = FeatureBuilder(divergence)
    campaign = AdversarialCampaign(seed).run(
        list(test), attack=ATTACKS[attack], attack_ratio=0.15, strength=0.6, adaptive=adaptive,
        detector=detector if adaptive else None,
        feature_builder=builder if adaptive else None,
        predict_twin_state=twin.predict if adaptive else None,
    )
    truth = [campaign.labels[m.message_id].label == "attack" for m in campaign.messages]
    full_twin = TrafficDigitalTwin(8)
    for m in train:
        full_twin.observe(m)
    full = FeatureBuilder(True)
    all_features = np.vstack([full.build(m, full_twin.observe(m)).values for m in campaign.messages])
    matrix = np.vstack([builder.build(m, twin.observe(m)).values for m in campaign.messages])
    flags, scores = detector.predict(matrix)
    scores = np.nan_to_num(np.asarray(scores, dtype=float), posinf=1e6)
    metrics = calculate_ml_metrics(truth, [bool(f) for f in flags], scores.tolist())
    return {
        "f1": metrics.f1,
        "score_auc": _auc(truth, scores),
        "feature_auc": {name: _auc(truth, all_features[:, i]) for i, name in enumerate(full.feature_names)},
        "mean_speed_strength_used": campaign.mean_speed_strength_used,
        "mean_occupancy_strength_used": campaign.mean_occupancy_strength_used,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="sumo")
    parser.add_argument("--attack", default="congestion_spoof")
    parser.add_argument("--seed", type=int, default=4)
    parser.add_argument("--models", nargs="+", default=["mahalanobis", "lof"])
    args = parser.parse_args()

    train, test = _temporal_split(load_dataset(args.source).telemetry, 0.6)
    results = {}
    for model in args.models:
        for divergence in (False, True):
            for adaptive in (False, True):
                key = f"{model}/divergence={str(divergence).lower()}/adaptive={str(adaptive).lower()}"
                results[key] = analyse(train, test, model=model, divergence=divergence,
                                       attack=args.attack, adaptive=adaptive, seed=args.seed)
                r = results[key]
                print(f"{key:48} F1={r['f1']:.3f} scoreAUC={r['score_auc']:.3f} "
                      f"strength(s,o)=({r['mean_speed_strength_used']:.2f},{r['mean_occupancy_strength_used']:.2f})")
    print("\nper-feature AUC, attack vs benign (static | adaptive vs the no-divergence detector):")
    first = args.models[0]
    static = results[f"{first}/divergence=false/adaptive=false"]["feature_auc"]
    for name in static:
        row = " ".join(
            f"{results[f'{m}/divergence=false/adaptive=true']['feature_auc'][name]:.3f}" for m in args.models
        )
        print(f"  {name:24} static={static[name]:.3f} | adaptive vs {'/'.join(args.models)}: {row}")
    out = ROOT / "results" / "ml" / f"mechanism-{args.source}-{args.attack}-seed{args.seed}.json"
    out.write_text(json.dumps({"source": args.source, "attack": args.attack, "seed": args.seed,
                               "results": results}, indent=2), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
