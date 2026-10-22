from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.evaluation import calculate_ml_metrics
from smart_city_security.evaluation.real_datasets import data_root
from smart_city_security.evaluation.v2x_datasets import RawMessage, read_veremi, to_telemetry
from smart_city_security.integration.hybrid_detector import HybridDetector
from smart_city_security.integration.hybrid_plus import HybridPlus, PlausibleForest
from smart_city_security.integration.real_data_experiment import _train_features, fit_detector
from smart_city_security.integration.sota_baselines import _ProbabilityDetector, plausibility
from smart_city_security.integration.supervised_baseline import TARGET_FPR, SupervisedDetector
from smart_city_security.ml_detection import AnomalyDetector, FeatureBuilder
from smart_city_security.schemas import Telemetry

CATEGORIES = {
    "ConstPos": "position", "ConstPosOffset": "position", "RandomPos": "position", "RandomPosOffset": "position",
    "ConstSpeed": "speed", "ConstSpeedOffset": "speed", "RandomSpeed": "speed", "RandomSpeedOffset": "speed",
    "EventualStop": "stop", "DataReplay": "replay", "DelayedMessages": "delay",
}
SETTINGS = ("seen", "unseen_type", "unseen_category")
MAX_ATTACK_ROWS = 2_000
MIN_WINDOW_MESSAGES = 5_000


def _window(raw: Sequence[RawMessage], index: int, window_s: float) -> list[RawMessage]:
    start = min(m.time for m in raw) + index * window_s
    return [m for m in raw if start <= m.time < start + window_s]


def _features(warm: Sequence[Telemetry], stream: Sequence[Telemetry]) -> np.ndarray:
    twin = TrafficDigitalTwin(8)
    for m in warm:
        twin.observe(m)
    builder = FeatureBuilder(True)
    return np.vstack([builder.build(m, twin.observe(m)).values for m in stream])


def prepare(raw: Sequence[RawMessage], name: str) -> dict[str, Any]:
    stream, attacked = to_telemetry(raw, prefix=name)
    cut_train, cut_test = int(len(stream) * 0.45), int(len(stream) * 0.6)
    train, test = stream[:cut_train], stream[cut_test:]
    train_rows = _features([], train)
    is_attack = np.asarray([m.message_id in attacked for m in train])
    return {
        "benign_train": [m for m in train if m.message_id not in attacked],
        "attack_rows": train_rows[is_attack],
        "test_features": _features(train, test),
        "test_labels": np.asarray([m.message_id in attacked for m in test]),
    }


def _sample(rows: np.ndarray, seed: int) -> np.ndarray:
    if len(rows) <= MAX_ATTACK_ROWS:
        return rows
    picked: np.ndarray = rows[np.random.default_rng(seed).choice(len(rows), MAX_ATTACK_ROWS, replace=False)]
    return picked


def evaluate_window(prepared: dict[str, dict[str, Any]], target: str, *, seed: int) -> dict[str, Any]:
    benign_stream = prepared[target]["benign_train"]
    benign = _train_features(benign_stream, twin_window=8, include_divergence=True)
    base_dims = _train_features(benign_stream[:2], twin_window=8, include_divergence=False).shape[1]
    lof, _ = fit_detector(benign_stream, model="lof", include_divergence=False, contamination=TARGET_FPR,
                          seed=seed, calibrate=True)
    features, labels = prepared[target]["test_features"], prepared[target]["test_labels"]

    def score(detector: AnomalyDetector, matrix: np.ndarray) -> dict[str, float]:
        flags, _ = detector.predict(matrix)
        m = calculate_ml_metrics(labels.tolist(), [bool(f) for f in flags])
        return {"f1": m.f1, "precision": m.precision, "recall": m.recall, "fpr": m.false_positive_rate}

    out: dict[str, Any] = {"lof": score(lof, features[:, :base_dims])}
    for setting in SETTINGS:
        allowed = [
            t for t in prepared
            if setting == "seen" or (setting == "unseen_type" and t != target)
            or (setting == "unseen_category" and CATEGORIES[t] != CATEGORIES[target])
        ]
        rows = [_sample(prepared[t]["attack_rows"], seed) for t in allowed if len(prepared[t]["attack_rows"])]
        if not rows:
            continue
        attack_rows = np.vstack(rows)
        forest = SupervisedDetector(benign, attack_rows, seed)
        forest_plus = PlausibleForest(benign, attack_rows, seed)
        detectors: dict[str, AnomalyDetector] = {
            "forest": forest,
            "forest_plus": forest_plus,
            "hybrid": HybridDetector(forest, lof, benign, base_dims),
            "hybrid_plus": HybridPlus(forest_plus, lof, benign, base_dims),
            "plausibility_knn": _ProbabilityDetector(
                "plausibility_knn",
                make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=15, weights="distance")),
                plausibility, benign, attack_rows),
        }
        out[setting] = {name: score(det, features) for name, det in detectors.items()}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=None, help="folder with <Attack>_1416.zip files")
    parser.add_argument("--attacks", nargs="+", choices=sorted(CATEGORIES), default=list(CATEGORIES))
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--window-seconds", type=float, default=1500.0)
    parser.add_argument("--seed", type=int, default=4)
    parser.add_argument("--output", default="results/ml/veremi-benchmark.json")
    args = parser.parse_args(argv)
    root = args.root or data_root() / "veremi"
    raw = {a: read_veremi(root / f"{a}_1416.zip", duration_s=None) for a in args.attacks}
    report: dict[str, Any] = {
        "experiment": "veremi_benchmark", "generated_at": datetime.now(UTC).isoformat(),
        "attacks": args.attacks, "categories": {a: CATEGORIES[a] for a in args.attacks},
        "windows": args.windows, "window_seconds": args.window_seconds, "target_fpr": TARGET_FPR,
        "units": [],
    }
    for w in range(args.windows):
        windows = {a: _window(raw[a], w, args.window_seconds) for a in args.attacks}
        prepared = {a: prepare(msgs, a) for a, msgs in windows.items() if len(msgs) >= MIN_WINDOW_MESSAGES}
        for target in prepared:
            if not prepared[target]["test_labels"].any():
                continue
            scores = evaluate_window(prepared, target, seed=args.seed + w)
            report["units"].append({
                "window": w, "attack": target, "test_messages": len(prepared[target]["test_labels"]),
                "attack_share": float(prepared[target]["test_labels"].mean()), "scores": scores,
            })
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
