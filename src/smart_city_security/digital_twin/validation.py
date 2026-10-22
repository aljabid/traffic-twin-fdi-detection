from __future__ import annotations

from collections.abc import Iterable
from math import sqrt
from statistics import NormalDist, fmean

import numpy as np


def prediction_metrics(
    predicted: Iterable[float], observed: Iterable[float], *, confidence: float = 0.95
) -> dict[str, float]:
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1 exclusive")
    predicted_values = np.asarray(list(predicted), dtype=float)
    observed_values = np.asarray(list(observed), dtype=float)
    if (
        predicted_values.size != observed_values.size
        or predicted_values.size == 0
        or not np.isfinite(predicted_values).all()
        or not np.isfinite(observed_values).all()
    ):
        raise ValueError("equal non-empty finite sequences required")
    errors = predicted_values - observed_values
    absolute = np.abs(errors)
    mae = float(np.mean(absolute))
    rmse = sqrt(float(np.mean(errors**2)))
    bias = float(np.mean(errors))
    standard_error = float(np.std(errors, ddof=1) / sqrt(errors.size)) if errors.size > 1 else 0
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    return {
        "n": int(errors.size),
        "mae": mae,
        "rmse": rmse,
        "bias": bias,
        "error_std": float(np.std(errors)),
        "bias_ci_low": bias - z * standard_error,
        "bias_ci_high": bias + z * standard_error,
        "observed_mean": fmean(observed_values.tolist()),
    }
