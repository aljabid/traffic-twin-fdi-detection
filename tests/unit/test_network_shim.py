from smart_city_security.network.network_shim import NetworkShim


def test_network_shim_returns_transmission():
    result = NetworkShim("ideal", seed=1).transmit(b"x")
    assert result.delay_ms >= 0
    assert result.delivered in (True, False)
