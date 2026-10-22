from dataclasses import replace

import numpy as np

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.ml_detection import FeatureBuilder
from smart_city_security.observability import MetricsRegistry
from smart_city_security.services import (
    AlertStore,
    TelemetryIngestionService,
    TelemetryQualityPolicy,
)
from smart_city_security.storage import InMemoryTelemetryRepository


class _StubDetector:
    def __init__(self, *, anomaly: bool):
        self.name = "stub"
        self._anomaly = anomaly

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        count = len(features)
        return (
            np.full(count, self._anomaly),
            np.full(count, 0.99 if self._anomaly else 0.01),
        )


def test_ingestion_updates_repository_and_twin():
    message = TrafficGenerator(1).generate(1)[0]
    repository = InMemoryTelemetryRepository()
    result = TelemetryIngestionService(
        repository, TrafficDigitalTwin()
    ).ingest(message)
    assert repository.get(message.message_id) == message
    assert result.twin_state.intersection_id == message.intersection_id


def test_quality_rejected_telemetry_raises_alert_and_skips_twin():
    message = replace(TrafficGenerator(1).generate(1)[0], speed=float("nan"))
    repository = InMemoryTelemetryRepository()
    twin = TrafficDigitalTwin()
    alert_store = AlertStore()
    service = TelemetryIngestionService(
        repository, twin, quality_policy=TelemetryQualityPolicy(), alert_store=alert_store
    )

    result = service.ingest(message)

    assert result.twin_state is None
    assert result.quality is not None and not result.quality.accepted
    assert result.alert is not None and result.alert.category == "data-quality"
    assert alert_store.list() == (result.alert,)
    assert twin.state.history(message.intersection_id) == ()


def test_anomalous_telemetry_raises_alert_and_does_not_poison_twin():
    message = TrafficGenerator(1).generate(1)[0]
    repository = InMemoryTelemetryRepository()
    twin = TrafficDigitalTwin()
    alert_store = AlertStore()
    service = TelemetryIngestionService(
        repository,
        twin,
        detector=_StubDetector(anomaly=True),
        feature_builder=FeatureBuilder(),
        alert_store=alert_store,
    )

    result = service.ingest(message)

    assert result.detection is not None and result.detection.is_anomaly
    assert result.alert is not None and result.alert.category == "behavior-anomaly"
    assert twin.state.history(message.intersection_id) == ()


def test_normal_telemetry_is_committed_to_twin_with_no_alert():
    message = TrafficGenerator(1).generate(1)[0]
    repository = InMemoryTelemetryRepository()
    twin = TrafficDigitalTwin()
    alert_store = AlertStore()
    service = TelemetryIngestionService(
        repository,
        twin,
        detector=_StubDetector(anomaly=False),
        feature_builder=FeatureBuilder(),
        alert_store=alert_store,
    )

    result = service.ingest(message)

    assert result.alert is None
    assert twin.state.history(message.intersection_id) == (message,)
    assert alert_store.list() == ()


def test_metrics_are_recorded_per_outcome():
    message = TrafficGenerator(1).generate(1)[0]
    metrics = MetricsRegistry()
    service = TelemetryIngestionService(
        InMemoryTelemetryRepository(),
        TrafficDigitalTwin(),
        detector=_StubDetector(anomaly=True),
        feature_builder=FeatureBuilder(),
        metrics=metrics,
    )

    service.ingest(message)

    snapshot = metrics.snapshot()["counters"]
    assert snapshot["telemetry_received_total"] == 1
    assert snapshot["anomaly_detected_total"] == 1
