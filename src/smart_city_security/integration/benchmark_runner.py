from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from smart_city_security.config import load_config
from smart_city_security.evaluation.benchmark import benchmark_callable
from smart_city_security.integration.pipeline import SecurityPipeline


def run_benchmark(config_path: str, repeats: int = 3) -> dict[str, Any]:
    config = load_config(config_path)
    result = benchmark_callable(lambda: SecurityPipeline(config).run().to_dict(), repeats)
    result["config_path"] = config_path
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/test.yaml")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", default="results/system/benchmark.json")
    args = parser.parse_args(argv)

    report = run_benchmark(args.config, args.repeats)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
