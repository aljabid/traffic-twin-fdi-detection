from __future__ import annotations

from dataclasses import dataclass

from smart_city_security.contracts import AlertEvent
from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.ml_detection import AnomalyDetector, FeatureBuilder
from smart_city_security.observability import MetricsRegistry, Tracer
from smart_city_security.pqc.secure_channel import SecureChannel
from smart_city_security.schemas import DetectionResult, SecureMessage, Telemetry, TwinState
from smart_city_security.security.audit import AuditLog
from smart_city_security.storage import TelemetryRepository

from .alerts import AlertPolicy, AlertStore
from .data_quality import QualityAssessment, TelemetryQualityPolicy


@dataclass(frozen=True, slots=True)
class IngestionResult:
    telemetry: Telemetry
    twin_state: TwinState | None = None
    quality: QualityAssessment | None = None
    detection: DetectionResult | None = None
    alert: AlertEvent | None = None


class TelemetryIngestionService:

    def __init__(
        self,
        repository: TelemetryRepository,
        twin: TrafficDigitalTwin,
        channel: SecureChannel | None = None,
        audit: AuditLog | None = None,
        quality_policy: TelemetryQualityPolicy | None = None,
        detector: AnomalyDetector | None = None,
        feature_builder: FeatureBuilder | None = None,
        alert_policy: AlertPolicy | None = None,
        alert_store: AlertStore | None = None,
        metrics: MetricsRegistry | None = None,
        tracer: Tracer | None = None,
    ):
        self.repository = repository
        self.twin = twin
        self.channel = channel
        self.audit = audit
        self.quality_policy = quality_policy
        self.detector = detector
        self.feature_builder = feature_builder
        self.alert_policy = alert_policy or AlertPolicy()
        self.alert_store = alert_store
        self.metrics = metrics
        self.tracer = tracer or Tracer()

    def ingest(self, payload: SecureMessage | Telemetry) -> IngestionResult:
        with self.tracer.span("telemetry.ingest"):
            return self._ingest(payload)

    def _ingest(self, payload: SecureMessage | Telemetry) -> IngestionResult:
        telemetry: SecureMessage | Telemetry
        if self.channel:
            if not isinstance(payload, SecureMessage):
                raise TypeError("payload must be a SecureMessage when a secure channel is configured")
            telemetry = self.channel.unprotect(payload)
        else:
            telemetry = payload
        if not isinstance(telemetry, Telemetry):
            raise TypeError("ingestion payload did not resolve to telemetry")
        self.repository.append(telemetry)
        self._count("telemetry_received_total")

        if self.quality_policy:
            quality = self.quality_policy.assess(telemetry)
            if not quality.accepted:
                alert = self._raise_alert(self.alert_policy.from_quality(quality, telemetry.device_id))
                if self.audit:
                    self.audit.record(
                        "telemetry_rejected_quality", telemetry.device_id, "failure",
                        "; ".join(issue.code for issue in quality.issues),
                    )
                self._count("telemetry_rejected_quality_total")
                return IngestionResult(telemetry, quality=quality, alert=alert)
        else:
            quality = None

        if self.detector and self.feature_builder:
            predicted_state = self.twin.predict(telemetry)
            feature = self.feature_builder.build(telemetry, predicted_state)
            labels, scores = self.detector.predict(feature.values.reshape(1, -1))
            detection = DetectionResult(
                telemetry.message_id, bool(labels[0]), float(scores[0]), self.detector.name
            )
            alert = None
            if detection.is_anomaly:
                alert = self._raise_alert(self.alert_policy.from_detection(detection, telemetry.device_id))
                if self.audit:
                    self.audit.record(
                        "anomaly_detected", telemetry.device_id, "flagged",
                        f"score={detection.anomaly_score:.4f}",
                    )
                self._count("anomaly_detected_total")
            else:
                self.twin.commit(telemetry)
                self._count("twin_committed_total")
            state = predicted_state
        else:
            detection = None
            alert = None
            state = self.twin.observe(telemetry)
            self._count("twin_committed_total")

        if self.audit:
            self.audit.record("telemetry_ingested", telemetry.device_id)
        return IngestionResult(telemetry, state, quality, detection, alert)

    def _count(self, name: str) -> None:
        if self.metrics:
            self.metrics.increment(name)

    def _raise_alert(self, alert: AlertEvent | None) -> AlertEvent | None:
        if alert and self.alert_store:
            self.alert_store.record(alert)
        return alert
