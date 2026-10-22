from __future__ import annotations

import csv
import itertools
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any


@dataclass(frozen=True, slots=True)
class PowerSample:
    timestamp_seconds: float
    voltage_volts: float
    current_amperes: float

    @property
    def power_watts(self) -> float:
        return self.voltage_volts * self.current_amperes


@dataclass(frozen=True, slots=True)
class EnergyReport:
    samples: int
    duration_seconds: float
    energy_joules: float
    mean_power_watts: float
    peak_power_watts: float
    meter_id: str
    calibration_reference: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_power_samples(path: str | Path) -> list[PowerSample]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp_seconds", "voltage_volts", "current_amperes"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Power CSV requires columns: {sorted(required)}")
        samples = [
            PowerSample(
                float(row["timestamp_seconds"]),
                float(row["voltage_volts"]),
                float(row["current_amperes"]),
            )
            for row in reader
        ]
    if len(samples) < 2:
        raise ValueError("At least two power samples are required")
    if any(right.timestamp_seconds <= left.timestamp_seconds for left, right in itertools.pairwise(samples)):
        raise ValueError("Power sample timestamps must increase")
    return samples


def calculate_energy(
    samples: list[PowerSample], *, meter_id: str, calibration_reference: str
) -> EnergyReport:
    if len(samples) < 2 or not meter_id or not calibration_reference:
        raise ValueError("Samples and attributable calibrated meter metadata are required")
    energy = 0.0
    for left, right in itertools.pairwise(samples):
        duration = right.timestamp_seconds - left.timestamp_seconds
        energy += duration * (left.power_watts + right.power_watts) / 2
    powers = [sample.power_watts for sample in samples]
    return EnergyReport(
        len(samples),
        samples[-1].timestamp_seconds - samples[0].timestamp_seconds,
        energy,
        fmean(powers),
        max(powers),
        meter_id,
        calibration_reference,
    )
