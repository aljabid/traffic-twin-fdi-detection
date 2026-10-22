from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class DatasetPartition:
    name: str
    locations: tuple[str, ...]
    start_timestamp: float
    end_timestamp: float
    records: int

    def __post_init__(self) -> None:
        if self.name not in {"train", "validation", "test"}:
            raise ValueError("Invalid partition name")
        if self.records < 1 or self.end_timestamp < self.start_timestamp:
            raise ValueError("Invalid partition bounds")


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    version: str
    source_sha256: str
    feature_version: str
    label_policy: str
    partitions: tuple[DatasetPartition, ...]

    def validate_leakage(self) -> None:
        names = {partition.name for partition in self.partitions}
        if names != {"train", "validation", "test"}:
            raise ValueError("Train, validation and test partitions are required")
        by_name = {partition.name: partition for partition in self.partitions}
        if not (
            by_name["train"].end_timestamp
            < by_name["validation"].start_timestamp
            <= by_name["validation"].end_timestamp
            < by_name["test"].start_timestamp
        ):
            raise ValueError("Partitions must be chronologically separated")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: str | Path) -> Path:
        self.validate_leakage()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target


def sha256_files(paths: Iterable[str | Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(item) for item in paths):
        digest.update(str(path).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()
