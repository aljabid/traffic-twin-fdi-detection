from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from smart_city_security.integration.avds_experiment import _parse_dataset, _split
from smart_city_security.integration.avds_full import MODES, _inner_attack_features
from smart_city_security.integration.hybrid_detector import HybridDetector, _percentile
from smart_city_security.integration.real_data_experiment import (
    _train_features,
    evaluate_once,
    fit_detector,
)
from smart_city_security.integration.sota_baselines import _ProbabilityDetector, plausibility
from smart_city_security.integration.supervised_baseline import TARGET_FPR, SupervisedDetector
from smart_city_security.iot_sim.adversary import (
    ATTACKS,
    NOVEL_ATTACKS,
    NOVEL_ATTACKS_2,
    REHEARSAL_ATTACKS,
)
from smart_city_security.ml_detection import AnomalyDetector
from smart_city_security.schemas import Telemetry

DETECTORS = ("hybrid", "hybrid_plus", "forest_plus", "plausibility_knn")


class PlausibleForest:

    name = "forest_plus"

    def __init__(self, benign: np.ndarray, attacks: np.ndarray, seed: int,
                 target_fpr: float = TARGET_FPR) -> None:
        self.inner = SupervisedDetector(plausibility(benign), plausibility(attacks), seed, target_fpr)
        self.model = self.inner.model

    def proba(self, features: np.ndarray) -> np.ndarray:
        p: np.ndarray = self.model.predict_proba(plausibility(features))[:, 1]
        return p

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        scores = self.proba(features)
        return scores > self.inner.threshold, scores


class HybridPlus(HybridDetector):

    name = "hybrid_plus"

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        forest: PlausibleForest = self.forest
        p_forest = _percentile(self._ref_forest, forest.proba(features))
        p_lof = _percentile(self._ref_lof, self._lof_scores(features[:, : self.base_dims]))
        fused = np.maximum(p_forest, p_lof)
        return fused > self.threshold, fused


def run_unit(stream: Sequence[Telemetry], *, seed: int, attacks: Sequence[str], detectors: Sequence[str],
             train_families: Sequence[str] = REHEARSAL_ATTACKS,
             strength: float = 0.6) -> dict[str, Any]:
    inner, _, train, test = _split(stream, 0.45, 0.6)
    benign = _train_features(inner, twin_window=8, include_divergence=True)
    base_dims = _train_features(inner[:2], twin_window=8, include_divergence=False).shape[1]
    attack_rows = np.vstack([_inner_attack_features(inner, a, seed, strength) for a in train_families])
    lof, _ = fit_detector(inner, model="lof", include_divergence=False, contamination=TARGET_FPR,
                          seed=seed, calibrate=True)
    built: dict[str, AnomalyDetector] = {}
    if "hybrid" in detectors:
        built["hybrid"] = HybridDetector(SupervisedDetector(benign, attack_rows, seed), lof, benign, base_dims)
    if {"hybrid_plus", "forest_plus"} & set(detectors):
        forest_plus = PlausibleForest(benign, attack_rows, seed)
        if "forest_plus" in detectors:
            built["forest_plus"] = forest_plus
        if "hybrid_plus" in detectors:
            built["hybrid_plus"] = HybridPlus(forest_plus, lof, benign, base_dims)
    if "plausibility_knn" in detectors:
        built["plausibility_knn"] = _ProbabilityDetector(
            "plausibility_knn",
            make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=15, weights="distance")),
            plausibility, benign, attack_rows)

    def score(detector: AnomalyDetector, attack: str) -> dict[str, float]:
        def f1(adaptive: bool, search: str) -> float:
            return float(evaluate_once(
                train, test, model=detector.name, include_divergence=True, contamination=TARGET_FPR,
                attack_name=attack, strength=strength, adaptive=adaptive, seed=seed, calibrate=True,
                fitted=(detector, TARGET_FPR), attack_mode="replace", attacker_search=search,
            )["f1"])

        out = {"static": f1(False, "gradient"), "gradient": f1(True, "gradient"), "grid": f1(True, "grid")}
        out["worst_case"] = min(out[m] for m in MODES)
        return out

    return {"seed": seed, "scores": {name: {a: score(det, a) for a in attacks} for name, det in built.items()}}


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(4, 14)))
    parser.add_argument("--detectors", nargs="+", choices=DETECTORS, default=["hybrid_plus", "forest_plus"])
    parser.add_argument("--attacks", nargs="+", choices=sorted(ATTACKS),
                        default=[*REHEARSAL_ATTACKS, *NOVEL_ATTACKS, *NOVEL_ATTACKS_2],
                        help="families to score")
    parser.add_argument("--train-families", nargs="+", choices=sorted(ATTACKS), default=list(REHEARSAL_ATTACKS),
                        help="families the supervised parts are trained on (default: the four rehearsal families)")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="results/ml/hybrid-plus.json")
    args = parser.parse_args(argv)
    attacks = list(args.attacks)
    report: dict[str, Any] = {"experiment": "hybrid_plus", "generated_at": datetime.now(UTC).isoformat(),
                              "seeds": args.seeds, "detectors": args.detectors, "attacks": attacks,
                              "train_families": args.train_families,
                              "attack_mode": "replace", "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"seed": s, "attacks": attacks, "detectors": args.detectors,
                   "train_families": args.train_families} for s in args.seeds]
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
