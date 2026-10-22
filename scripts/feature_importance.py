from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.integration.real_data_experiment import (
    DEFAULT_MODELS,
    _temporal_split,
    fit_detector,
    load_dataset,
)
from smart_city_security.iot_sim.adversary import ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import FeatureBuilder

ROOT = Path(__file__).resolve().parents[1]
REPEATS = 5


def _auc(truth: np.ndarray, scores: np.ndarray) -> float:
    return float(roc_auc_score(truth, np.nan_to_num(scores, posinf=1e12)))


def importance(source: str, model: str, attack: str, adaptive: bool, seed: int) -> dict[str, float]:
    train, test = _temporal_split(load_dataset(source).telemetry, 0.6)
    detector, _ = fit_detector(train, model=model, include_divergence=True, contamination=0.05,
                               seed=seed, calibrate=True)
    twin = TrafficDigitalTwin(8)
    for m in train:
        twin.observe(m)
    builder = FeatureBuilder(True)
    campaign = AdversarialCampaign(seed).run(
        list(test), attack=ATTACKS[attack], attack_ratio=0.15, strength=0.6, adaptive=adaptive,
        detector=detector if adaptive else None, feature_builder=builder if adaptive else None,
        predict_twin_state=twin.predict if adaptive else None,
    )
    truth = np.array([campaign.labels[m.message_id].label == "attack" for m in campaign.messages])
    matrix = np.vstack([builder.build(m, twin.observe(m)).values for m in campaign.messages])
    base = _auc(truth, np.asarray(detector.predict(matrix)[1], dtype=float))
    rng = np.random.default_rng(seed)
    drops = {}
    for j, name in enumerate(builder.feature_names):
        aucs = []
        for _ in range(REPEATS):
            shuffled = matrix.copy()
            shuffled[:, j] = rng.permutation(shuffled[:, j])
            aucs.append(_auc(truth, np.asarray(detector.predict(shuffled)[1], dtype=float)))
        drops[name] = base - float(np.mean(aucs))
    return {"base_auc": base, **drops}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", nargs="+", default=["sumo", "ngsim", "pneuma"])
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--attacks", nargs="+", default=["congestion_spoof", "replay_stale"])
    parser.add_argument("--seed", type=int, default=4)
    args = parser.parse_args()
    results = {}
    for source in args.sources:
        for model in args.models:
            for attack in args.attacks:
                for adaptive in (False, True):
                    key = f"{source}/{model}/{attack}/adaptive={str(adaptive).lower()}"
                    r = importance(source, model, attack, adaptive, args.seed)
                    results[key] = r
                    top = sorted(((k, v) for k, v in r.items() if k != "base_auc"), key=lambda kv: -kv[1])[:3]
                    print(f"{key:58} AUC={r['base_auc']:.3f} top: " + ", ".join(f"{k} {v:+.3f}" for k, v in top))
    out = ROOT / "results" / "ml" / "feature-importance.json"
    out.write_text(json.dumps({"seed": args.seed, "repeats": REPEATS, "results": results}, indent=2), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
