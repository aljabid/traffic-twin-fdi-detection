from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from smart_city_security.config import load_config
from smart_city_security.evaluation.crypto_metrics import benchmark_backend
from smart_city_security.evaluation.report_builder import write_json_report
from smart_city_security.integration.pipeline import SecurityPipeline
from smart_city_security.pqc import BackendUnavailableError, ClassicalBackend, PQCBackend


def _run_crypto(config: dict[str, Any]) -> dict[str, Any]:
    repetitions = int(config["experiment"].get("repetitions", 20))
    results = [benchmark_backend(ClassicalBackend(), repetitions).to_dict()]
    try:
        results.append(benchmark_backend(PQCBackend(), repetitions).to_dict())
    except BackendUnavailableError as exc:
        results.append({"algorithm": "PQC", "available": False, "reason": str(exc)})
    return {"experiment": "pqc_vs_classical", "results": results}


def _run_ablation(config: dict[str, Any]) -> dict[str, Any]:
    results = {}
    for include in (False, True):
        current = deepcopy(config)
        current["ml"]["include_divergence"] = include
        results[f"include_divergence_{str(include).lower()}"] = (
            SecurityPipeline(current).run().to_dict()
        )
    return {"experiment": "divergence_ablation", "results": results}


def _run_secure(config: dict[str, Any]) -> dict[str, Any]:
    results = {}
    for backend in ("none", "classical"):
        current = deepcopy(config)
        current["security"]["backend"] = backend
        results[backend] = SecurityPipeline(current).run().to_dict()
    return {"experiment": "secure_vs_nonsecure", "results": results}


def _run_scalability(config: dict[str, Any]) -> dict[str, Any]:
    results = []
    for devices in config["experiment"]["device_counts"]:
        for preset in config["experiment"]["network_presets"]:
            current = deepcopy(config)
            current["simulation"]["devices"] = devices
            current["network"]["preset"] = preset
            result = SecurityPipeline(current).run()
            results.append(
                {
                    "devices": devices,
                    "preset": preset,
                    "system_metrics": result.system_metrics.to_dict(),
                }
            )
    return {"experiment": "scalability", "results": results}


def run_named_experiment(config: dict[str, Any]) -> dict[str, Any]:
    name = config["experiment"]["name"]
    runners = {
        "pipeline": lambda value: {
            "experiment": "pipeline",
            "results": SecurityPipeline(value).run().to_dict(),
        },
        "pqc_vs_classical": _run_crypto,
        "divergence_ablation": _run_ablation,
        "secure_vs_nonsecure": _run_secure,
        "scalability": _run_scalability,
    }
    try:
        report = runners[name](config)
    except KeyError as exc:
        raise ValueError(f"Unknown experiment: {name}") from exc
    report["generated_at"] = datetime.now(UTC).isoformat()
    report["config"] = config
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Smart City security experiments")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--output")
    arguments = parser.parse_args(argv)
    config = load_config(arguments.config)
    report = run_named_experiment(config)
    if arguments.output:
        output = Path(arguments.output)
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        output = Path(config["experiment"]["output_dir"]) / f"{config['experiment']['name']}-{timestamp}.json"
    write_json_report(report, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
