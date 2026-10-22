from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from smart_city_security.digital_twin.kalman_twin import TWIN_KINDS
from smart_city_security.evaluation import paired_compare
from smart_city_security.integration.real_data_experiment import (
    DEFAULT_ATTACKS,
    DEFAULT_MODELS,
    DEFAULT_SEEDS,
    Dataset,
    evaluate_once,
    fit_detector,
    load_dataset,
)
from smart_city_security.ml_detection import AnomalyDetector
from smart_city_security.schemas import Telemetry

POLICIES = ("never", "always", "avds", "avds_novel", "oracle")
METHODS = ("avds", "avds_novel")


def _split(
    stream: Sequence[Telemetry], inner_fraction: float, train_fraction: float
) -> tuple[list[Telemetry], list[Telemetry], list[Telemetry], list[Telemetry]]:
    if not 0.0 < inner_fraction < train_fraction < 1.0:
        raise ValueError("need 0 < inner_fraction < train_fraction < 1")
    inner_cut = int(len(stream) * inner_fraction)
    cut = int(len(stream) * train_fraction)
    return (
        list(stream[:inner_cut]),
        list(stream[inner_cut:cut]),
        list(stream[:cut]),
        list(stream[cut:]),
    )


def worst_case(scores: dict[str, float]) -> float:
    return min(scores["static"], scores["adaptive"])


def select_divergence(
    validation: dict[bool, dict[str, dict[str, float]]], attacks: Sequence[str]
) -> bool:
    if not attacks:
        raise ValueError("selection needs at least one validation attack")
    off = fmean(worst_case(validation[False][a]) for a in attacks)
    on = fmean(worst_case(validation[True][a]) for a in attacks)
    return on > off


def _condition(
    train: Sequence[Telemetry],
    test: Sequence[Telemetry],
    *,
    model: str,
    include_divergence: bool,
    attack_name: str,
    seed: int,
    strength: float,
    contamination: float,
    calibrate: bool,
    fitted: tuple[AnomalyDetector, float] | None = None,
    twin_kind: str = "window",
    target_fpr: float = 0.05,
    attack_ratio: float = 0.15,
    attacker_steps: int = 8,
    divergence_transform: str = "none",
    feature_history: int = 1,
    attack_mode: str = "inject",
    attacker_search: str = "gradient",
) -> dict[str, float]:
    if fitted is None:
        fitted = fit_detector(train, model=model, include_divergence=include_divergence,
                              contamination=contamination, seed=seed, calibrate=calibrate,
                              twin_kind=twin_kind, target_fpr=target_fpr,
                              divergence_transform=divergence_transform, feature_history=feature_history)
    return {
        mode: evaluate_once(
            train, test,
            model=model, include_divergence=include_divergence,
            contamination=contamination, attack_name=attack_name,
            strength=strength, adaptive=mode == "adaptive", seed=seed,
            calibrate=calibrate, fitted=fitted, twin_kind=twin_kind,
            target_fpr=target_fpr, attack_ratio=attack_ratio, attacker_steps=attacker_steps,
            divergence_transform=divergence_transform, feature_history=feature_history,
            attack_mode=attack_mode, attacker_search=attacker_search,
        )["f1"]
        for mode in ("static", "adaptive")
    }


