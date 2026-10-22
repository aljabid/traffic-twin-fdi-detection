from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DetectionResult:
    message_id: str
    is_anomaly: bool
    anomaly_score: float
    model: str
    transport_rejected: bool = False
    rejection_reason: str | None = None
