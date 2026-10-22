import numpy as np
import pytest

from smart_city_security.ml_detection.baselines import (
    EWMAResidualDetector,
    LOFDetector,
    MahalanobisDetector,
)


def _blob(rows: int = 200, cols: int = 7, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 1.0, size=(rows, cols))


@pytest.mark.parametrize("cls", [LOFDetector, MahalanobisDetector, EWMAResidualDetector])
def test_baseline_rejects_bad_contamination(cls):
    with pytest.raises(ValueError):
        cls(contamination=0.0)
    with pytest.raises(ValueError):
        cls(contamination=0.6)


@pytest.mark.parametrize("cls", [LOFDetector, MahalanobisDetector, EWMAResidualDetector])
def test_baseline_predict_before_fit_raises(cls):
    with pytest.raises(RuntimeError):
        cls().predict(_blob(5))


@pytest.mark.parametrize("cls", [LOFDetector, MahalanobisDetector, EWMAResidualDetector])
def test_baseline_flags_outliers_and_shapes(cls):
    train = _blob(seed=1)
    detector = cls(contamination=0.1).fit(train)
    probe = np.vstack([train[:10], np.full((3, 7), 8.0)])
    labels, scores = detector.predict(probe)
    assert labels.shape == (13,)
    assert scores.shape == (13,)
    assert labels[-3:].all()
    assert labels[:10].mean() < 0.3


def test_train_detector_exposes_baselines():
    from smart_city_security.ml_detection import train_detector

    for name in ("lof", "mahalanobis", "ewma_residual"):
        detector = train_detector(name, _blob(seed=2), contamination=0.1)
        assert detector.name == name
        labels, _ = detector.predict(_blob(10, seed=3))
        assert labels.shape == (10,)
