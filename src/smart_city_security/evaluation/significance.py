from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats


@dataclass(frozen=True, slots=True)
class PairedComparison:
    metric: str
    n_pairs: int
    mean_a: float
    mean_b: float
    mean_diff: float
    ci95_low: float
    ci95_high: float
    wilcoxon_statistic: float | None
    wilcoxon_p: float | None
    significant_at_05: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "n_pairs": self.n_pairs,
            "mean_a": self.mean_a,
            "mean_b": self.mean_b,
            "mean_diff": self.mean_diff,
            "ci95_low": self.ci95_low,
            "ci95_high": self.ci95_high,
            "wilcoxon_statistic": self.wilcoxon_statistic,
            "wilcoxon_p": self.wilcoxon_p,
            "significant_at_05": self.significant_at_05,
        }


def bootstrap_mean_ci(
    values: Sequence[float], *, resamples: int = 5000, seed: int = 0, confidence: float = 0.95
) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    data = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    for i in range(resamples):
        means[i] = rng.choice(data, size=len(data), replace=True).mean()
    alpha = (1 - confidence) / 2
    low, high = np.quantile(means, [alpha, 1 - alpha])
    return float(low), float(high)


def paired_compare(
    values_a: Sequence[float], values_b: Sequence[float], *, metric: str, seed: int = 0
) -> PairedComparison:
    if len(values_a) != len(values_b):
        raise ValueError("paired samples must be the same length")
    a = np.asarray(values_a, dtype=float)
    b = np.asarray(values_b, dtype=float)
    diffs = b - a
    n = len(diffs)

    wilcoxon_stat: float | None = None
    wilcoxon_p: float | None = None
    if n >= 2 and not np.allclose(diffs, 0.0):
        try:
            result = stats.wilcoxon(b, a)
            wilcoxon_stat, wilcoxon_p = float(result.statistic), float(result.pvalue)
        except ValueError:
            pass

    ci_low, ci_high = bootstrap_mean_ci(diffs.tolist(), seed=seed)
    return PairedComparison(
        metric=metric,
        n_pairs=n,
        mean_a=float(a.mean()) if n else 0.0,
        mean_b=float(b.mean()) if n else 0.0,
        mean_diff=float(diffs.mean()) if n else 0.0,
        ci95_low=ci_low,
        ci95_high=ci_high,
        wilcoxon_statistic=wilcoxon_stat,
        wilcoxon_p=wilcoxon_p,
        significant_at_05=(wilcoxon_p is not None and wilcoxon_p < 0.05),
    )


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def bh_adjust(p_values: Sequence[float]) -> list[float]:
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i], reverse=True)
    adjusted = [0.0] * m
    running = 1.0
    for k, i in enumerate(order):
        rank = m - k
        running = min(running, p_values[i] * m / rank)
        adjusted[i] = min(1.0, running)
    return adjusted
