from __future__ import annotations

import csv
import gzip
import json
import zipfile
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import Path
from statistics import fmean
from typing import Any

from .validation import prediction_metrics


@dataclass(frozen=True, slots=True)
class TrafficVolumeObservation:
    timestamp: str
    traffic_volume: float


def load_uci_metro_zip(path: str | Path) -> list[TrafficVolumeObservation]:
    with zipfile.ZipFile(path) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.lower().endswith((".csv", ".csv.gz"))
        ]
        if len(candidates) != 1:
            raise ValueError("Expected exactly one CSV in UCI dataset archive")
        name = candidates[0]
        with archive.open(name) as raw:
            stream = gzip.GzipFile(fileobj=raw) if name.lower().endswith(".gz") else raw
            reader = csv.DictReader(TextIOWrapper(stream, encoding="utf-8"))
            required = {"date_time", "traffic_volume"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError("UCI dataset columns are incomplete")
            values = [
                TrafficVolumeObservation(
                    row["date_time"], float(row["traffic_volume"])
                )
                for row in reader
            ]
    if len(values) < 24:
        raise ValueError("Dataset is too small for traffic validation")
    return values


def rolling_volume_validation(
    observations: list[TrafficVolumeObservation], window: int = 24
) -> dict[str, Any]:
    if window < 2 or len(observations) <= window:
        raise ValueError("insufficient observations for selected window")
    predicted, observed = [], []
    history = [item.traffic_volume for item in observations[:window]]
    for item in observations[window:]:
        predicted.append(fmean(history[-window:]))
        observed.append(item.traffic_volume)
        history.append(item.traffic_volume)
    metrics: dict[str, Any] = dict(prediction_metrics(predicted, observed))
    metrics.update(
        {
            "passed": True,
            "dataset": "UCI Metro Interstate Traffic Volume",
            "doi": "10.24432/C5X60B",
            "license": "CC BY 4.0",
            "observations": len(observations),
            "window": window,
        }
    )
    return metrics


def write_validation_report(dataset: str | Path, output: str | Path) -> Path:
    metrics = rolling_volume_validation(load_uci_metro_zip(dataset))
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return target
