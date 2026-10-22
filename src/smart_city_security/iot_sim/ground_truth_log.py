from __future__ import annotations

import csv
from pathlib import Path

from smart_city_security.schemas import GroundTruth


def write_ground_truth(labels: dict[str, GroundTruth], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("message_id", "label", "attack_type"))
        writer.writeheader()
        for item in labels.values():
            writer.writerow(
                {
                    "message_id": item.message_id,
                    "label": item.label,
                    "attack_type": item.attack_type or "",
                }
            )
    return path


def read_ground_truth(path: str | Path) -> dict[str, GroundTruth]:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return {
            row["message_id"]: GroundTruth(
                row["message_id"], row["label"], row["attack_type"] or None
            )
            for row in csv.DictReader(stream)
        }
