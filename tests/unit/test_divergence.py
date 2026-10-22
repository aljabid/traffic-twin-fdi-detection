from smart_city_security.digital_twin.divergence import absolute_divergence


def test_absolute_divergence():
    assert absolute_divergence(10, 7) == 3
