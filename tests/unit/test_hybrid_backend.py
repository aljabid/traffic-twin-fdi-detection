from smart_city_security.pqc import ClassicalBackend, HybridBackend


def test_hybrid_backend_requires_both_signatures():
    backend = HybridBackend(ClassicalBackend(), ClassicalBackend())
    payload = b"telemetry"
    signature = backend.sign("device-1", payload)
    assert backend.verify("device-1", payload, signature)
    corrupted = signature[:-1] + bytes([signature[-1] ^ 1])
    assert not backend.verify("device-1", payload, corrupted)
    assert len(backend.establish_key("device-1").shared_key) == 32
