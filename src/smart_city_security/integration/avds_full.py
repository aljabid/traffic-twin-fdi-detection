from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.integration.avds_experiment import _parse_dataset, _split
from smart_city_security.integration.real_data_experiment import _train_features, evaluate_once
from smart_city_security.integration.supervised_baseline import TARGET_FPR, SupervisedDetector
from smart_city_security.iot_sim.adversary import ATTACKS, REHEARSAL_ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import FeatureBuilder
from smart_city_security.schemas import Telemetry

MODES = ("static", "gradient", "grid")


def _inner_attack_features(inner: Sequence[Telemetry], attack: str, seed: int, strength: float) -> np.ndarray:
    campaign = AdversarialCampaign(seed + 40_000).run(
        list(inner), attack=ATTACKS[attack], attack_ratio=0.15, strength=strength, mode="replace",
    )
    twin, builder = TrafficDigitalTwin(8), FeatureBuilder(True)
    rows = [builder.build(m, twin.observe(m)).values for m in campaign.messages]
    keep = np.asarray([campaign.labels[m.message_id].label == "attack" for m in campaign.messages])
    attacked: np.ndarray = np.vstack(rows)[keep]
    return attacked


def _scores(detector: SupervisedDetector, warm: Sequence[Telemetry], stream: Sequence[Telemetry],
            attack: str, seed: int, strength: float) -> dict[str, float]:
    def f1(adaptive: bool, search: str) -> float:
        return float(evaluate_once(
            warm, stream, model="supervised_rf", include_divergence=True, contamination=TARGET_FPR,
            attack_name=attack, strength=strength, adaptive=adaptive, seed=seed, calibrate=True,
            fitted=(detector, TARGET_FPR), attack_mode="replace", attacker_search=search,
        )["f1"])

    out = {"static": f1(False, "gradient"), "gradient": f1(True, "gradient"), "grid": f1(True, "grid")}
    out["worst_case"] = min(out[m] for m in MODES)
    return out


def run_unit(stream: Sequence[Telemetry], *, seed: int, attacks: Sequence[str],
             strength: float = 0.6, novel_attacks: Sequence[str] = (),
             unseen: bool = True) -> dict[str, Any]:
    inner, validation, train, test = _split(stream, 0.45, 0.6)
    benign = _train_features(inner, twin_window=8, include_divergence=True)
    attack_rows = {a: _inner_attack_features(inner, a, seed, strength) for a in attacks}

    def forest(families: Sequence[str]) -> SupervisedDetector:
        return SupervisedDetector(benign, np.vstack([attack_rows[a] for a in families]), seed)

    known = forest(attacks)
    out: dict[str, Any] = {
        "seed": seed,
        "known": {
            "validation": {a: _scores(known, inner, validation, a, seed, strength) for a in attacks},
            "test": {a: _scores(known, train, test, a, seed, strength) for a in attacks},
        },
        "unseen": {},
        "novel": {a: _scores(known, train, test, a, seed, strength) for a in novel_attacks},
    }
    for held_out in (attacks if unseen else ()):
        others = [a for a in attacks if a != held_out]
        model = forest(others)
        out["unseen"][held_out] = {
            "validation": {a: _scores(model, inner, validation, a, seed, strength) for a in others},
            "test": _scores(model, train, test, held_out, seed, strength),
        }
    return out


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--attacks", nargs="+", default=list(REHEARSAL_ATTACKS))
    parser.add_argument("--seeds", type=int, nargs="+", default=[4, 5, 6, 7, 8])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--novel-attacks", nargs="*", default=[],
                        help="held-out, qualitatively different attack families to test the forest on")
    parser.add_argument("--skip-unseen", action="store_true",
                        help="skip the leave-one-family-out forests (already computed)")
    parser.add_argument("--output", default="results/ml/avds-full-rf.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": "avds_full_supervised_candidate",
                              "generated_at": datetime.now(UTC).isoformat(), "seeds": args.seeds,
                              "attacks": args.attacks, "attack_mode": "replace", "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"seed": s, "attacks": args.attacks, "novel_attacks": args.novel_attacks,
                   "unseen": not args.skip_unseen} for s in args.seeds]
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
