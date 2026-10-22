from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from smart_city_security.evaluation.real_datasets import _clamp_speed, occupancy_from_headway
from smart_city_security.schemas import Telemetry

NEIGHBOUR_RANGE_M = 100.0


@dataclass(frozen=True, slots=True)
class RawMessage:

    sender: str
    time: float
    x: float
    y: float
    speed_kmh: float
    attack: bool = False


def _nearest_gaps(messages: list[RawMessage]) -> list[float]:
    cell = NEIGHBOUR_RANGE_M
    latest: dict[str, RawMessage] = {}
    grid: dict[tuple[int, int], set[str]] = {}
    where: dict[str, tuple[int, int]] = {}
    gaps: list[float] = []
    for m in messages:
        cx, cy = int(m.x // cell), int(m.y // cell)
        best = math.inf
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in grid.get((cx + dx, cy + dy), ()):
                    o = latest[other]
                    if other != m.sender and m.time - o.time <= 1.0:
                        best = min(best, math.hypot(m.x - o.x, m.y - o.y))
        gaps.append(best if best <= NEIGHBOUR_RANGE_M else 0.0)
        old = where.get(m.sender)
        if old is not None and old != (cx, cy):
            grid[old].discard(m.sender)
        grid.setdefault((cx, cy), set()).add(m.sender)
        where[m.sender], latest[m.sender] = (cx, cy), m
    return gaps


def to_telemetry(messages: Iterable[RawMessage], *, prefix: str, grid_m: float = 200.0
                 ) -> tuple[list[Telemetry], set[str]]:
    ordered = sorted(messages, key=lambda m: (m.time, m.sender))
    gaps = _nearest_gaps(ordered)
    travelled: dict[str, float] = {}
    previous: dict[str, RawMessage] = {}
    sequence: dict[str, int] = {}
    stream: list[Telemetry] = []
    attacked: set[str] = set()
    for m, gap in zip(ordered, gaps, strict=True):
        last = previous.get(m.sender)
        if last is not None:
            travelled[m.sender] = travelled[m.sender] + math.hypot(m.x - last.x, m.y - last.y)
        else:
            travelled[m.sender] = 0.0
        previous[m.sender] = m
        seq = sequence[m.sender] = sequence.get(m.sender, 0) + 1
        device_id = f"{prefix}-{m.sender}"
        message_id = f"{device_id}-{seq:06d}"
        stream.append(Telemetry(
            device_id=device_id,
            timestamp=round(m.time, 3),
            position=round(travelled[m.sender], 4),
            speed=round(_clamp_speed(m.speed_kmh), 4),
            intersection_id=f"cell-{int(m.x // grid_m)}-{int(m.y // grid_m)}",
            occupancy=round(occupancy_from_headway(gap), 4),
            signal_state="unknown",
            sequence_number=seq,
            message_id=message_id,
        ))
        if m.attack:
            attacked.add(message_id)
    return stream, attacked


def _veremi_traces(archive: zipfile.ZipFile) -> Iterator[tuple[str, io.BufferedIOBase]]:
    for name in archive.namelist():
        if name.endswith(".zip"):
            with archive.open(name) as inner, zipfile.ZipFile(io.BytesIO(inner.read())) as nested:
                yield from _veremi_traces(nested)
        elif "traceJSON-" in name and name.endswith(".json"):
            with archive.open(name) as handle:
                yield name, handle


def read_veremi(path: str | Path, *, duration_s: float | None = 900.0) -> list[RawMessage]:
    attackers: set[str] = set()
    seen: dict[int, RawMessage] = {}
    with zipfile.ZipFile(path) as archive:
        for name, handle in _veremi_traces(archive):
            parts = Path(name).name.split("-")
            if len(parts) >= 4 and parts[3] != "A0":
                attackers.add(parts[1])
            for line in handle:
                if b'"sender"' not in line:
                    continue
                record = json.loads(line)
                if record.get("type") != 3 or record["messageID"] in seen:
                    continue
                seen[record["messageID"]] = RawMessage(
                    sender=str(record["sender"]), time=float(record["sendTime"]),
                    x=float(record["pos"][0]), y=float(record["pos"][1]),
                    speed_kmh=math.hypot(record["spd"][0], record["spd"][1]) * 3.6,
                )
    if not seen:
        return []
    start = min(m.time for m in seen.values())
    return [
        RawMessage(m.sender, m.time, m.x, m.y, m.speed_kmh, m.sender in attackers)
        for m in seen.values()
        if duration_s is None or m.time - start <= duration_s
    ]


def read_tampa_bsm(path: str | Path) -> list[RawMessage]:
    parent: dict[str, str] = {}

    def find(i: str) -> str:
        while parent.setdefault(i, i) != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first: dict[tuple[str, str, str, str], tuple[str, float, float, float, float]] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                lat, lon = float(row["coredata_lat"]) * 1e-7, float(row["coredata_long"]) * 1e-7
                speed_kmh = float(row["coredata_speed"]) * 0.02 * 3.6
                when = datetime.fromisoformat(row["metadata_recordgeneratedat"]).timestamp()
            except (KeyError, ValueError):
                continue
            key = (row["coredata_secmark"], row["coredata_lat"], row["coredata_long"], row["coredata_speed"])
            vehicle = row["coredata_id"]
            if key in first:
                parent[find(vehicle)] = find(first[key][0])
            else:
                first[key] = (vehicle, when, lat, lon, speed_kmh)
    if not first:
        return []
    lat0, lon0 = next(iter(first.values()))[2:4]
    scale = 6_371_000.0
    return [
        RawMessage(sender=find(vehicle), time=when,
                   x=math.radians(lon - lon0) * scale * math.cos(math.radians(lat0)),
                   y=math.radians(lat - lat0) * scale, speed_kmh=speed_kmh)
        for vehicle, when, lat, lon, speed_kmh in first.values()
    ]