def run_unit(
    stream: Sequence[Telemetry],
    *,
    model: str,
    seed: int,
    attacks: Sequence[str] = DEFAULT_ATTACKS,
    strength: float = 0.6,
    contamination: float = 0.05,
    calibrate: bool = True,
    inner_fraction: float = 0.45,
    train_fraction: float = 0.6,
    twin_kind: str = "window",
    target_fpr: float = 0.05,
    attack_ratio: float = 0.15,
    attacker_steps: int = 8,
    divergence_transform: str = "none",
    feature_history: int = 1,
    attack_mode: str = "inject",
    attacker_search: str = "gradient",
) -> dict[str, Any]:
    inner, validation_stream, train, test = _split(stream, inner_fraction, train_fraction)
    common: dict[str, Any] = {
        "model": model, "seed": seed, "strength": strength,
        "contamination": contamination, "calibrate": calibrate, "twin_kind": twin_kind,
        "target_fpr": target_fpr, "attack_ratio": attack_ratio, "attacker_steps": attacker_steps,
        "divergence_transform": divergence_transform, "feature_history": feature_history,
        "attack_mode": attack_mode, "attacker_search": attacker_search,
    }
    def fit(stream: Sequence[Telemetry], div: bool) -> tuple[AnomalyDetector, float]:
        return fit_detector(stream, model=model, include_divergence=div,
                            contamination=contamination, seed=seed, calibrate=calibrate,
                            twin_kind=twin_kind, target_fpr=target_fpr,
                            divergence_transform=divergence_transform,
                            feature_history=feature_history)

    validation = {}
    tested = {}
    for div in (False, True):
        on_inner, on_train = fit(inner, div), fit(train, div)
        validation[div] = {a: _condition(inner, validation_stream, include_divergence=div,
                                         attack_name=a, fitted=on_inner, **common) for a in attacks}
        tested[div] = {a: _condition(train, test, include_divergence=div,
                                     attack_name=a, fitted=on_train, **common) for a in attacks}
    known = select_divergence(validation, attacks)
    per_attack: dict[str, Any] = {}
    for attack in attacks:
        others = [a for a in attacks if a != attack] or [attack]
        oracle = worst_case(tested[True][attack]) > worst_case(tested[False][attack])
        choices = {
            "never": False,
            "always": True,
            "avds": known,
            "avds_novel": select_divergence(validation, others),
            "oracle": oracle,
        }
        per_attack[attack] = {
            "choices": choices,
            "test": {
                policy: {**tested[choice][attack], "worst_case": worst_case(tested[choice][attack])}
                for policy, choice in choices.items()
            },
            "validation_attacks": others,
        }
    return {
        "model": model,
        "seed": seed,
        "validation": {str(div).lower(): scores for div, scores in validation.items()},
        "attacks": per_attack,
        "sizes": {"inner_train": len(inner), "validation": len(validation_stream),
                  "train": len(train), "test": len(test)},
    }


def _run_unit_task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def summarise(
    units: Sequence[dict[str, Any]], *, dataset: str, models: Sequence[str], attacks: Sequence[str]
) -> dict[str, Any]:
    conditions: dict[str, Any] = {}
    pooled: dict[str, list[float]] = {p: [] for p in POLICIES}
    for model in models:
        runs = sorted((u for u in units if u["model"] == model), key=lambda u: u["seed"])
        for attack in attacks:
            rows = [u["attacks"][attack] for u in runs]
            worst = {p: [r["test"][p]["worst_case"] for r in rows] for p in POLICIES}
            for p in POLICIES:
                pooled[p].extend(worst[p])
            conditions[f"{dataset}/{model}/{attack}"] = {
                "n_seeds": len(rows),
                "mean": {
                    p: {m: fmean(r["test"][p][m] for r in rows)
                        for m in ("static", "adaptive", "worst_case")}
                    for p in POLICIES
                },
                "keeps_divergence_rate": {
                    p: fmean(float(r["choices"][p]) for r in rows) for p in (*METHODS, "oracle")
                },
                "agrees_with_oracle_rate": {
                    p: fmean(float(r["choices"][p] == r["choices"]["oracle"]) for r in rows)
                    for p in METHODS
                },
                "regret": {
                    p: fmean(o - a for o, a in zip(worst["oracle"], worst[p], strict=True))
                    for p in METHODS
                },
                "significance": {
                    f"{p}_vs_{base}": paired_compare(worst[base], worst[p], metric="worst_case_f1").to_dict()
                    for p in METHODS for base in ("never", "always")
                },
            }
    return {
        "conditions": conditions,
        "pooled": {
            "n_units": len(pooled["avds"]),
            "mean_worst_case_f1": {p: fmean(v) for p, v in pooled.items()},
            "significance": {
                f"{p}_vs_{base}": paired_compare(pooled[base], pooled[p], metric="worst_case_f1").to_dict()
                for p in METHODS for base in ("never", "always")
            },
            "note": "pooled over (model, attack, seed) units, which are not independent; "
                    "per-condition tests are the primary evidence",
        },
    }


