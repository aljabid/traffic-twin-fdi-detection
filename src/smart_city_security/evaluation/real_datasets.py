from __future__ import annotations

import csv
import math
import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from smart_city_security.schemas import Telemetry

FT_TO_M = 0.3048
FT_PER_S_TO_KMH = 1.09728
_MAX_PLAUSIBLE_KMH = 89.0

_NGSIM_DEVICE_TYPE = {"1": "vehicle", "2": "vehicle", "3": "bus"}
_PNEUMA_DEVICE_TYPE = {
    "Car": "vehicle",
    "Taxi": "vehicle",
    "Motorcycle": "vehicle",
    "Bus": "bus",
    "Medium Vehicle": "vehicle",
    "Heavy Vehicle": "bus",
}


def data_root() -> Path:
    return Path(os.environ.get("SCS_DATA_DIR", "datasets"))


def occupancy_from_headway(space_headway_m: float, *, reference_m: float = 36.0) -> float:
    if space_headway_m <= 0.0:
        return 0.05
    return max(0.0, min(1.0, 1.0 - space_headway_m / reference_m))


def _clamp_speed(kmh: float) -> float:
    return max(0.0, min(_MAX_PLAUSIBLE_KMH, kmh))


def ngsim_rows_to_telemetry(
    rows: Iterable[dict[str, str]],
    *,
    downsample: int = 10,
    locations: tuple[str, ...] = ("lankershim", "peachtree"),
) -> Iterator[Telemetry]:
    sequence: dict[str, int] = {}
    for row in rows:
        if row["location"] not in locations:
            continue
        if int(row["frame_id"]) % downsample != 0:
            continue
        device_id = f"ngsim-{row['location']}-{row['vehicle_id']}"
        sequence[device_id] = sequence.get(device_id, 0) + 1
        seq = sequence[device_id]
        headway_m = float(row["space_headway"]) * FT_TO_M
        int_id = row["int_id"] if row["int_id"] not in ("0", "", None) else f"sec{row['section_id']}"
        yield Telemetry(
            device_id=device_id,
            timestamp=float(row["global_time"]) / 1000.0,
            position=round(float(row["local_y"]) * FT_TO_M, 4),
            speed=round(_clamp_speed(float(row["v_vel"]) * FT_PER_S_TO_KMH), 4),
            intersection_id=f"{row['location']}-{int_id}",
            occupancy=round(occupancy_from_headway(headway_m), 4),
            signal_state="unknown",
            sequence_number=seq,
            message_id=f"{device_id}-{seq:06d}",
            device_type=_NGSIM_DEVICE_TYPE.get(row["v_class"], "vehicle"),
        )


def read_ngsim_csv(path: str | Path, **kwargs: object) -> Iterator[Telemetry]:
    with open(path, newline="", encoding="utf-8") as handle:
        yield from ngsim_rows_to_telemetry(csv.DictReader(handle), **kwargs)


def _equirect_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    r = 6_371_000.0
    x = math.radians(lon - lon0) * r * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * r
    return x, y


def occupancy_from_speed(speed_kmh: float, *, free_flow_kmh: float = 50.0) -> float:
    return max(0.0, min(1.0, 1.0 - speed_kmh / free_flow_kmh))


def pneuma_lines_to_telemetry(
    lines: Iterable[str],
    *,
    downsample: int = 25,
    grid_m: float = 80.0,
) -> Iterator[Telemetry]:
    origin: tuple[float, float] | None = None
    for raw in lines:
        parts = [p.strip() for p in raw.split(";") if p.strip() != ""]
        if len(parts) < 10 or not parts[0].isdigit():
            continue
        track_id, vtype = parts[0], parts[1]
        samples = parts[4:]
        step = 6 * downsample
        for seq, i in enumerate(range(0, len(samples) - 5, step), start=1):
            lat, lon, speed_kmh = float(samples[i]), float(samples[i + 1]), float(samples[i + 2])
            timestamp = float(samples[i + 5])
            if origin is None:
                origin = (lat, lon)
            x, y = _equirect_xy(lat, lon, origin[0], origin[1])
            device_id = f"pneuma-{track_id}"
            yield Telemetry(
                device_id=device_id,
                timestamp=round(timestamp, 3),
                position=round(math.hypot(x, y) % 1000.0, 4),
                speed=round(_clamp_speed(speed_kmh), 4),
                intersection_id=f"cell-{int(x // grid_m)}-{int(y // grid_m)}",
                occupancy=round(occupancy_from_speed(speed_kmh), 4),
                signal_state="unknown",
                sequence_number=seq,
                message_id=f"{device_id}-{seq:06d}",
                device_type=_PNEUMA_DEVICE_TYPE.get(vtype, "vehicle"),
            )


def read_pneuma_csv(path: str | Path, **kwargs: object) -> Iterator[Telemetry]:
    with open(path, encoding="utf-8") as handle:
        yield from pneuma_lines_to_telemetry(handle, **kwargs)


def sumo_fcd_rows_to_telemetry(
    rows: Iterable[dict[str, str]],
    *,
    downsample: int = 1,
) -> Iterator[Telemetry]:
    sequence: dict[str, int] = {}
    for idx, row in enumerate(rows):
        if idx % downsample != 0:
            continue
        device_id = f"sumo-{row['id']}"
        sequence[device_id] = sequence.get(device_id, 0) + 1
        seq = sequence[device_id]
        yield Telemetry(
            device_id=device_id,
            timestamp=float(row["time"]),
            position=round(float(row["y"]), 4),
            speed=round(_clamp_speed(float(row["speed"]) * 3.6), 4),
            intersection_id=str(row.get("edge", "sumo-net")).split("_")[0].lstrip("-:"),
            occupancy=round(float(row.get("occupancy", 0.2)), 4),
            signal_state=str(row.get("signal_state", "unknown")),
            sequence_number=seq,
            message_id=f"{device_id}-{seq:06d}",
            device_type=str(row.get("type", "vehicle")),
        )
