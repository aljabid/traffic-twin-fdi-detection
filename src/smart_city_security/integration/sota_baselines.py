from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import cross_val_predict
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from smart_city_security.integration.avds_experiment import _parse_dataset, _split
from smart_city_security.integration.avds_full import MODES, _inner_attack_features
from smart_city_security.integration.real_data_experiment import _train_features, evaluate_once
from smart_city_security.integration.supervised_baseline import TARGET_FPR
from smart_city_security.iot_sim.adversary import NOVEL_ATTACKS, NOVEL_ATTACKS_2, REHEARSAL_ATTACKS
from smart_city_security.ml_detection import AnomalyDetector
from smart_city_security.schemas import Telemetry

SPEED, OCC, SPEED_DELTA, POS_DELTA, INTERARRIVAL = 0, 1, 2, 3, 4


def plausibility(features: np.ndarray) -> np.ndarray:
    dt = np.maximum(features[:, INTERARRIVAL], 1e-6)
    movement = np.abs(features[:, POS_DELTA] - (features[:, SPEED] / 3.6) * dt)
    accel = features[:, SPEED_DELTA] / dt
    extended: np.ndarray = np.column_stack([features, movement, accel])
    return extended


class _ProbabilityDetector:

    def __init__(self, name: str, model: Any, transform: Any, benign: np.ndarray, attacks: np.ndarray,
                 target_fpr: float = TARGET_FPR) -> None:
        self.name, self.model, self.transform = name, model, transform
        x = transform(np.vstack([benign, attacks]))
        y = np.concatenate([np.zeros(len(benign)), np.ones(len(attacks))])
        oof = cross_val_predict(model, x, y, cv=3, method="predict_proba")[: len(benign), 1]
        self.threshold = float(np.quantile(oof, 1.0 - target_fpr))
        self.model.fit(x, y)

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        scores = self.model.predict_proba(self.transform(features))[:, 1]
        return scores > self.threshold, scores


class KalmanChiSquared:

    name = "kalman_chi2"

    def __init__(self, benign: np.ndarray, target_fpr: float = TARGET_FPR) -> None:
        self.threshold = float(np.quantile(self._scores(benign), 1.0 - target_fpr))

    @staticmethod
    def _scores(features: np.ndarray) -> np.ndarray:
        chi2: np.ndarray = features[:, -2] ** 2 + features[:, -1] ** 2
        return chi2

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        scores = self._scores(features)
        return scores > self.threshold, scores


def run_unit(stream: Sequence[Telemetry], *, seed: int, attacks: Sequence[str],
             strength: float = 0.6) -> dict[str, Any]:
    inner, _, train, test = _split(stream, 0.45, 0.6)
    benign = _train_features(inner, twin_window=8, include_divergence=True)
    attack_rows = np.vstack([_inner_attack_features(inner, a, seed, strength) for a in REHEARSAL_ATTACKS])
    benign_kalman = _train_features(inner, twin_window=8, include_divergence=True, twin_kind="kalman")

    def identity(x: np.ndarray) -> np.ndarray:
        return x

    detectors: dict[str, tuple[AnomalyDetector, str]] = {
        "plausibility_knn": (_ProbabilityDetector(
            "plausibility_knn",
            make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=15, weights="distance")),
            plausibility, benign, attack_rows), "window"),
        "gradient_boosting": (_ProbabilityDetector(
            "gradient_boosting", HistGradientBoostingClassifier(random_state=seed),
            identity, benign, attack_rows), "window"),
        "kalman_chi2": (KalmanChiSquared(benign_kalman), "kalman"),
    }

    def score(name: str, attack: str) -> dict[str, float]:
        detector, twin_kind = detectors[name]

        def f1(adaptive: bool, search: str) -> float:
            return float(evaluate_once(
                train, test, model=name, include_divergence=True, contamination=TARGET_FPR,
                attack_name=attack, strength=strength, adaptive=adaptive, seed=seed, calibrate=True,
                fitted=(detector, TARGET_FPR), attack_mode="replace", attacker_search=search,
                twin_kind=twin_kind,
            )["f1"])

        out = {"static": f1(False, "gradient"), "gradient": f1(True, "gradient"), "grid": f1(True, "grid")}
        out["worst_case"] = min(out[m] for m in MODES)
        return out

    return {"seed": seed, "scores": {name: {a: score(name, a) for a in attacks} for name in detectors}}


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(4, 14)))
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="results/ml/sota.json")
    args = parser.parse_args(argv)
    attacks = [*REHEARSAL_ATTACKS, *NOVEL_ATTACKS, *NOVEL_ATTACKS_2]
    report: dict[str, Any] = {"experiment": "sota_baselines", "generated_at": datetime.now(UTC).isoformat(),
                              "seeds": args.seeds, "attacks": attacks, "attack_mode": "replace", "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"seed": s, "attacks": attacks} for s in args.seeds]
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
