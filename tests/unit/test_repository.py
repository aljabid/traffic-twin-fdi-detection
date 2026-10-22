import pytest

from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.storage import InMemoryTelemetryRepository


def test_repository_rejects_duplicates_and_returns_recent_messages():
    repository = InMemoryTelemetryRepository()
    message = TrafficGenerator(1).generate(1)[0]
    repository.append(message)
    assert repository.recent(message.device_id) == [message]
    with pytest.raises(ValueError, match="Duplicate"):
        repository.append(message)
