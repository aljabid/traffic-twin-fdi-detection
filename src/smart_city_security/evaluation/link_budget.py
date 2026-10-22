from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

LATENCY_BUDGET_MS = 100.0


@dataclass(frozen=True, slots=True)
class Link:
    name: str
    bit_rate: float
    max_payload_bytes: int | None = None
    duty_cycle: float | None = None
    source: str = ""


LINKS: tuple[Link, ...] = (
    Link("LoRaWAN EU868 DR0 (SF12)", 250, 51, 0.01, "LoRa Alliance RP002; ETSI 1% sub-band"),
    Link("LoRaWAN EU868 DR5 (SF7)", 5_470, 222, 0.01, "LoRa Alliance RP002; ETSI 1% sub-band"),
    Link("NB-IoT (Rel-13 Cat-NB1)", 62_500, None, None, "3GPP Rel-13, multi-tone UL peak"),
    Link("IEEE 802.15.4 (2.4 GHz)", 250_000, 127, None, "IEEE 802.15.4 O-QPSK, aMaxPHYPacketSize"),
    Link("LTE-M (Rel-13 Cat-M1)", 1_000_000, None, None, "3GPP Rel-13 UL peak"),
    Link("5G (IMT-2020 UL)", 50_000_000, None, None, "ITU-R M.2410 UL user-experienced rate"),
    Link("6G (IMT-2030 target)", 300_000_000, None, None, "ITU-R M.2160 user-experienced rate example"),
)


@dataclass(frozen=True, slots=True)
class SuiteSizes:

    suite: str
    message_bytes: int
    handshake_bytes: int
    messages_per_session: int


def link_cost(sizes: SuiteSizes, link: Link) -> dict[str, Any]:
    per_message = sizes.message_bytes + sizes.handshake_bytes / sizes.messages_per_session
    airtime_ms = sizes.message_bytes * 8 / link.bit_rate * 1000
    handshake_ms = sizes.handshake_bytes * 8 / link.bit_rate * 1000
    frames = math.ceil(sizes.message_bytes / link.max_payload_bytes) if link.max_payload_bytes else 1
    max_rate = link.bit_rate / (8 * per_message) * (link.duty_cycle or 1.0)
    return {
        "link": link.name,
        "suite": sizes.suite,
        "message_bytes": sizes.message_bytes,
        "message_airtime_ms": airtime_ms,
        "handshake_airtime_ms": handshake_ms,
        "frames_per_message": frames,
        "within_latency_budget": airtime_ms <= LATENCY_BUDGET_MS,
        "max_messages_per_second": max_rate,
        "min_seconds_between_messages": (
            airtime_ms / 1000 / link.duty_cycle if link.duty_cycle else airtime_ms / 1000
        ),
    }


def analyse(suites: list[SuiteSizes], links: tuple[Link, ...] = LINKS) -> dict[str, Any]:
    rows = [link_cost(s, link) for link in links for s in suites]
    return {
        "latency_budget_ms": LATENCY_BUDGET_MS,
        "model": "lower bound: payload bits / nominal rate; excludes headers, "
                 "retransmission, scheduling and propagation",
        "suites": [asdict(s) for s in suites],
        "links": [asdict(link) for link in links],
        "rows": rows,
    }


def measure_suites(messages_per_session: int = 50) -> list[SuiteSizes]:
    from smart_city_security.evaluation.crypto_metrics import benchmark_backend
    from smart_city_security.pqc import ClassicalBackend, PQCBackend, SecureChannel
    from smart_city_security.schemas import Telemetry

    sample = Telemetry.create("veh-0001", 123.4, 12.5, "int-01", 0.31, "green", 17)
    suites = []
    for backend in (ClassicalBackend(), PQCBackend()):
        message = SecureChannel(backend, max_messages=messages_per_session).protect(sample)
        suites.append(SuiteSizes(
            suite=backend.name,
            message_bytes=len(message.to_bytes()),
            handshake_bytes=benchmark_backend(backend, 3).handshake_bytes,
            messages_per_session=messages_per_session,
        ))
    return suites


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--messages-per-session", type=int, default=50,
                        help="re-key interval; SecureChannel's default is 50")
    parser.add_argument("--output", default="results/crypto/link-budget.json")
    args = parser.parse_args(argv)
    report = analyse(measure_suites(args.messages_per_session))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{'link':28} {'suite':22} {'bytes':>6} {'airtime ms':>11} {'frames':>7} {'<=100ms':>8} {'max msg/s':>10}")
    for r in report["rows"]:
        print(f"{r['link']:28} {r['suite']:22} {r['message_bytes']:>6} {r['message_airtime_ms']:>11.2f} "
              f"{r['frames_per_message']:>7} {r['within_latency_budget']!s:>8} {r['max_messages_per_second']:>10.2f}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
