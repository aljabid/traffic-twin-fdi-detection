from __future__ import annotations

import uuid

from smart_city_security.contracts import AlertEvent
from smart_city_security.schemas import DetectionResult

from .data_quality import QualityAssessment

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class AlertStore:

    def __init__(self) -> None:
        self.items: list[AlertEvent] = []

    def record(self, alert: AlertEvent) -> AlertEvent:
        self.items.append(alert)
        return alert

    def get(self, alert_id: str) -> AlertEvent | None:
        return next((item for item in self.items if item.alert_id == alert_id), None)

    def list(self) -> tuple[AlertEvent, ...]:
        return tuple(self.items)


class AlertPolicy:
    def __init__(self, high_score: float = 0.75):
        self.high_score = high_score

    def from_detection(
        self, detection: DetectionResult, device_id: str
    ) -> AlertEvent | None:
        if not detection.is_anomaly:
            return None
        severity = (
            "critical"
            if detection.transport_rejected
            else "high"
            if detection.anomaly_score >= self.high_score
            else "medium"
        )
        explanation = detection.rejection_reason or (
            f"{detection.model} anomaly score={detection.anomaly_score:.4f}"
        )
        return AlertEvent(
            alert_id=str(uuid.uuid4()),
            device_id=device_id,
            severity=severity,
            category="transport-security"
            if detection.transport_rejected
            else "behavior-anomaly",
            score=detection.anomaly_score,
            explanation=explanation,
        )

    def from_quality(
        self, assessment: QualityAssessment, device_id: str
    ) -> AlertEvent | None:
        if assessment.accepted:
            return None
        worst = max(assessment.issues, key=lambda issue: _SEVERITY_ORDER[issue.severity])
        explanation = "; ".join(f"{issue.code}: {issue.detail}" for issue in assessment.issues)
        return AlertEvent(
            alert_id=str(uuid.uuid4()),
            device_id=device_id,
            severity="critical" if worst.severity == "critical" else "high",
            category="data-quality",
            score=1.0 - assessment.score,
            explanation=explanation,
        )
