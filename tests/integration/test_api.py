import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from smart_city_security.api import create_app
from smart_city_security.contracts import AlertEvent
from smart_city_security.services import AlertStore


def test_api_health_and_protected_device_lifecycle():
    client = TestClient(create_app(admin_token="test-secret"))
    assert client.get("/live").json() == {"live": True}
    assert client.get("/ready").status_code == 200
    assert client.post(
        "/v1/devices", json={"device_id": "d1", "device_type": "vehicle"}
    ).status_code == 401
    enrolled = client.post(
        "/v1/devices",
        headers={"Authorization": "Bearer test-secret"},
        json={"device_id": "d1", "device_type": "vehicle"},
    )
    assert enrolled.status_code == 201
    revoked = client.post(
        "/v1/devices/d1/revoke",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert revoked.json()["status"] == "revoked"


def test_feedback_endpoint_requires_admin_auth():
    client = TestClient(create_app(admin_token="test-secret"))
    body = {"operator_id": "op-1", "verdict": "true_positive"}
    assert client.post("/v1/alerts/a1/feedback", json=body).status_code == 401
    accepted = client.post(
        "/v1/alerts/a1/feedback",
        headers={"Authorization": "Bearer test-secret"},
        json=body,
    )
    assert accepted.status_code == 200
    assert accepted.json()["verdict"] == "true_positive"


def test_alerts_endpoint_requires_admin_auth_and_lists_raised_alerts():
    alert_store = AlertStore()
    alert_store.record(
        AlertEvent(
            alert_id="a1",
            device_id="device-001",
            severity="high",
            category="behavior-anomaly",
            score=0.91,
            explanation="isolation_forest anomaly score=0.9100",
        )
    )
    client = TestClient(create_app(admin_token="test-secret", alerts=alert_store))

    assert client.get("/v1/alerts").status_code == 401
    listed = client.get("/v1/alerts", headers={"Authorization": "Bearer test-secret"})
    assert listed.status_code == 200
    assert listed.json()["alerts"][0]["alert_id"] == "a1"
