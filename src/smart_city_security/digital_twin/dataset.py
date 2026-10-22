from __future__ import annotations

import csv
from pathlib import Path

from smart_city_security.schemas import Telemetry

REQUIRED = {"device_id","timestamp","position","speed","intersection_id","occupancy","signal_state","sequence_number"}
def load_telemetry_csv(path: str | Path) -> list[Telemetry]:
    with Path(path).open(newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames): raise ValueError(f"CSV must contain {sorted(REQUIRED)}")
        rows=[]
        for row in reader:
            rows.append(Telemetry.create(row["device_id"],float(row["position"]),float(row["speed"]),row["intersection_id"],float(row["occupancy"]),row["signal_state"],int(row["sequence_number"]),timestamp=float(row["timestamp"]),message_id=row.get("message_id") or None,device_type=row.get("device_type","vehicle")))
        return rows

def validate_telemetry(messages: list[Telemetry]) -> list[str]:
    errors=[]
    for m in messages:
        if not 0 <= m.occupancy <= 1: errors.append(f"{m.message_id}: occupancy")
        if m.speed < 0: errors.append(f"{m.message_id}: speed")
        if m.sequence_number < 0: errors.append(f"{m.message_id}: sequence")
    return errors
