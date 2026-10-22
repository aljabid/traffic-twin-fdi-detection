from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from smart_city_security.integration.avds_experiment import _parse_dataset, _split
from smart_city_security.integration.avds_full import MODES, _inner_attack_features
from smart_city_security.integration.real_data_experiment import (
    _train_features,
    evaluate_once,
    fit_detector,
)
from smart_city_security.integration.supervised_baseline import TARGET_FPR, SupervisedDetector
from smart_city_security.iot_sim.adversary import NOVEL_ATTACKS, REHEARSAL_ATTACKS
from smart_city_security.ml_detection import AnomalyDetector
from smart_city_security.schemas import Telemetry


def _percentile(reference: np.ndarray, scores: np.ndarray) -> np.ndarray:
    pct: np.ndarray = np.searchsorted(reference, scores, side="right") / len(reference)
    return pct


class HybridDetector:

    name = "hybrid_rf_lof"

    def __init__(self, forest: SupervisedDetector, lof: AnomalyDetector, benign_full: np.ndarray,
                 base_dims: int, target_fpr: float = TARGET_FPR) -> None:
        self.forest, self.lof, self.base_dims = forest, lof, base_dims
        oob = np.nan_to_num(forest.model.oob_decision_function_[: len(benign_full), 1])
        self._ref_forest = np.sort(oob)
        lof_scores = self._lof_scores(benign_full[:, :base_dims])
        self._ref_lof = np.sort(lof_scores)
        fused = np.maximum(_percentile(self._ref_forest, oob), _percentile(self._ref_lof, lof_scores))
        self.threshold = float(np.quantile(fused, 1.0 - target_fpr))

    def _lof_scores(self, features: np.ndarray) -> np.ndarray:
        _, scores = self.lof.predict(features)
        cleaned: np.ndarray = np.nan_to_num(np.asarray(scores, dtype=float), nan=np.inf, posinf=np.inf)
        return cleaned

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        p_forest = _percentile(self._ref_forest, self.forest.model.predict_proba(features)[:, 1])
        p_lof = _percentile(self._ref_lof, self._lof_scores(features[:, : self.base_dims]))
        fused = np.maximum(p_forest, p_lof)
        return fused > self.threshold, fused


def run_unit(stream: Sequence[Telemetry], *, seed: int, rehearsal: Sequence[str], novel: Sequence[str],
             strength: float = 0.6) -> dict[str, Any]:
    inner, _, train, test = _split(stream, 0.45, 0.6)
    benign_full = _train_features(inner, twin_window=8, include_divergence=True)
    base_dims = _train_features(inner[:2], twin_window=8, include_divergence=False).shape[1]
    attacks = np.vstack([_inner_attack_features(inner, a, seed, strength) for a in rehearsal])
    forest = SupervisedDetector(benign_full, attacks, seed)
    lof, lof_contamination = fit_detector(inner, model="lof", include_divergence=False,
                                          contamination=TARGET_FPR, seed=seed, calibrate=True)
    hybrid = HybridDetector(forest, lof, benign_full, base_dims)
    detectors: dict[str, tuple[AnomalyDetector, float, bool]] = {
        "forest": (forest, TARGET_FPR, True),
        "lof": (lof, lof_contamination, False),
        "hybrid": (hybrid, TARGET_FPR, True),
    }

    def score(name: str, attack: str) -> dict[str, float]:
        detector, contamination, divergence = detectors[name]

        def f1(adaptive: bool, search: str) -> float:
            return float(evaluate_once(
                train, test, model=name, include_divergence=divergence, contamination=contamination,
                attack_name=attack, strength=strength, adaptive=adaptive, seed=seed, calibrate=True,
                fitted=(detector, contamination), attack_mode="replace", attacker_search=search,
            )["f1"])

        out = {"static": f1(False, "gradient"), "gradient": f1(True, "gradient"), "grid": f1(True, "grid")}
        out["worst_case"] = min(out[m] for m in MODES)
        return out

    return {"seed": seed,
            "scores": {name: {a: score(name, a) for a in (*rehearsal, *novel)} for name in detectors}}


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[4, 5, 6, 7, 8])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--novel", nargs="+", default=list(NOVEL_ATTACKS),
                        help="held-out attack families to score (never used in training)")
    parser.add_argument("--output", default="results/ml/hybrid.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": "hybrid_forest_lof", "generated_at": datetime.now(UTC).isoformat(),
                              "seeds": args.seeds, "rehearsal": list(REHEARSAL_ATTACKS),
                              "novel": args.novel, "attack_mode": "replace", "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"seed": s, "rehearsal": list(REHEARSAL_ATTACKS), "novel": list(args.novel)}
                  for s in args.seeds]
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
