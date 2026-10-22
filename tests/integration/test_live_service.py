import pytest

from smart_city_security.integration.live_service import LiveIngestionDaemon
from smart_city_security.iot_sim import TrafficGenerator

CONFIG = {
    "seed": 42,
    "simulation": {"devices": 3, "messages_per_device": 10},
    "network": {"mode": "simulated", "topic": "smart-city/telemetry"},
    "security": {"backend": "none"},
    "digital_twin": {"history_window": 8},
    "ml": {"model": "isolation_forest", "contamination": 0.15, "include_divergence": True},
}


def test_daemon_ingests_published_telemetry_end_to_end():
    daemon = LiveIngestionDaemon(dict(CONFIG))
    daemon.start()
    try:
        message = TrafficGenerator(1, seed=7).generate(1)[0]
        daemon.mqtt_client.publish("smart-city/telemetry", message.to_bytes())

        assert daemon.repository.get(message.message_id) == message
        assert daemon.metrics.snapshot()["counters"]["telemetry_received_total"] == 1
        assert daemon.health.status().ready
    finally:
        daemon.stop()


def test_daemon_refuses_automatic_control():
    config = dict(CONFIG)
    config["operation"] = {"automatic_control": True}
    with pytest.raises(ValueError, match="advisory-only"):
        LiveIngestionDaemon(config)


def test_daemon_drops_undecodable_payload_without_crashing():
    daemon = LiveIngestionDaemon(dict(CONFIG))
    daemon.start()
    try:
        daemon.mqtt_client.publish("smart-city/telemetry", b"not valid telemetry bytes")
        assert daemon.metrics.snapshot()["counters"]["telemetry_undecodable_total"] == 1
    finally:
        daemon.stop()


def test_daemon_calibrates_detector_from_warmup_window():
    config = dict(CONFIG)
    config["ml"] = {
        **CONFIG["ml"],
        "calibration": {"enabled": True, "warmup_messages": 24, "target_false_positive_rate": 0.1},
    }
    daemon = LiveIngestionDaemon(config)
    daemon.start()
    try:
        warmup = TrafficGenerator(4, seed=11).generate(6)
        assert len(warmup) == 24
        for message in warmup[:-1]:
            daemon.mqtt_client.publish("smart-city/telemetry", message.to_bytes())
        assert daemon._calibrating is True
        assert daemon.ingestion_service.detector is None
        assert daemon.health.status().ready is False

        daemon.mqtt_client.publish("smart-city/telemetry", warmup[-1].to_bytes())

        assert daemon._calibrating is False
        assert daemon.ingestion_service.detector is not None
        assert daemon.health.status().ready is True
        assert any(e.event == "detector_calibrated" for e in daemon.audit.events)
        assert daemon.metrics.snapshot()["counters"]["warmup_samples_total"] == 24

        live = TrafficGenerator(1, seed=99).generate(1)[0]
        daemon.mqtt_client.publish("smart-city/telemetry", live.to_bytes())
        assert daemon.metrics.snapshot()["counters"]["telemetry_received_total"] == 1
    finally:
        daemon.stop()


def test_calibration_disabled_by_default_uses_bootstrap_detector():
    daemon = LiveIngestionDaemon(dict(CONFIG))
    assert daemon._calibrating is False
    assert daemon.ingestion_service.detector is not None
