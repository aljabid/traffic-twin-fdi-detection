from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import RLock

ACTIVE = "active"
SUSPENDED = "suspended"
REVOKED = "revoked"
LOST = "lost"
DECOMMISSIONED = "decommissioned"
TERMINAL_STATES = {REVOKED, LOST, DECOMMISSIONED}


@dataclass(frozen=True, slots=True)
class DeviceCredential:
    device_id: str
    device_type: str
    credential_id: str
    enabled: bool = True
    created_at: str = ""
    owner: str | None = None
    status: str = ACTIVE
    generation: int = 1
    replaced_by: str | None = None
    expires_at: float | None = None
    updated_at: str = ""


class DeviceRegistry:

    def __init__(self, *, credential_lifetime_seconds: float | None = None):
        self._devices: dict[str, DeviceCredential] = {}
        self.credential_lifetime_seconds = credential_lifetime_seconds
        self._lock = RLock()

    def enroll(
        self, device_id: str, device_type: str, owner: str | None = None
    ) -> DeviceCredential:
        if not device_id.strip() or not device_type.strip():
            raise ValueError("device_id and device_type are required")
        with self._lock:
            if device_id in self._devices and self._devices[device_id].enabled:
                raise ValueError(f"Device already enrolled: {device_id}")
            now = datetime.now(UTC).isoformat()
            credential = DeviceCredential(
                device_id=device_id,
                device_type=device_type,
                credential_id=secrets.token_urlsafe(24),
                created_at=now,
                updated_at=now,
                owner=owner,
                expires_at=(
                    time.time() + self.credential_lifetime_seconds
                    if self.credential_lifetime_seconds
                    else None
                ),
            )
            self._devices[device_id] = credential
            return credential

    def _transition(self, device_id: str, status: str) -> DeviceCredential:
        with self._lock:
            current = self._devices[device_id]
            if current.status in TERMINAL_STATES and status != current.status:
                raise ValueError("Terminal device state cannot transition")
            updated = replace(
                current,
                status=status,
                enabled=status == ACTIVE,
                updated_at=datetime.now(UTC).isoformat(),
            )
            self._devices[device_id] = updated
            return updated

    def suspend(self, device_id: str) -> DeviceCredential:
        return self._transition(device_id, SUSPENDED)

    def activate(self, device_id: str) -> DeviceCredential:
        if self._devices[device_id].status in TERMINAL_STATES:
            raise ValueError("Terminal device state cannot be reactivated")
        return self._transition(device_id, ACTIVE)

    def report_lost(self, device_id: str) -> DeviceCredential:
        return self._transition(device_id, LOST)

    def revoke(self, device_id: str) -> None:
        if device_id not in self._devices:
            raise KeyError(device_id)
        self._transition(device_id, REVOKED)

    def rotate(self, device_id: str) -> DeviceCredential:
        with self._lock:
            current = self._devices[device_id]
            if current.status != ACTIVE:
                raise ValueError("Only active credentials can rotate")
            updated = replace(
                current,
                credential_id=secrets.token_urlsafe(24),
                generation=current.generation + 1,
                expires_at=(
                    time.time() + self.credential_lifetime_seconds
                    if self.credential_lifetime_seconds
                    else None
                ),
                updated_at=datetime.now(UTC).isoformat(),
            )
            self._devices[device_id] = updated
            return updated

    def replace(self, device_id: str, replacement_id: str) -> DeviceCredential:
        current = self._devices[device_id]
        replacement = self.enroll(
            replacement_id, current.device_type, current.owner
        )
        self._devices[device_id] = replace(
            current,
            status=DECOMMISSIONED,
            enabled=False,
            replaced_by=replacement_id,
        )
        return replacement

    def decommission(self, device_id: str) -> DeviceCredential:
        return self._transition(device_id, DECOMMISSIONED)

    def authorize(self, device_id: str) -> bool:
        with self._lock:
            credential = self._devices.get(device_id)
            return bool(
                credential
                and credential.enabled
                and credential.status == ACTIVE
                and (
                    credential.expires_at is None
                    or credential.expires_at > time.time()
                )
            )

    def authorize_credential(self, device_id: str, credential_id: str) -> bool:
        with self._lock:
            credential = self._devices.get(device_id)
            return bool(
                credential
                and secrets.compare_digest(credential.credential_id, credential_id)
                and self.authorize(device_id)
            )

    def get(self, device_id: str) -> DeviceCredential:
        with self._lock:
            return self._devices[device_id]

    def expiring_within(self, seconds: float) -> tuple[DeviceCredential, ...]:
        if seconds < 0:
            raise ValueError("seconds cannot be negative")
        deadline = time.time() + seconds
        with self._lock:
            return tuple(
                credential
                for credential in self._devices.values()
                if credential.status == ACTIVE
                and credential.expires_at is not None
                and credential.expires_at <= deadline
            )
