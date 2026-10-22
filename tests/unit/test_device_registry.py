from smart_city_security.security.device_registry import DeviceRegistry


def test_device_enrollment_and_revocation():
    registry = DeviceRegistry()
    credential = registry.enroll("device-1", "vehicle")
    assert credential.credential_id and registry.authorize("device-1")
    registry.revoke("device-1")
    assert not registry.authorize("device-1")
