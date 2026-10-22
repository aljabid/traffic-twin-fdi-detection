from __future__ import annotations

import os
import time
from pathlib import Path
from threading import RLock
from typing import Protocol


class SecretProvider(Protocol):
    def get(self, name: str) -> str: ...


class EnvironmentSecretProvider:
    def __init__(self, prefix: str = "SMART_CITY_"):
        self.prefix = prefix

    def get(self, name: str) -> str:
        key = f"{self.prefix}{name}".upper()
        try:
            return os.environ[key]
        except KeyError as exc:
            raise KeyError(f"Required secret is not set: {key}") from exc


class DockerSecretProvider:
    def __init__(self, directory: str | Path = "/run/secrets"):
        self.directory = Path(directory)

    def get(self, name: str) -> str:
        path = self.directory / name
        if not path.is_file():
            raise KeyError(f"Required Docker secret is unavailable: {name}")
        return path.read_text(encoding="utf-8").strip()


class ChainedSecretProvider:

    def __init__(self, *providers: SecretProvider):
        if not providers:
            raise ValueError("At least one secret provider is required")
        self.providers = providers

    def get(self, name: str) -> str:
        failures = []
        for provider in self.providers:
            try:
                return provider.get(name)
            except KeyError:
                failures.append(type(provider).__name__)
        raise KeyError(f"Secret {name!r} unavailable from providers: {failures}")


class CachingSecretProvider:

    def __init__(self, provider: SecretProvider, ttl_seconds: float = 30):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.provider = provider
        self.ttl_seconds = ttl_seconds
        self._values: dict[str, tuple[str, float]] = {}
        self._lock = RLock()

    def get(self, name: str) -> str:
        now = time.monotonic()
        with self._lock:
            cached = self._values.get(name)
            if cached and cached[1] > now:
                return cached[0]
        value = self.provider.get(name)
        with self._lock:
            self._values[name] = (value, now + self.ttl_seconds)
        return value

    def invalidate(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self._values.clear()
            else:
                self._values.pop(name, None)
