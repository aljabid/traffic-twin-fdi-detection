import pytest

from smart_city_security.resilience import CircuitBreaker, CircuitOpenError, RetryPolicy


def test_circuit_breaker_opens_after_failures():
    breaker = CircuitBreaker(failure_threshold=2)
    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("failed")))
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: True)


def test_retry_eventually_succeeds():
    calls = []

    def operation():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("temporary")
        return "ok"

    assert RetryPolicy(attempts=2, base_delay_seconds=0).execute(operation) == "ok"
