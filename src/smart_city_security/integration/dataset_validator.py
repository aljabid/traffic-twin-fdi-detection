from __future__ import annotations

import argparse

from smart_city_security.digital_twin.external_dataset import (
    write_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--output", default="results/system/real-dataset-validation.json"
    )
    args = parser.parse_args(argv)
    print(write_validation_report(args.dataset, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
