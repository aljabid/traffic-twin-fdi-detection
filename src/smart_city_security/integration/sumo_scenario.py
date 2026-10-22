from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

import sumolib
import traci

_SUMO_HOME = Path(sumolib.__file__).resolve().parents[1] / "sumo"
_BIN = _SUMO_HOME / "bin"
_RANDOM_TRIPS = _SUMO_HOME / "tools" / "randomTrips.py"

_TLS_STATE_TO_SIGNAL = {"r": "red", "y": "yellow", "g": "green", "G": "green", "s": "green", "o": "unknown", "u": "yellow"}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def build_scenario(out_dir: Path, *, seed: int, vehicles_per_hour: int, duration_s: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    net = out_dir / "net.net.xml"
    _run([
        str(_BIN / "netgenerate"), "--grid", "--grid.number", "1",
        "--grid.length", "300", "--grid.attach-length", "250",
        "--default.lanenumber", "2", "--tls.guess", "true",
        "--tls.default-type", "static", "--no-turnarounds", "true",
        "--output-file", str(net),
    ])
    trips = out_dir / "trips.trips.xml"
    routes = out_dir / "routes.rou.xml"
    period = max(0.2, 3600.0 / max(1, vehicles_per_hour))
    _run([
        sys.executable, str(_RANDOM_TRIPS), "-n", str(net),
        "-o", str(trips), "-r", str(routes), "--seed", str(seed),
        "-b", "0", "-e", str(duration_s), "-p", f"{period:.3f}",
        "--vehicle-class", "passenger", "--validate",
        "--trip-attributes", 'departLane="best" departSpeed="max"',
    ])
    cfg = out_dir / "scenario.sumocfg"
    cfg.write_text(
        f"""<configuration>
  <input><net-file value="{net.name}"/><route-files value="{routes.name}"/></input>
  <time><begin value="0"/><end value="{duration_s}"/></time>
  <processing><time-to-teleport value="-1"/></processing>
</configuration>
""",
        encoding="utf-8",
    )
    return cfg


def run_simulation(cfg: Path, out_csv: Path, *, duration_s: int, step_s: float = 1.0) -> int:
    os.environ.setdefault("SUMO_HOME", str(_SUMO_HOME))
    traci.start([str(_BIN / "sumo"), "-c", str(cfg), "--step-length", str(step_s), "--no-warnings", "true"])
    rows = 0
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "id", "x", "y", "speed", "type", "edge", "occupancy", "signal_state"])
        try:
            while traci.simulation.getTime() < duration_s and traci.simulation.getMinExpectedNumber() > 0:
                traci.simulationStep()
                now = traci.simulation.getTime()
                for vehicle in traci.vehicle.getIDList():
                    lane = traci.vehicle.getLaneID(vehicle)
                    x, y = traci.vehicle.getPosition(vehicle)
                    signal = "unknown"
                    tls_list = traci.vehicle.getNextTLS(vehicle)
                    if tls_list:
                        state = str(tls_list[0][3])
                        signal = _TLS_STATE_TO_SIGNAL.get(state, "unknown")
                    writer.writerow([
                        f"{now:.1f}", vehicle, f"{x:.3f}", f"{y:.3f}",
                        f"{traci.vehicle.getSpeed(vehicle):.4f}", "vehicle",
                        traci.vehicle.getRoadID(vehicle) or lane,
                        f"{traci.lane.getLastStepOccupancy(lane):.4f}" if lane else "0.0",
                        signal,
                    ])
                    rows += 1
        finally:
            traci.close()
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="datasets/sumo")
    parser.add_argument("--out-csv", default="datasets/sumo/sumo_fcd.csv")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--vehicles-per-hour", type=int, default=900)
    parser.add_argument("--duration", type=int, default=1800)
    args = parser.parse_args(argv)

    if not _RANDOM_TRIPS.exists():
        print(f"SUMO tools not found at {_RANDOM_TRIPS}; install eclipse-sumo", file=sys.stderr)
        return 1
    cfg = build_scenario(
        Path(args.out_dir), seed=args.seed,
        vehicles_per_hour=args.vehicles_per_hour, duration_s=args.duration,
    )
    rows = run_simulation(cfg, Path(args.out_csv), duration_s=args.duration)
    print(f"{args.out_csv}: {rows} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
