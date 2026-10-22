from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from .validation import prediction_metrics


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    intersection_id: str
    context: str
    timestamp: float
    predicted: float
    observed: float
    lower_bound: float
    upper_bound: float


def calibrate_by_location(
    observations: list[CalibrationObservation], *, minimum_per_location: int = 10
) -> dict[str, Any]:
    if not observations:
        raise ValueError("observations cannot be empty")
    grouped: dict[str, list[CalibrationObservation]] = {}
    for item in observations:
        grouped.setdefault(item.intersection_id, []).append(item)
    locations = {}
    for location, values in grouped.items():
        if len(values) < minimum_per_location:
            locations[location] = {
                "passed": False,
                "reason": "insufficient observations",
                "n": len(values),
            }
            continue
        metrics = prediction_metrics(
            [item.predicted for item in values],
            [item.observed for item in values],
        )
        coverage = fmean(
            item.lower_bound <= item.observed <= item.upper_bound for item in values
        )
        context_bias = {}
        for context in sorted({item.context for item in values}):
            subset = [item for item in values if item.context == context]
            context_bias[context] = prediction_metrics(
                [item.predicted for item in subset],
                [item.observed for item in subset],
            )["bias"]
        locations[location] = {
            **metrics,
            "interval_coverage": coverage,
            "context_bias": context_bias,
            "passed": True,
        }
    return {
        "passed": all(value["passed"] for value in locations.values()),
        "locations": locations,
        "location_count": len(locations),
    }


def write_calibration_report(
    observations: list[CalibrationObservation],
    output: str | Path,
    *,
    source_path: str | Path | None = None,
    model_version: str,
) -> Path:
    report = calibrate_by_location(observations)
    report.update(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "model_version": model_version,
            "source_sha256": (
                hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
                if source_path
                else None
            ),
        }
    )
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return target
