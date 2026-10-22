from __future__ import annotations

import hmac
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from smart_city_security.ml_detection.feedback import FeedbackStore
from smart_city_security.security.device_registry import DeviceRegistry
from smart_city_security.services.alerts import AlertStore
from smart_city_security.services.health import HealthService


class EnrollmentRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    device_type: str = Field(min_length=1, max_length=64)
    owner: str | None = Field(default=None, max_length=128)


class FeedbackRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=128)
    verdict: str
    comment: str = Field(default="", max_length=2000)


def create_app(
    *,
    registry: DeviceRegistry | None = None,
    health: HealthService | None = None,
    feedback: FeedbackStore | None = None,
    alerts: AlertStore | None = None,
    admin_token: str | None = None,
) -> FastAPI:
    devices = registry or DeviceRegistry()
    health_service = health or HealthService("smart-city-api")
    feedback_store = feedback or FeedbackStore()
    alert_store = alerts or AlertStore()
    app = FastAPI(
        title="Smart City Digital Twin Security API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
    )

    def require_admin(
        authorization: str | None = Header(default=None),
    ) -> None:
        if not admin_token:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Administrative authentication is not configured",
            )
        expected = f"Bearer {admin_token}"
        if authorization is None or not hmac.compare_digest(
            authorization, expected
        ):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid administrative token"
            )

    @app.get("/live")
    def live() -> dict[str, Any]:
        return {"live": True}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        state = health_service.status()
        if not state.ready:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"dependencies": state.dependencies},
            )
        return {
            "ready": True,
            "dependencies": state.dependencies,
        }

    @app.post(
        "/v1/devices",
        dependencies=[Depends(require_admin)],
        status_code=status.HTTP_201_CREATED,
    )
    def enroll(request: EnrollmentRequest) -> dict[str, Any]:
        credential = devices.enroll(
            request.device_id, request.device_type, request.owner
        )
        return {
            "device_id": credential.device_id,
            "status": credential.status,
            "generation": credential.generation,
        }

    @app.post(
        "/v1/devices/{device_id}/revoke",
        dependencies=[Depends(require_admin)],
    )
    def revoke(device_id: str) -> dict[str, Any]:
        try:
            devices.revoke(device_id)
        except KeyError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown device") from exc
        return {"device_id": device_id, "status": "revoked"}

    @app.get(
        "/v1/alerts",
        dependencies=[Depends(require_admin)],
    )
    def list_alerts() -> dict[str, Any]:
        return {
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "device_id": alert.device_id,
                    "severity": alert.severity,
                    "category": alert.category,
                    "score": alert.score,
                    "explanation": alert.explanation,
                    "requires_operator_ack": alert.requires_operator_ack,
                }
                for alert in alert_store.list()
            ]
        }

    @app.post(
        "/v1/alerts/{alert_id}/feedback",
        dependencies=[Depends(require_admin)],
    )
    def record_feedback(alert_id: str, request: FeedbackRequest) -> dict[str, Any]:
        try:
            item = feedback_store.record(
                alert_id,
                request.operator_id,
                request.verdict,
                request.comment,
            )
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)
            ) from exc
        return {
            "alert_id": item.alert_id,
            "verdict": item.verdict,
            "recorded_at": item.recorded_at,
        }

    return app
