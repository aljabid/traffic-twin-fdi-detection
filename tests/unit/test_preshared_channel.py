import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.pqc import DeviceKey, PreSharedKeyChannel
from smart_city_security.pqc.preshared_channel import ALGORITHM
from smart_city_security.pqc.replay_guard import ReplayError
from smart_city_security.pqc.secure_channel import AuthenticationError


def _provision(device_id: str) -> tuple[DeviceKey, bytes, bytes]:
    aes_key = os.urandom(32)
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return DeviceKey(device_id, aes_key, public_pem), aes_key, private_pem


def _telemetry(device_id: str):
    message = TrafficGenerator(1, seed=3).generate(1)[0]
    from dataclasses import replace

    return replace(message, device_id=device_id)


def test_device_key_rejects_wrong_length():
    with pytest.raises(ValueError):
        DeviceKey("d", b"short", b"pem")


def test_round_trip_protect_then_unprotect():
    key, aes_key, private_pem = _provision("wokwi-esp32-01")
    channel = PreSharedKeyChannel([key])
    telemetry = _telemetry("wokwi-esp32-01")

    message = channel.protect(telemetry, aes_key, private_pem, timestamp=1_000_000)
    assert message.algorithm == ALGORITHM

    restored = channel.unprotect(message, now=1_000_000)
    assert restored == telemetry


def test_unknown_device_is_rejected():
    key, aes_key, private_pem = _provision("known")
    channel = PreSharedKeyChannel([key])
    telemetry = _telemetry("stranger")
    message = channel.protect(telemetry, aes_key, private_pem, timestamp=1_000_000)
    with pytest.raises(AuthenticationError, match="Unknown device"):
        channel.unprotect(message, now=1_000_000)


def test_tampered_signature_is_rejected():
    key, aes_key, private_pem = _provision("d1")
    channel = PreSharedKeyChannel([key])
    message = channel.protect(_telemetry("d1"), aes_key, private_pem, timestamp=1_000_000)
    message.signature = message.signature[:-1] + bytes([message.signature[-1] ^ 0x01])
    with pytest.raises(AuthenticationError, match="Invalid message signature"):
        channel.unprotect(message, now=1_000_000)


def test_wrong_aes_key_fails_decrypt():
    key, _aes_key, private_pem = _provision("d1")
    channel = PreSharedKeyChannel([key])
    message = channel.protect(_telemetry("d1"), os.urandom(32), private_pem, timestamp=1_000_000)
    with pytest.raises(AuthenticationError, match="Ciphertext authentication failed"):
        channel.unprotect(message, now=1_000_000)


def test_replay_is_rejected():
    key, aes_key, private_pem = _provision("d1")
    channel = PreSharedKeyChannel([key])
    message = channel.protect(_telemetry("d1"), aes_key, private_pem, timestamp=1_000_000)
    channel.unprotect(message, now=1_000_000)
    with pytest.raises(ReplayError):
        channel.unprotect(message, now=1_000_000)


def test_stale_timestamp_is_rejected():
    key, aes_key, private_pem = _provision("d1")
    channel = PreSharedKeyChannel([key], replay_tolerance_seconds=30)
    message = channel.protect(_telemetry("d1"), aes_key, private_pem, timestamp=1_000_000)
    with pytest.raises(ReplayError):
        channel.unprotect(message, now=1_000_100)
