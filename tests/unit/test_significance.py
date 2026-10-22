import pytest

from smart_city_security.evaluation.significance import bootstrap_mean_ci, paired_compare


def test_paired_compare_requires_equal_length():
    with pytest.raises(ValueError):
        paired_compare([1.0, 2.0], [1.0], metric="f1")


def test_paired_compare_detects_a_consistent_improvement():
    a = [0.5, 0.52, 0.48, 0.51, 0.49, 0.50]
    b = [0.7, 0.72, 0.68, 0.71, 0.69, 0.70]
    result = paired_compare(a, b, metric="f1")
    assert result.n_pairs == 6
    assert result.mean_diff == pytest.approx(0.2, abs=1e-6)
    assert result.ci95_low > 0.0
    assert result.wilcoxon_p is not None
    assert result.significant_at_05 is True


def test_paired_compare_no_difference_is_not_significant():
    a = [0.5, 0.5, 0.5, 0.5]
    b = [0.5, 0.5, 0.5, 0.5]
    result = paired_compare(a, b, metric="f1")
    assert result.mean_diff == 0.0
    assert result.wilcoxon_p is None
    assert result.significant_at_05 is False


def test_paired_compare_noisy_difference_is_not_necessarily_significant():
    a = [0.50, 0.80, 0.30, 0.60, 0.40]
    b = [0.55, 0.75, 0.35, 0.55, 0.60]
    result = paired_compare(a, b, metric="f1")
    assert result.n_pairs == 5
    assert result.ci95_low <= 0.0 <= result.ci95_high or not result.significant_at_05


def test_bootstrap_mean_ci_bounds_contain_the_mean():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    low, high = bootstrap_mean_ci(values, seed=1)
    assert low <= sum(values) / len(values) <= high


def test_bootstrap_mean_ci_empty_is_zero():
    assert bootstrap_mean_ci([]) == (0.0, 0.0)


def test_holm_matches_hand_computation():
    from smart_city_security.evaluation import holm_adjust

    assert holm_adjust([0.04, 0.01, 0.02]) == pytest.approx([0.04, 0.03, 0.04])
    assert holm_adjust([0.5, 0.9]) == pytest.approx([1.0, 1.0])


def test_bh_matches_hand_computation():
    from smart_city_security.evaluation import bh_adjust

    assert bh_adjust([0.2, 0.01, 0.03, 0.02]) == pytest.approx([0.2, 0.04, 0.04, 0.04])


def test_adjustments_never_shrink_p_values():
    from smart_city_security.evaluation import bh_adjust, holm_adjust

    p = [0.001, 0.2, 0.03, 0.5, 0.04]
    for adjusted in (holm_adjust(p), bh_adjust(p)):
        assert all(a >= raw for a, raw in zip(adjusted, p, strict=True))
        assert all(a <= 1.0 for a in adjusted)
