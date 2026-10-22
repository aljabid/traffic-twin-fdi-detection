import math

import pytest

from smart_city_security.ml_detection.drift import DriftMonitor


def test_drift_monitor_detects_shift():
    monitor = DriftMonitor().fit([1, 1, 1, 1])
    assert monitor.drifted([10, 10, 10, 10])


def test_constructor_rejects_bad_parameters():
    with pytest.raises(ValueError):
        DriftMonitor(window=3)
    with pytest.raises(ValueError):
        DriftMonitor(bins=1)


def test_fit_requires_four_finite_values():
    with pytest.raises(ValueError):
        DriftMonitor().fit([1, 2, 3])
    with pytest.raises(ValueError):
        DriftMonitor().fit([1.0, 2.0, 3.0, math.nan])


def test_evaluate_without_fit_reports_no_drift():
    result = DriftMonitor().evaluate([1, 2, 3, 4])
    assert result.drifted is False
    assert result.reference_count == 0
    assert result.normalized_mean_shift == 0.0


def test_evaluate_flags_non_finite_current_window():
    monitor = DriftMonitor().fit([1.0, 1.1, 0.9, 1.0, 1.05])
    result = monitor.evaluate([1.0, math.inf, 1.0, 1.0, 1.0])
    assert result.drifted is True
    assert math.isinf(result.normalized_mean_shift)


def test_stable_stream_is_not_flagged_and_psi_is_finite():
    reference = [float(x % 7) for x in range(200)]
    monitor = DriftMonitor(window=200).fit(reference)
    result = monitor.evaluate(reference)
    assert result.drifted is False
    assert result.population_stability_index < monitor.psi_threshold


def test_score_returns_normalized_mean_shift():
    monitor = DriftMonitor().fit([1, 1, 1, 1, 1])
    assert monitor.score([1, 1, 1, 1, 1]) == pytest.approx(0.0, abs=1e-6)
    assert monitor.score([5, 5, 5, 5, 5]) > 0
