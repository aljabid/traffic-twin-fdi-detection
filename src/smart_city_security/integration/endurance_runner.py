from __future__ import annotations

import argparse
import json
import tracemalloc
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from smart_city_security.config import load_config
from smart_city_security.integration.pipeline import SecurityPipeline


def run_endurance(
    config_path: str,
    *,
    iterations: int,
    max_p95_ms: float = 100.0,
    min_handled_rate: float = 0.99,
) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    tracemalloc.start()
    started = perf_counter()
    config = load_config(config_path)
    p95_values: list[float] = []
    handled = sent = 0
    for _ in range(iterations):
        result = SecurityPipeline(config).run()
        metrics = result.system_metrics
        p95_values.append(float(metrics.p95_latency_ms))
        sent += int(metrics.sent)
        handled += int(metrics.delivered) + int(metrics.rejected)
    elapsed = perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    handled_rate = handled / max(1, sent)
    worst_p95 = max(p95_values)
    return {
        "passed": worst_p95 <= max_p95_ms and handled_rate >= min_handled_rate,
        "iterations": iterations,
        "sent": sent,
        "handled": handled,
        "handled_rate": handled_rate,
        "mean_p95_latency_ms": mean(p95_values),
        "worst_p95_latency_ms": worst_p95,
        "elapsed_seconds": elapsed,
        "peak_memory_bytes": peak_bytes,
        "targets": {
            "max_p95_latency_ms": max_p95_ms,
            "min_handled_rate": min_handled_rate,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/acceptance.yaml")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", default="results/system/endurance.json")
    args = parser.parse_args(argv)
    report = run_endurance(args.config, iterations=args.iterations)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(target)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
