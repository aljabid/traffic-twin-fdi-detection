from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from smart_city_security.evaluation.crypto_metrics import benchmark_backend
from smart_city_security.pqc import BackendUnavailableError, PQCBackend


def validate_native_pqc(repetitions: int = 20) -> dict[str, Any]:
    try:
        metrics = benchmark_backend(PQCBackend(), repetitions)
        return {
            "passed": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "metrics": metrics.to_dict(),
        }
    except BackendUnavailableError as exc:
        return {
            "passed": False,
            "generated_at": datetime.now(UTC).isoformat(),
            "reason": str(exc),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument(
        "--output", default="results/crypto/pqc-native-validation.json"
    )
    args = parser.parse_args(argv)
    report = validate_native_pqc(args.repetitions)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
