from __future__ import annotations

import argparse
import csv
import pickle
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import dataclasses

import numpy as np

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.integration.hybrid_plus import HybridPlus, PlausibleForest
from smart_city_security.integration.real_data_experiment import _train_features, fit_detector
from smart_city_security.integration.supervised_baseline import TARGET_FPR
from smart_city_security.iot_sim.adversary import ATTACKS, REHEARSAL_ATTACKS, AdversarialCampaign
from smart_city_security.ml_detection import FeatureBuilder
from smart_city_security.schemas import Telemetry

FIELDS = ("device", "millis", "rtc", "position_cm", "speed_kmh", "occupancy", "attack")


@dataclass(frozen=True, slots=True)
class Reading:
    telemetry: Telemetry
    attack: int


NO_RTC_EPOCH = 1760000000


def parse(line: str, sequence: int, *, zone: str = "bench", clock: str = "rtc",
          offset_s: float = 0.0) -> Reading | None:
    parts = line.strip().split(",")
    if len(parts) != len(FIELDS) + 1 or parts[0] != "T":
        return None
    try:
        device, millis, rtc, position, speed, occupancy, attack = parts[1:]
        if clock == "millis":
            timestamp = NO_RTC_EPOCH + offset_s + int(millis) / 1000.0
        else:
            timestamp = float(rtc) + (int(millis) % 1000) / 1000.0
        telemetry = Telemetry(
            device_id=f"node-{device}", timestamp=round(timestamp, 3),
            position=float(position) / 100.0, speed=float(speed), intersection_id=zone,
            occupancy=min(1.0, max(0.0, float(occupancy))), signal_state="unknown",
            sequence_number=sequence, message_id=f"node-{device}-{sequence:07d}",
        )
        return Reading(telemetry, int(attack))
    except ValueError:
        return None


def readings(lines: Iterable[str], *, clock: str = "rtc") -> Iterator[Reading]:
    sequence, offset, last = 0, 0.0, -1
    for line in lines:
        parts = line.split(",")
        if clock == "millis" and len(parts) == len(FIELDS) + 1 and parts[2].isdigit():
            millis = int(parts[2])
            if millis < last:
                offset += last / 1000.0 + 0.1
            last = millis
        reading = parse(line, sequence + 1, clock=clock, offset_s=offset)
        if reading is not None:
            sequence += 1
            yield reading


def _attack_features(benign: list[Telemetry], name: str, seed: int, strength: float,
                     speed_scale: float) -> np.ndarray:
    attack = ATTACKS[name]
    attack = dataclasses.replace(attack, speed_bias_kmh=attack.speed_bias_kmh * speed_scale)
    campaign = AdversarialCampaign(seed + 40_000).run(benign, attack=attack, attack_ratio=0.15,
                                                      strength=strength, mode="replace")
    twin, builder = TrafficDigitalTwin(8), FeatureBuilder(True)
    rows = np.vstack([builder.build(m, twin.observe(m)).values for m in campaign.messages])
    keep = np.asarray([campaign.labels[m.message_id].label == "attack" for m in campaign.messages])
    return rows[keep]


def fit(benign: list[Telemetry], *, seed: int = 4, strength: float = 0.6,
        speed_scale: float = 1.0) -> dict[str, Any]:
    features = _train_features(benign, twin_window=8, include_divergence=True)
    base_dims = _train_features(benign[:2], twin_window=8, include_divergence=False).shape[1]
    attacks = np.vstack([_attack_features(benign, a, seed, strength, speed_scale) for a in REHEARSAL_ATTACKS])
    lof, _ = fit_detector(benign, model="lof", include_divergence=False, contamination=TARGET_FPR,
                          seed=seed, calibrate=True)
    detector = HybridPlus(PlausibleForest(features, attacks, seed), lof, features, base_dims)
    return {"detector": detector, "warm": benign[-200:]}


class LiveScorer:

    def __init__(self, model: dict[str, Any]) -> None:
        self.detector = model["detector"]
        self.twin = TrafficDigitalTwin(8)
        self.builder = FeatureBuilder(True)
        for m in model["warm"]:
            self.builder.build(m, self.twin.observe(m))

    def score(self, telemetry: Telemetry) -> bool:
        row = self.builder.build(telemetry, self.twin.observe(telemetry)).values
        flags, _ = self.detector.predict(row.reshape(1, -1))
        return bool(flags[0])


def parse_schedule(text: str) -> list[tuple[float, int]]:
    out, start = [], 0.0
    for part in filter(None, text.split(",")):
        code, seconds = part.split(":")
        out.append((start, int(code)))
        start += float(seconds)
    out.append((start, -1))
    return out


def _serial_lines(port: str, baud: int) -> Any:
    import serial

    return serial.Serial(port, baud, timeout=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("record", "fit", "live"))
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--csv", type=Path, default=Path("results/hardware/recording.csv"))
    parser.add_argument("--model", type=Path, default=Path("results/hardware/hybrid_plus.pkl"))
    parser.add_argument("--log", type=Path, default=Path("results/hardware/live.csv"))
    parser.add_argument("--seconds", type=float, default=1800.0)
    parser.add_argument("--schedule", default="", help="live mode: code:seconds,... attack plan")
    parser.add_argument("--clock", choices=("rtc", "millis"), default="rtc",
                        help="time source; millis for recordings made before the 2026-10-20 firmware fix")
    parser.add_argument("--speed-scale", type=float, default=1.0,
                        help="fit mode: scale of the rehearsal attacks' speed biases (bench: 0.2)")
    args = parser.parse_args(argv)

    if args.mode == "fit":
        with args.csv.open(encoding="utf-8") as handle:
            rows = [r for r in readings(handle, clock=args.clock) if r.attack == 0]
        model = fit([r.telemetry for r in rows], speed_scale=args.speed_scale)
        args.model.parent.mkdir(parents=True, exist_ok=True)
        args.model.write_bytes(pickle.dumps(model))
        print(f"trained on {len(rows)} benign readings -> {args.model}")
        return 0

    port = _serial_lines(args.port, args.baud)
    time.sleep(2.5)
    plan = parse_schedule(args.schedule) if args.schedule else []
    if plan:
        args.seconds = plan[-1][0]
    started = time.monotonic()
    deadline = started + args.seconds
    sent = -2
    out_path = args.csv if args.mode == "record" else args.log
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scorer = LiveScorer(pickle.loads(args.model.read_bytes())) if args.mode == "live" else None
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        sequence = 0
        while time.monotonic() < deadline:
            line = port.readline().decode("ascii", errors="ignore")
            if args.mode == "record":
                if line.startswith("T,"):
                    handle.write(line if line.endswith("\n") else line + "\n")
                continue
            if plan:
                elapsed = time.monotonic() - started
                code = next(c for (t0, c), (t1, _) in pairwise(plan) if t0 <= elapsed < t1)                     if elapsed < plan[-1][0] else 0
                if code != sent:
                    port.write(str(code).encode())
                    sent = code
            reading = parse(line, sequence + 1, clock=args.clock)
            if reading is None or scorer is None:
                continue
            sequence += 1
            start = time.perf_counter()
            alarm = scorer.score(reading.telemetry)
            port.write(b"A\n" if alarm else b"N\n")
            writer.writerow([reading.telemetry.message_id, reading.attack, int(alarm),
                             round((time.perf_counter() - start) * 1000.0, 3)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
