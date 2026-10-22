from smart_city_security.schemas import Telemetry
from smart_city_security.services import TelemetryQualityPolicy


def message(**overrides):
    values = {
        "device_id": "d1",
        "timestamp": 100.0,
        "position": 1.0,
        "speed": 20.0,
        "intersection_id": "i1",
        "occupancy": 0.5,
        "signal_state": "green",
        "sequence_number": 1,
        "message_id": "m1",
    }
    values.update(overrides)
    return Telemetry(**values)


def test_quality_policy_accepts_valid_and_rejects_replay():
    policy = TelemetryQualityPolicy(maximum_clock_skew_seconds=10)
    assert policy.assess(message(), now=100).accepted
    result = policy.assess(message(message_id="m2"), now=100)
    assert not result.accepted
    assert "SEQUENCE_ORDER" in {issue.code for issue in result.issues}


def test_quality_policy_normalizes_unknown_signal():
    policy = TelemetryQualityPolicy()
    result = policy.assess(message(signal_state="flashing"), now=100)
    assert result.accepted
    assert result.normalized.signal_state == "unknown"
    assert result.score < 1
