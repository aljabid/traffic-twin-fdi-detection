from __future__ import annotations

from collections.abc import Callable, Iterable
from statistics import fmean, median, stdev

import numpy as np


def summarize_runs(values: Iterable[float]) -> dict[str, float]:
    values_array = np.asarray(list(values), dtype=float)
    if values_array.size == 0 or not np.isfinite(values_array).all():
        raise ValueError("values must be non-empty and finite")
    mean = fmean(values_array)
    standard_deviation = stdev(values_array) if values_array.size > 1 else 0.0
    margin = 1.96 * standard_deviation / (values_array.size**0.5)
    return {
        "n": int(values_array.size),
        "mean": mean,
        "median": median(values_array),
        "std": standard_deviation,
        "minimum": float(np.min(values_array)),
        "maximum": float(np.max(values_array)),
        "ci95_low": mean - margin,
        "ci95_high": mean + margin,
    }


def bootstrap_confidence_interval(
    values: Iterable[float],
    *,
    statistic: Callable[[list[float]], float] = fmean,
    confidence: float = 0.95,
    resamples: int = 2_000,
    seed: int = 42,
) -> dict[str, float | int]:
    samples = np.asarray(list(values), dtype=float)
    if samples.size < 2 or not np.isfinite(samples).all():
        raise ValueError("at least two finite values are required")
    if not 0 < confidence < 1 or resamples < 100:
        raise ValueError("invalid confidence or resample count")
    generator = np.random.default_rng(seed)
    estimates = np.empty(resamples)
    for index in range(resamples):
        draw = generator.choice(samples, size=samples.size, replace=True)
        estimates[index] = float(statistic(draw.tolist()))
    alpha = (1 - confidence) / 2
    return {
        "estimate": float(statistic(samples.tolist())),
        "confidence": confidence,
        "low": float(np.quantile(estimates, alpha)),
        "high": float(np.quantile(estimates, 1 - alpha)),
        "resamples": resamples,
        "seed": seed,
    }
