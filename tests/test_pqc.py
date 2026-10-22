import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_city_security.iot_sim.traffic_generator import TrafficGenerator
from smart_city_security.pqc.classical_backend import ClassicalBackend
from smart_city_security.pqc.secure_channel import SecureChannel


def test_classical_secure_round_trip_and_replay_rejection():
    channel = SecureChannel(ClassicalBackend(), max_messages=10)
    telemetry = TrafficGenerator(1, seed=1).generate(1)[0]
    message = channel.protect(telemetry, now=telemetry.timestamp)
    recovered = channel.unprotect(message, now=telemetry.timestamp)
    assert recovered.message_id == telemetry.message_id
    try:
        channel.unprotect(message, now=telemetry.timestamp)
    except ValueError:
        pass
    else:
        raise AssertionError("replayed message was accepted")
