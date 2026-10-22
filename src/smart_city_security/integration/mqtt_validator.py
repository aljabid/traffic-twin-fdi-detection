from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from smart_city_security.network.mqtt_client import MQTTClient, MQTTTLSConfig


def validate_broker(
    host: str,
    port: int,
    tls: MQTTTLSConfig,
    timeout_seconds: float = 10,
) -> bool:
    received = Event()
    topic = "smart-city/validation/loopback"
    client = MQTTClient(
        host,
        port,
        client_id="smart-city-validator",
        tls=tls,
        default_qos=1,
    )
    client.set_last_will(
        "smart-city/status/validator", b"offline", qos=1, retain=False
    )
    try:
        client.connect()
        client.subscribe(topic, lambda payload: received.set() if payload == b"ok" else None)
        client.publish(topic, b"ok", qos=1, expiry_seconds=10)
        return received.wait(timeout_seconds)
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument(
        "--output", default="results/system/mqtt-tls-validation.json"
    )
    args = parser.parse_args(argv)
    ok = validate_broker(
        args.host,
        args.port,
        MQTTTLSConfig(args.ca, args.cert, args.key),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "passed": ok,
                "host": args.host,
                "port": args.port,
                "generated_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(output)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
