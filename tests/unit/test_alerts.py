from smart_city_security.schemas import DetectionResult
from smart_city_security.services.alerts import AlertPolicy


def test_transport_rejection_becomes_critical_alert():
    detection = DetectionResult(
        "m1", True, float("inf"), "transport-security", True, "replay"
    )
    alert = AlertPolicy().from_detection(detection, "d1")
    assert alert is not None and alert.severity == "critical"
