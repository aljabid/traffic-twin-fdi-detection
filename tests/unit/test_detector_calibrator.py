import numpy as np
import pytest

from smart_city_security.ml_detection.calibration import (
    CalibrationResult,
    DetectorCalibrator,
)


def _clean_features(rows: int = 80) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.normal(0.0, 1.0, size=(rows, 6))


def test_rejects_bad_configuration():
    with pytest.raises(ValueError):
        DetectorCalibrator("isolation_forest", target_false_positive_rate=0.0)
    with pytest.raises(ValueError):
        DetectorCalibrator("isolation_forest", contamination_grid=())


def test_add_count_and_ready():
    calibrator = DetectorCalibrator("isolation_forest")
    assert calibrator.ready(5) is False
    for row in _clean_features(5):
        calibrator.add(row)
    assert calibrator.count == 5
    assert calibrator.ready(5) is True


def test_fit_requires_minimum_samples():
    calibrator = DetectorCalibrator("isolation_forest")
    for row in _clean_features(3):
        calibrator.add(row)
    with pytest.raises(ValueError):
        calibrator.fit()


def test_fit_selects_operating_point_within_budget():
    calibrator = DetectorCalibrator(
        "isolation_forest", target_false_positive_rate=0.05, seed=1
    )
    for row in _clean_features(120):
        calibrator.add(row)

    detector, result = calibrator.fit()

    assert isinstance(result, CalibrationResult)
    assert result.budget_met is True
    assert result.self_false_positive_rate <= 0.05
    assert result.samples == 120
    labels, _scores = detector.predict(_clean_features(10))
    assert labels.shape == (10,)


def test_fit_falls_back_when_budget_unreachable():
    calibrator = DetectorCalibrator(
        "isolation_forest",
        target_false_positive_rate=0.001,
        contamination_grid=(0.1, 0.2, 0.3),
        seed=1,
    )
    for row in _clean_features(60):
        calibrator.add(row)

    _detector, result = calibrator.fit()

    assert result.budget_met is False
    assert result.contamination == 0.1
    assert set(result.to_dict()) == {
        "model",
        "contamination",
        "self_false_positive_rate",
        "samples",
        "budget_met",
    }
