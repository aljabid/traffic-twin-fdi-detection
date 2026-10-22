from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from smart_city_security.integration.avds_experiment import (
    _parse_dataset,
    _split,
    select_divergence,
)
from smart_city_security.integration.real_data_experiment import (
    DEFAULT_MODELS,
    evaluate_once,
    fit_detector,
)
from smart_city_security.iot_sim.adversary import ATTACKS, REHEARSAL_ATTACKS, AdversarialCampaign
from smart_city_security.schemas import Telemetry


def poison(validation: Sequence[Telemetry], attack: str, rate: float, seed: int,
           strength: float = 0.6) -> list[Telemetry]:
    campaign = AdversarialCampaign(seed + 10_000).run(
        list(validation), attack=ATTACKS[attack], attack_ratio=rate, strength=strength
    )
    return campaign.messages


def run_unit(stream: Sequence[Telemetry], *, model: str, seed: int, attacks: Sequence[str],
             rates: Sequence[float], strength: float = 0.6, contamination: float = 0.05) -> dict[str, Any]:
    inner, validation, _, _ = _split(stream, 0.45, 0.6)
    fits = {div: fit_detector(inner, model=model, include_divergence=div, contamination=contamination,
                              seed=seed, calibrate=True) for div in (False, True)}

    def rehearse(val_stream: Sequence[Telemetry]) -> dict[bool, dict[str, dict[str, float]]]:
        return {
            div: {a: {mode: evaluate_once(inner, val_stream, model=model, include_divergence=div,
                                          contamination=contamination, attack_name=a, strength=strength,
                                          adaptive=mode == "adaptive", seed=seed, calibrate=True,
                                          fitted=fits[div])["f1"]
                      for mode in ("static", "adaptive")}
                  for a in attacks}
            for div in (False, True)
        }

    clean_choice = select_divergence(rehearse(validation), attacks)
    poisoned: dict[str, dict[str, bool]] = {}
    for rate in rates:
        poisoned[str(rate)] = {
            p: select_divergence(rehearse(poison(validation, p, rate, seed, strength)), attacks)
            for p in attacks
        }
    return {"model": model, "seed": seed, "clean_choice": clean_choice, "poisoned_choice": poisoned}


def _task(args: tuple[list[Telemetry], dict[str, Any]]) -> dict[str, Any]:
    stream, kwargs = args
    return run_unit(stream, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", default=["sumo"])
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--attacks", nargs="+", default=list(REHEARSAL_ATTACKS))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(4, 14)))
    parser.add_argument("--rates", type=float, nargs="+", default=[0.10])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", default="results/ml/avds-poisoning.json")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"experiment": "avds_validation_poisoning",
                              "generated_at": datetime.now(UTC).isoformat(),
                              "seeds": args.seeds, "attacks": args.attacks, "rates": args.rates, "datasets": {}}
    for spec in args.datasets:
        dataset = _parse_dataset(spec, 40_000)
        kwargs = [{"model": m, "seed": s, "attacks": args.attacks, "rates": args.rates}
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
