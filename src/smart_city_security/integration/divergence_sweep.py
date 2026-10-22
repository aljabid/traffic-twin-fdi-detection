from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from smart_city_security.config import load_config
from smart_city_security.integration.pipeline import SecurityPipeline

DEFAULT_CONTAMINATION = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)
DEFAULT_SEEDS = (1, 2, 3, 4, 5)
DEFAULT_MODELS = ("isolation_forest", "autoencoder")
_METRICS = ("accuracy", "precision", "recall", "f1", "false_positive_rate")


def _mean_metrics(config: dict[str, Any], seeds: Sequence[int]) -> dict[str, float]:
    runs: list[dict[str, float]] = []
    for seed in seeds:
        current = deepcopy(config)
        current["seed"] = seed
        runs.append(SecurityPipeline(current).run().ml_metrics.to_dict())
    return {key: fmean(run[key] for run in runs) for key in _METRICS}


def sweep(
    config: dict[str, Any],
    *,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    contamination_grid: Sequence[float] = DEFAULT_CONTAMINATION,
    models: Sequence[str] = DEFAULT_MODELS,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for model in models:
        for include_divergence in (False, True):
            grid: list[dict[str, Any]] = []
            for contamination in contamination_grid:
                current = deepcopy(config)
                current["ml"] = {
                    **config["ml"],
                    "model": model,
                    "include_divergence": include_divergence,
                    "contamination": contamination,
                }
                metrics = _mean_metrics(current, seeds)
                grid.append({"contamination": contamination, **metrics})
            best = max(grid, key=lambda row: row["f1"])
            results[f"{model}/divergence={str(include_divergence).lower()}"] = {
                "grid": grid,
                "tuned": best,
            }

    effects: dict[str, Any] = {}
    for model in models:
        without = results[f"{model}/divergence=false"]["tuned"]
        with_ = results[f"{model}/divergence=true"]["tuned"]
        effects[model] = {
            "tuned_contamination_without": without["contamination"],
            "tuned_contamination_with": with_["contamination"],
            "delta_at_tuned": {key: with_[key] - without[key] for key in _METRICS},
            "divergence_helps_f1": with_["f1"] > without["f1"],
        }
    return {
        "experiment": "divergence_ablation_contamination_tuned",
        "seeds": list(seeds),
        "contamination_grid": list(contamination_grid),
        "results": results,
        "effects": effects,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/exp2_divergence_ablation.yaml")
    parser.add_argument("--output", default="results/ml/divergence-sweep.json")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument(
        "--contamination", type=float, nargs="+", default=list(DEFAULT_CONTAMINATION)
    )
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    args = parser.parse_args(argv)

    report = sweep(
        load_config(args.config),
        seeds=args.seeds,
        contamination_grid=args.contamination,
        models=args.models,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
