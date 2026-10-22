import pytest

from smart_city_security.security.device_registry import DeviceRegistry


def test_complete_device_lifecycle():
    registry = DeviceRegistry()
    first = registry.enroll("d1", "vehicle", owner="city")
    rotated = registry.rotate("d1")
    assert rotated.generation == first.generation + 1
    registry.suspend("d1")
    assert not registry.authorize("d1")
    registry.activate("d1")
    replacement = registry.replace("d1", "d2")
    assert registry.get("d1").replaced_by == "d2"
    assert registry.authorize(replacement.device_id)
    with pytest.raises(ValueError):
        registry.activate("d1")


def test_credential_identity_and_expiry_are_enforced():
    registry = DeviceRegistry(credential_lifetime_seconds=60)
    credential = registry.enroll("sensor", "road")
    assert registry.authorize_credential("sensor", credential.credential_id)
    assert not registry.authorize_credential("sensor", "wrong")
    assert registry.expiring_within(120) == (credential,)
