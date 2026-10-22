import sqlite3

from smart_city_security.contracts import EventEnvelope
from smart_city_security.messaging import SQLiteEventQueue


def test_durable_queue_acknowledges_and_dead_letters(tmp_path):
    queue = SQLiteEventQueue(tmp_path / "events.db", max_attempts=2)
    sequence = queue.publish(EventEnvelope("telemetry", {"speed": 1}))
    leased = queue.lease()
    assert leased is not None and leased.sequence == sequence
    assert queue.reject(sequence, "transient", retry_delay_seconds=0)
    assert queue.lease().attempts == 1
    assert queue.reject(sequence, "permanent", retry_delay_seconds=0)
    assert queue.depth() == 0
    assert queue.dead_letter_depth() == 1
    queue.close()


def test_durable_queue_prevents_duplicate_event_ids(tmp_path):
    queue = SQLiteEventQueue(tmp_path / "events.db")
    event = EventEnvelope("alert", {})
    queue.publish(event)
    try:
        queue.publish(event)
    except sqlite3.IntegrityError as exc:
        assert "UNIQUE" in str(exc)
    else:
        raise AssertionError("duplicate event was accepted")
    leased = queue.lease()
    assert leased and queue.acknowledge(leased.sequence)
    assert not queue.acknowledge(leased.sequence)
