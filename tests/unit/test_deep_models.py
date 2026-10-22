import numpy as np
import pytest

from smart_city_security.ml_detection.deep_models import AutoencoderDetector


def _normal_block(rows: int = 60) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.normal(loc=0.0, scale=1.0, size=(rows, 4))


def test_fit_requires_minimum_samples():
    detector = AutoencoderDetector()
    with pytest.raises(ValueError):
        detector.fit(np.zeros((3, 4)))


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError):
        AutoencoderDetector().predict(np.zeros((1, 4)))


def test_fit_sets_model_and_threshold():
    detector = AutoencoderDetector(contamination=0.1, seed=1).fit(_normal_block())
    assert detector.model is not None
    assert detector.threshold is not None
    assert detector.threshold >= 0.0


def test_predict_shapes_and_flags_outlier():
    train = _normal_block()
    detector = AutoencoderDetector(contamination=0.1, seed=1).fit(train)

    probe = np.vstack([train[:5], np.full((1, 4), 25.0)])
    labels, scores = detector.predict(probe)

    assert labels.shape == (6,)
    assert scores.shape == (6,)
    assert bool(labels[-1]) is True
    assert scores[-1] > scores[:-1].max()


def test_small_training_set_disables_early_stopping():
    detector = AutoencoderDetector(seed=1).fit(_normal_block(rows=10))
    assert detector.model is not None
    assert detector.model.early_stopping is False
