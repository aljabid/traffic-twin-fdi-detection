from smart_city_security.evaluation import PowerSample, calculate_energy


def test_energy_uses_trapezoidal_integration_and_meter_metadata():
    report = calculate_energy(
        [PowerSample(0, 5, 1), PowerSample(2, 5, 3)],
        meter_id="meter-1",
        calibration_reference="certificate-123",
    )
    assert report.energy_joules == 20
    assert report.mean_power_watts == 10
    assert report.peak_power_watts == 15
