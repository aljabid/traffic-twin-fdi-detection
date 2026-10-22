import pytest

from smart_city_security.contracts import SchemaRegistry


def require_name(payload):
    if not isinstance(payload.get("name"), str):
        raise TypeError("name required")


def require_enabled(payload):
    require_name(payload)
    if not isinstance(payload.get("enabled"), bool):
        raise TypeError("enabled required")


def test_registry_validates_and_migrates_sequentially():
    registry = SchemaRegistry()
    registry.register("device", 1, require_name)
    registry.register("device", 2, require_enabled)
    registry.register_migration(
        "device", 1, lambda payload: {**payload, "enabled": True}
    )
    version, payload = registry.migrate("device", 1, {"name": "sensor"})
    assert version == 2
    assert payload == {"name": "sensor", "enabled": True}


def test_registry_rejects_missing_migration_and_duplicates():
    registry = SchemaRegistry()
    registry.register("event", 1, lambda payload: None)
    registry.register("event", 2, lambda payload: None)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("event", 1, lambda payload: None)
    with pytest.raises(ValueError, match="Missing migration"):
        registry.migrate("event", 1, {})
