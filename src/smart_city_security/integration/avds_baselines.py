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
from smart_city_security.integration.real_data_experiment import (
    DEFAULT_MODELS,
    _train_features,
    evaluate_once,
    fit_detector,
)
from smart_city_security.iot_sim.adversary import REHEARSAL_ATTACKS
from smart_city_security.ml_detection import AnomalyDetector
from smart_city_security.schemas import Telemetry

TARGET_FPR = 0.05


class FusionDetector:

    name = "fusion"

    def __init__(self, off: AnomalyDetector, on: AnomalyDetector,
                 train_off: np.ndarray, train_on: np.ndarray, target_fpr: float = TARGET_FPR) -> None:
        self.off, self.on = off, on
        self.base_dims = train_off.shape[1]
        self._ref_off = np.sort(self._scores(off, train_off))
        self._ref_on = np.sort(self._scores(on, train_on))
        fused_train = self._fuse(self._scores(off, train_off), self._scores(on, train_on))
        self.threshold = float(np.quantile(fused_train, 1.0 - target_fpr))

    @staticmethod
    def _scores(detector: AnomalyDetector, features: np.ndarray) -> np.ndarray:
        _, scores = detector.predict(features)
        cleaned: np.ndarray = np.nan_to_num(np.asarray(scores, dtype=float), nan=np.inf, posinf=np.inf)
        return cleaned

    def _fuse(self, s_off: np.ndarray, s_on: np.ndarray) -> np.ndarray:
        p_off = np.searchsorted(self._ref_off, s_off, side="right") / len(self._ref_off)
        p_on = np.searchsorted(self._ref_on, s_on, side="right") / len(self._ref_on)
        fused: np.ndarray = np.maximum(p_off, p_on)
        return fused

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        fused = self._fuse(self._scores(self.off, features[:, : self.base_dims]),
                           self._scores(self.on, features))
        return fused > self.threshold, fused


def _clean_fpr(detector: AnomalyDetector, stream: Sequence[Telemetry], warmup: Sequence[Telemetry],
               divergence: bool) -> float:
    features = _train_features([*warmup, *stream], twin_window=8, include_divergence=divergence)
    flags, _ = detector.predict(features[len(warmup):])
    return float(np.mean(np.asarray(flags, dtype=bool)))


def run_unit(stream: Sequence[Telemetry], *, model: str, seed: int, attacks: Sequence[str],
             strength: float = 0.6, contamination: float = 0.05,
             inner_fraction: float = 0.45, train_fraction: float = 0.6,
             attack_mode: str = "inject") -> dict[str, Any]:
    inner, validation, train, test = _split(stream, inner_fraction, train_fraction)

    inner_fits = {div: fit_detector(inner, model=model, include_divergence=div,
                                    contamination=contamination, seed=seed, calibrate=True)
                  for div in (False, True)}
    fpr = {div: _clean_fpr(inner_fits[div][0], validation, inner, div) for div in (False, True)}
    clean_choice = fpr[True] < fpr[False]

    inner_fusion = FusionDetector(inner_fits[False][0], inner_fits[True][0],
                                  _train_features(inner, twin_window=8, include_divergence=False),
                                  _train_features(inner, twin_window=8, include_divergence=True))
    ensemble_validation = {
        attack: {
            mode: evaluate_once(inner, validation, model=model, include_divergence=True,
                                contamination=contamination, attack_name=attack, strength=strength,
                                adaptive=mode == "adaptive", seed=seed, calibrate=True,
                                fitted=(inner_fusion, inner_fits[False][1]), attack_mode=attack_mode)["f1"]
            for mode in ("static", "adaptive")
        }
        for attack in attacks
    }

    off, chosen_off = fit_detector(train, model=model, include_divergence=False,
                                   contamination=contamination, seed=seed, calibrate=True)
    on, _ = fit_detector(train, model=model, include_divergence=True,
                         contamination=contamination, seed=seed, calibrate=True)
    fusion = FusionDetector(off, on,
                            _train_features(train, twin_window=8, include_divergence=False),
                            _train_features(train, twin_window=8, include_divergence=True))
    ensemble = {}
    for attack in attacks:
        scores = {
            mode: evaluate_once(train, test, model=model, include_divergence=True,
                                contamination=contamination, attack_name=attack, strength=strength,
                                adaptive=mode == "adaptive", seed=seed, calibrate=True,
                                fitted=(fusion, chosen_off), attack_mode=attack_mode)["f1"]
            for mode in ("static", "adaptive")
        }
        ensemble[attack] = {**scores, "worst_case": min(scores.values())}
    return {"model": model, "seed": seed, "clean_validation_fpr": {str(k).lower(): v for k, v in fpr.items()},
            "clean_choice": clean_choice, "ensemble": ensemble,
            "ensemble_validation": ensemble_validation}


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--attacks", nargs="+", default=list(REHEARSAL_ATTACKS))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(4, 14)))
    parser.add_argument("--max-messages", type=int, default=40_000)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--attack-mode", choices=("inject", "replace"), default="inject")
    parser.add_argument("--output", default="results/ml/avds-baselines.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": "avds_baselines", "generated_at": datetime.now(UTC).isoformat(),
                              "seeds": args.seeds, "attacks": args.attacks, "attack_mode": args.attack_mode,
                              "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, args.max_messages)
        kwargs = [{"model": m, "seed": s, "attacks": args.attacks, "attack_mode": args.attack_mode}
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
