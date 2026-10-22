from smart_city_security.digital_twin.calibration import (
    CalibrationObservation,
    calibrate_by_location,
)


def test_calibration_reports_location_context_and_interval_coverage():
    observations = [
        CalibrationObservation("i1", "rush" if i < 5 else "normal", i, i, i + 1, i - 2, i + 2)
        for i in range(10)
    ]
    report = calibrate_by_location(observations)
    location = report["locations"]["i1"]
    assert report["passed"]
    assert location["mae"] == 1
    assert location["interval_coverage"] == 1
    assert set(location["context_bias"]) == {"normal", "rush"}