def run_experiment(
    datasets: Sequence[Dataset],
    *,
    models: Sequence[str] = DEFAULT_MODELS,
    attacks: Sequence[str] = DEFAULT_ATTACKS,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    strength: float = 0.6,
    contamination: float = 0.05,
    calibrate: bool = True,
    inner_fraction: float = 0.45,
    train_fraction: float = 0.6,
    jobs: int = 1,
    twin_kind: str = "window",
    target_fpr: float = 0.05,
    attack_ratio: float = 0.15,
    attacker_steps: int = 8,
    divergence_transform: str = "none",
    feature_history: int = 1,
    attack_mode: str = "inject",
    attacker_search: str = "gradient",
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "experiment": "avds_divergence_selection",
        "generated_at": datetime.now(UTC).isoformat(),
        "seeds": list(seeds),
        "models": list(models),
        "attacks": list(attacks),
        "strength": strength,
        "calibrated": calibrate,
        "inner_fraction": inner_fraction,
        "train_fraction": train_fraction,
        "twin": twin_kind,
        "target_fpr": target_fpr,
        "attack_ratio": attack_ratio,
        "attacker_steps": attacker_steps,
        "divergence_transform": divergence_transform,
        "feature_history": feature_history,
        "attack_mode": attack_mode,
        "attacker_search": attacker_search,
        "selection_rule": "keep divergence iff mean worst-case (min of static, adaptive) "
                          "validation F1 over the rehearsed attacks is strictly higher; "
                          "avds rehearses all attacks, avds_novel all but the tested one",
        "datasets": {},
    }
    for dataset in datasets:
        kwargs: list[dict[str, Any]] = [
            {"model": model, "seed": seed, "attacks": list(attacks), "strength": strength,
             "contamination": contamination, "calibrate": calibrate,
             "inner_fraction": inner_fraction, "train_fraction": train_fraction,
             "twin_kind": twin_kind, "target_fpr": target_fpr, "attack_ratio": attack_ratio,
             "attacker_steps": attacker_steps, "divergence_transform": divergence_transform,
             "feature_history": feature_history, "attack_mode": attack_mode,
             "attacker_search": attacker_search}
            for model in models for seed in seeds
        ]
        if jobs > 1:
            with ProcessPoolExecutor(max_workers=jobs) as pool:
                units = list(pool.map(_run_unit_task, [(dataset.telemetry, k) for k in kwargs]))
        else:
            units = [run_unit(dataset.telemetry, **k) for k in kwargs]
        report["datasets"][dataset.name] = {
            "units": units,
            "summary": summarise(units, dataset=dataset.name, models=models, attacks=attacks),
        }
    return report


def _parse_dataset(spec: str, max_messages: int) -> Dataset:
    name, _, path = spec.partition("=")
    dataset = load_dataset(name, path=path or None, max_messages=max_messages)
    if path:
        return Dataset(f"{name}:{Path(path).stem}", dataset.telemetry)
    return dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", default=["sumo"],
                        help="dataset names, or name=path (e.g. pneuma=datasets/pneuma/session.csv)")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--attacks", nargs="+", default=list(DEFAULT_ATTACKS))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--strength", type=float, default=0.6)
    parser.add_argument("--max-messages", type=int, default=40_000)
    parser.add_argument("--inner-fraction", type=float, default=0.45)
    parser.add_argument("--no-calibrate", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--twin", choices=TWIN_KINDS, default="window",
                        help="digital twin used for the divergence features")
    parser.add_argument("--target-fpr", type=float, default=0.05,
                        help="benign false-positive budget used to calibrate every detector")
    parser.add_argument("--attack-ratio", type=float, default=0.15,
                        help="fraction of messages attacked in rehearsal and test")
    parser.add_argument("--attacker-steps", type=int, default=8,
                        help="gradient-search budget of the adaptive adversary")
    parser.add_argument("--divergence-transform", choices=("none", "log1p"), default="none",
                        help="compress the divergence features' heavy benign tail")
    parser.add_argument("--feature-history", type=int, default=1,
                        help="per-device message window fed to the detector (1 = current only)")
    parser.add_argument("--attack-mode", choices=("inject", "replace"), default="inject",
                        help="add malicious copies next to genuine messages, or replace them")
    parser.add_argument("--attacker-search", choices=("gradient", "grid"), default="gradient",
                        help="adaptive adversary: finite-difference gradient or gradient-free grid")
    parser.add_argument("--output", default="results/ml/avds.json")
    args = parser.parse_args(argv)

    datasets = [_parse_dataset(spec, args.max_messages) for spec in args.datasets]
    report = run_experiment(
        datasets, models=args.models, attacks=args.attacks, seeds=args.seeds,
        strength=args.strength, calibrate=not args.no_calibrate,
        inner_fraction=args.inner_fraction, jobs=args.jobs, twin_kind=args.twin,
        target_fpr=args.target_fpr, attack_ratio=args.attack_ratio, attacker_steps=args.attacker_steps,
        divergence_transform=args.divergence_transform, feature_history=args.feature_history,
        attack_mode=args.attack_mode, attacker_search=args.attacker_search,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
