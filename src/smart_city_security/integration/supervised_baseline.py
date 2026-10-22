from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.integration.avds_experiment import _parse_dataset, _split
from smart_city_security.integration.real_data_experiment import _train_features, evaluate_once
from smart_city_security.iot_sim.adversary import ATTACKS, REHEARSAL_ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import FeatureBuilder
from smart_city_security.schemas import Telemetry

TARGET_FPR = 0.05


class SupervisedDetector:

    name = "supervised_rf"

    def __init__(self, benign: np.ndarray, attacks: np.ndarray, seed: int,
                 target_fpr: float = TARGET_FPR) -> None:
        x = np.vstack([benign, attacks])
        y = np.concatenate([np.zeros(len(benign)), np.ones(len(attacks))])
        self.model = RandomForestClassifier(
            n_estimators=200, min_samples_leaf=2, class_weight="balanced",
            oob_score=True, random_state=seed, n_jobs=1,
        ).fit(x, y)
        oob_benign = self.model.oob_decision_function_[: len(benign), 1]
        self.threshold = float(np.quantile(np.nan_to_num(oob_benign), 1.0 - target_fpr))

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        scores = self.model.predict_proba(features)[:, 1]
        return scores > self.threshold, scores


def _attack_features(inner: Sequence[Telemetry], validation: Sequence[Telemetry], attack: str,
                     seed: int, strength: float) -> np.ndarray:
    campaign = AdversarialCampaign(seed + 30_000).run(
        list(validation), attack=ATTACKS[attack], attack_ratio=0.15, strength=strength, mode="replace",
    )
    twin, builder = TrafficDigitalTwin(8), FeatureBuilder(True)
    for m in inner:
        twin.observe(m)
    rows = [builder.build(m, twin.observe(m)).values for m in campaign.messages]
    keep = [campaign.labels[m.message_id].label == "attack" for m in campaign.messages]
    return np.vstack(rows)[np.asarray(keep)]


def run_unit(stream: Sequence[Telemetry], *, seed: int, attacks: Sequence[str],
             strength: float = 0.6, attacker_search: str = "gradient") -> dict[str, Any]:
    inner, validation, train, test = _split(stream, 0.45, 0.6)
    benign = _train_features(inner, twin_window=8, include_divergence=True)
    attack_rows = {a: _attack_features(inner, validation, a, seed, strength) for a in attacks}

    def evaluate(detector: SupervisedDetector, attack: str) -> dict[str, float]:
        f1 = {mode: evaluate_once(train, test, model="supervised_rf", include_divergence=True,
                                  contamination=TARGET_FPR, attack_name=attack, strength=strength,
                                  adaptive=mode == "adaptive", seed=seed, calibrate=True,
                                  fitted=(detector, TARGET_FPR), attack_mode="replace",
                                  attacker_search=attacker_search)["f1"]
              for mode in ("static", "adaptive")}
        return {**f1, "worst_case": min(f1.values())}

    known = SupervisedDetector(benign, np.vstack([attack_rows[a] for a in attacks]), seed)
    out: dict[str, Any] = {"seed": seed, "known": {}, "unseen": {}}
    for attack in attacks:
        out["known"][attack] = evaluate(known, attack)
        others = [a for a in attacks if a != attack]
        held_out = SupervisedDetector(benign, np.vstack([attack_rows[a] for a in others]), seed)
        out["unseen"][attack] = evaluate(held_out, attack)
    return out


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--attacks", nargs="+", default=list(REHEARSAL_ATTACKS))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(4, 14)))
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--attacker-search", choices=("gradient", "grid"), default="gradient")
    parser.add_argument("--output", default="results/ml/supervised-baseline.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": "supervised_baseline", "generated_at": datetime.now(UTC).isoformat(),
                              "seeds": args.seeds, "attacks": args.attacks, "attack_mode": "replace",
                              "attacker_search": args.attacker_search,
                              "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"seed": s, "attacks": args.attacks, "attacker_search": args.attacker_search}
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
