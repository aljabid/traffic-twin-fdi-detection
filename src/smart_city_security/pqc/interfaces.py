from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class BackendUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EstablishedKey:
    shared_key: bytes
    handshake_bytes: int


class CryptoBackend(ABC):
    name: str

    @abstractmethod
    def establish_key(self, device_id: str) -> EstablishedKey:
        raise NotImplementedError

    @abstractmethod
    def sign(self, device_id: str, payload: bytes) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def verify(self, device_id: str, payload: bytes, signature: bytes) -> bool:
        raise NotImplementedError

    @abstractmethod
    def public_key_size(self, device_id: str) -> int:
        raise NotImplementedError
