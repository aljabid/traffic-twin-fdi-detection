import pytest

from smart_city_security.ml_detection.registry import ModelRegistry


def test_model_registry_enforces_promotion_sequence(tmp_path):
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"model")
    registry = ModelRegistry(tmp_path / "registry.json")
    registry.register("detector", "1", artifact, "features-v1", "dataset-v1")
    with pytest.raises(ValueError, match="Invalid"):
        registry.transition("detector", "1", "production")
    for status in ("approved", "shadow", "canary", "production"):
        registry.transition("detector", "1", status)
    assert registry.production("detector").version == "1"
