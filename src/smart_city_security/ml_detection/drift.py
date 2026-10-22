from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class DriftResult:
    drifted: bool
    normalized_mean_shift: float
    population_stability_index: float
    reference_count: int
    current_count: int


class DriftMonitor:

    def __init__(
        self,
        window: int = 100,
        threshold: float = 0.25,
        *,
        psi_threshold: float = 0.2,
        bins: int = 10,
    ) -> None:
        if window < 4 or bins < 2:
            raise ValueError("window must be >=4 and bins >=2")
        self.window, self.threshold = window, threshold
        self.psi_threshold, self.bins = psi_threshold, bins
        self.reference: list[float] = []

    def fit(self, values: Iterable[float]) -> DriftMonitor:
        reference = np.asarray(list(values)[-self.window :], dtype=float)
        if reference.size < 4 or not np.isfinite(reference).all():
            raise ValueError("at least 4 finite reference values are required")
        self.reference = reference.tolist()
        return self

    def evaluate(self, values: Iterable[float]) -> DriftResult:
        current = np.asarray(list(values)[-self.window :], dtype=float)
        reference = np.asarray(self.reference, dtype=float)
        if reference.size == 0 or current.size == 0:
            return DriftResult(False, 0.0, 0.0, int(reference.size), int(current.size))
        if not np.isfinite(current).all():
            return DriftResult(True, math.inf, math.inf, int(reference.size), int(current.size))
        center = float(np.median(reference))
        mad = float(np.median(np.abs(reference - center))) * 1.4826
        scale = max(mad, float(np.std(reference)), 1e-9)
        shift = abs(float(np.mean(current)) - float(np.mean(reference))) / scale
        edges = np.unique(np.quantile(reference, np.linspace(0, 1, self.bins + 1)))
        if edges.size < 3:
            psi = 0.0 if np.allclose(current, reference[0]) else math.inf
        else:
            edges[0], edges[-1] = -math.inf, math.inf
            expected = np.histogram(reference, bins=edges)[0] / reference.size
            actual = np.histogram(current, bins=edges)[0] / current.size
            expected = np.clip(expected, 1e-6, None)
            actual = np.clip(actual, 1e-6, None)
            psi = float(np.sum((actual - expected) * np.log(actual / expected)))
        return DriftResult(
            shift > self.threshold or psi > self.psi_threshold,
            shift,
            psi,
            int(reference.size),
            int(current.size),
        )

    def score(self, values: Iterable[float]) -> float:
        return self.evaluate(values).normalized_mean_shift

    def drifted(self, values: Iterable[float]) -> bool:
        return self.evaluate(values).drifted
