from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

ALLOWED_TRANSITIONS = {
    "candidate": {"approved", "retired"},
    "approved": {"shadow", "retired"},
    "shadow": {"canary", "retired"},
    "canary": {"production", "retired"},
    "production": {"retired"},
    "retired": set(),
}


@dataclass(frozen=True, slots=True)
class ModelRecord:
    name: str
    version: str
    artifact: str
    artifact_sha256: str
    feature_version: str
    dataset_version: str
    status: str = "candidate"
    created_at: str = ""
    metrics: dict[str, float] | None = None


class ModelRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: dict[tuple[str, str], ModelRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for item in json.loads(self.path.read_text(encoding="utf-8")):
            record = ModelRecord(**item)
            self.records[(record.name, record.version)] = record

    def _save(self) -> None:
        payload = [
            {
                "name": r.name,
                "version": r.version,
                "artifact": r.artifact,
                "artifact_sha256": r.artifact_sha256,
                "feature_version": r.feature_version,
                "dataset_version": r.dataset_version,
                "status": r.status,
                "created_at": r.created_at,
                "metrics": r.metrics,
            }
            for r in self.records.values()
        ]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def register(
        self,
        name: str,
        version: str,
        artifact: str | Path,
        feature_version: str,
        dataset_version: str,
        metrics: dict[str, float] | None = None,
    ) -> ModelRecord:
        key = (name, version)
        if key in self.records:
            raise ValueError(f"Model already registered: {name}:{version}")
        artifact_path = Path(artifact)
        digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        record = ModelRecord(
            name,
            version,
            str(artifact_path),
            digest,
            feature_version,
            dataset_version,
            created_at=datetime.now(UTC).isoformat(),
            metrics=metrics,
        )
        self.records[key] = record
        self._save()
        return record

    def transition(self, name: str, version: str, status: str) -> ModelRecord:
        key = (name, version)
        current = self.records[key]
        if status not in ALLOWED_TRANSITIONS[current.status]:
            raise ValueError(f"Invalid model transition: {current.status} -> {status}")
        updated = replace(current, status=status)
        self.records[key] = updated
        self._save()
        return updated

    def production(self, name: str) -> ModelRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.name == name and record.status == "production"
            ),
            None,
        )
