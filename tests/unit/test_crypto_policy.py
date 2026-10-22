import pytest

from smart_city_security.pqc import (
    PILOT_HYBRID_SUITE,
    AlgorithmSuite,
    CryptographicPolicy,
)


def test_crypto_policy_negotiates_only_enabled_suites():
    disabled = AlgorithmSuite("legacy", ("RSA",), ("RSA",), "AES", "disabled")
    policy = CryptographicPolicy([PILOT_HYBRID_SUITE, disabled])
    selected = policy.negotiation(["legacy", PILOT_HYBRID_SUITE.suite_id])
    assert selected == PILOT_HYBRID_SUITE
    with pytest.raises(ValueError):
        policy.negotiation(["legacy"])
