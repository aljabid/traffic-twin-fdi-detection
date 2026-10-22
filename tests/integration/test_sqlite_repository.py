import pytest

from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.storage import SQLiteTelemetryRepository


def test_sqlite_repository_persists_and_backs_up(tmp_path):
    message = TrafficGenerator(1).generate(1)[0]
    repository = SQLiteTelemetryRepository(tmp_path / "telemetry.db")
    repository.append(message)
    assert repository.get(message.message_id) == message
    backup = repository.backup(tmp_path / "backup.db")
    repository.close()
    restored = SQLiteTelemetryRepository(backup)
    assert restored.get(message.message_id) == message
    restored.close()


def test_get_missing_returns_none(tmp_path):
    repository = SQLiteTelemetryRepository(tmp_path / "t.db")
    try:
        assert repository.get("nope") is None
    finally:
        repository.close()


def test_duplicate_append_raises(tmp_path):
    message = TrafficGenerator(1).generate(1)[0]
    repository = SQLiteTelemetryRepository(tmp_path / "t.db")
    try:
        repository.append(message)
        with pytest.raises(ValueError):
            repository.append(message)
    finally:
        repository.close()


def test_recent_orders_newest_first_and_honours_limit(tmp_path):
    messages = TrafficGenerator(1).generate(5)
    device_id = messages[0].device_id
    repository = SQLiteTelemetryRepository(tmp_path / "t.db")
    try:
        for message in messages:
            repository.append(message)
        recent = repository.recent(device_id, limit=3)
        assert [m.message_id for m in recent] == [m.message_id for m in messages[-3:]]
        assert repository.recent(device_id, limit=0) == []
    finally:
        repository.close()


def test_purge_before_deletes_and_counts(tmp_path):
    messages = TrafficGenerator(1).generate(4)
    repository = SQLiteTelemetryRepository(tmp_path / "t.db")
    try:
        for message in messages:
            repository.append(message)
        cutoff = messages[2].timestamp
        removed = repository.purge_before(cutoff)
        assert removed == sum(1 for m in messages if m.timestamp < cutoff)
        assert all(m.timestamp >= cutoff for m in repository.recent(messages[0].device_id))
    finally:
        repository.close()
