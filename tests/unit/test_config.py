import pytest

from smart_city_security.config import load_config, validate_config


def test_base_configuration_is_valid():
    assert load_config("configs/base.yaml")["simulation"]["devices"] > 0


def test_invalid_attack_ratio_is_rejected():
    config = load_config("configs/test.yaml")
    config["simulation"]["attack_ratio"] = 2
    with pytest.raises(ValueError, match="attack_ratio"):
        validate_config(config)


@pytest.mark.parametrize(
    "path",
    [
        "configs/development.yaml",
        "configs/security-test.yaml",
        "configs/staging.yaml",
        "configs/pilot.yaml",
        "configs/production.yaml",
        "configs/disaster-recovery.yaml",
        "configs/acceptance.yaml",
    ],
)
def test_environment_configuration_is_valid(path):
    assert load_config(path)["deployment"]["environment"]
