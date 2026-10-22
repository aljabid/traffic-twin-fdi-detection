from smart_city_security.contracts import EventEnvelope
from smart_city_security.messaging import InMemoryEventBus


def test_event_bus_delivers_and_dead_letters_failures():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe("telemetry", received.append)
    bus.subscribe("telemetry", lambda _event: 1 / 0)
    event = EventEnvelope("telemetry", {"id": "1"})
    assert bus.publish(event) == 1
    assert received == [event]
    assert len(bus.dead_letters) == 1
