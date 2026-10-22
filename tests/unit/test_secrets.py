import pytest

from smart_city_security.security.secrets import (
    CachingSecretProvider,
    ChainedSecretProvider,
    EnvironmentSecretProvider,
)


def test_environment_secret_provider(monkeypatch):
    monkeypatch.setenv("SMART_CITY_BROKER_PASSWORD", "secret")
    provider = EnvironmentSecretProvider()
    assert provider.get("broker_password") == "secret"
    with pytest.raises(KeyError):
        provider.get("missing")


def test_chained_and_cached_secret_rotation(monkeypatch):
    monkeypatch.setenv("SMART_CITY_VALUE", "old")
    source = EnvironmentSecretProvider()
    provider = CachingSecretProvider(ChainedSecretProvider(source), ttl_seconds=60)
    assert provider.get("value") == "old"
    monkeypatch.setenv("SMART_CITY_VALUE", "new")
    assert provider.get("value") == "old"
    provider.invalidate("value")
    assert provider.get("value") == "new"
