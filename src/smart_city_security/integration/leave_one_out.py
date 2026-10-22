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
from smart_city_security.integration.hybrid_detector import HybridDetector
from smart_city_security.integration.hybrid_plus import HybridPlus, PlausibleForest
from smart_city_security.integration.real_data_experiment import (
    _train_features,
    evaluate_once,
    fit_detector,
)
from smart_city_security.integration.supervised_baseline import TARGET_FPR, SupervisedDetector
from smart_city_security.iot_sim.adversary import NOVEL_ATTACKS, NOVEL_ATTACKS_2, REHEARSAL_ATTACKS
from smart_city_security.ml_detection import AnomalyDetector
from smart_city_security.schemas import Telemetry

FAMILIES = (*REHEARSAL_ATTACKS, *NOVEL_ATTACKS, *NOVEL_ATTACKS_2)
CATEGORIES = {
    "value": ("congestion_spoof", "clear_road_spoof", "drift_congestion", "noise_injection"),
    "stale": ("replay_stale", "stuck_at"),
    "time": ("time_shift", "backdate"),
    "position": ("position_spoof",),
    "identity": ("identity_spoof",),
}


def run_unit(stream: Sequence[Telemetry], *, seed: int, families: Sequence[str] = FAMILIES,
             strength: float = 0.6, by_category: bool = False) -> dict[str, Any]:
    inner, _, train, test = _split(stream, 0.45, 0.6)
    benign = _train_features(inner, twin_window=8, include_divergence=True)
    base_dims = _train_features(inner[:2], twin_window=8, include_divergence=False).shape[1]
    rows = {a: _inner_attack_features(inner, a, seed, strength) for a in families}
    lof, _ = fit_detector(inner, model="lof", include_divergence=False, contamination=TARGET_FPR,
                          seed=seed, calibrate=True)

    def score(detector: AnomalyDetector, attack: str, divergence: bool = True) -> dict[str, float]:
        def f1(adaptive: bool, search: str) -> float:
            return float(evaluate_once(
                train, test, model=detector.name, include_divergence=divergence, contamination=TARGET_FPR,
                attack_name=attack, strength=strength, adaptive=adaptive, seed=seed, calibrate=True,
                fitted=(detector, TARGET_FPR), attack_mode="replace", attacker_search=search,
            )["f1"])

        out = {"static": f1(False, "gradient"), "gradient": f1(True, "gradient"), "grid": f1(True, "grid")}
        out["worst_case"] = min(out[m] for m in MODES)
        return out

    def build(held: Sequence[str]) -> dict[str, AnomalyDetector]:
        attack_rows = np.vstack([rows[a] for a in families if a not in held])
        forest = SupervisedDetector(benign, attack_rows, seed)
        forest_plus = PlausibleForest(benign, attack_rows, seed)
        return {
            "forest": forest,
            "forest_plus": forest_plus,
            "hybrid": HybridDetector(forest, lof, benign, base_dims),
            "hybrid_plus": HybridPlus(forest_plus, lof, benign, base_dims),
        }

    unseen: dict[str, dict[str, dict[str, float]]] = {}
    if by_category:
        for group in CATEGORIES.values():
            members = [a for a in group if a in families]
            if not members or len(members) == len(families):
                continue
            for name, det in build(members).items():
                for a in members:
                    unseen.setdefault(name, {})[a] = score(det, a)
        return {"seed": seed, "unseen_category": unseen}
    seen = {name: {a: score(det, a) for a in families} for name, det in build(()).items()}
    for held in families:
        for name, det in build((held,)).items():
            unseen.setdefault(name, {})[held] = score(det, held)
    return {"seed": seed, "seen": seen, "unseen": unseen,
            "lof": {a: score(lof, a, divergence=False) for a in families}}


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(4, 14)))
    parser.add_argument("--by-category", action="store_true",
                        help="withhold the scored family's whole category (see CATEGORIES)")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="results/ml/leave-one-out.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": "leave_one_family_out", "generated_at": datetime.now(UTC).isoformat(),
                              "seeds": args.seeds, "families": list(FAMILIES), "attack_mode": "replace",
                              "by_category": args.by_category, "categories": CATEGORIES,
                              "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"seed": s, "by_category": args.by_category} for s in args.seeds]
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
