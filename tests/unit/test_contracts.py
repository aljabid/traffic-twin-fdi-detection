import pytest

from smart_city_security.contracts import EventEnvelope


def test_event_envelope_round_trip():
    event = EventEnvelope("telemetry.received", {"device_id": "d1"})
    assert EventEnvelope.from_bytes(event.to_bytes()) == event


def test_unknown_schema_version_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        EventEnvelope("telemetry.received", {}, schema_version=99)
