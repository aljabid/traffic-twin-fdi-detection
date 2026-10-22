from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .interfaces import AnomalyDetector
from .train import train_detector

DEFAULT_CONTAMINATION_GRID = (0.01, 0.02, 0.03, 0.05, 0.08, 0.12)


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    model: str
    contamination: float
    self_false_positive_rate: float
    samples: int
    budget_met: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "contamination": self.contamination,
            "self_false_positive_rate": self.self_false_positive_rate,
            "samples": self.samples,
            "budget_met": self.budget_met,
        }


class DetectorCalibrator:
    def __init__(
        self,
        model: str,
        *,
        target_false_positive_rate: float = 0.05,
        contamination_grid: Sequence[float] = DEFAULT_CONTAMINATION_GRID,
        seed: int = 42,
    ) -> None:
        if not 0.0 < target_false_positive_rate < 1.0:
            raise ValueError("target_false_positive_rate must be in (0, 1)")
        if not contamination_grid:
            raise ValueError("contamination_grid must be non-empty")
        self.model = model
        self.target_fpr = target_false_positive_rate
        self.contamination_grid = tuple(sorted(contamination_grid))
        self.seed = seed
        self._features: list[np.ndarray] = []

    @property
    def count(self) -> int:
        return len(self._features)

    def add(self, feature_values: np.ndarray) -> None:
        self._features.append(np.asarray(feature_values, dtype=float))

    def ready(self, warmup_messages: int) -> bool:
        return self.count >= warmup_messages

    def fit(self) -> tuple[AnomalyDetector, CalibrationResult]:
        if self.count < 4:
            raise ValueError("at least 4 warm-up samples are required to calibrate")
        matrix = np.vstack(self._features)

        within_budget: tuple[float, float, AnomalyDetector] | None = None
        least_aggressive: tuple[float, float, AnomalyDetector] | None = None
        for contamination in self.contamination_grid:
            detector = train_detector(
                self.model, matrix, contamination=contamination, seed=self.seed
            )
            labels, _ = detector.predict(matrix)
            self_fpr = float(np.mean(np.asarray(labels, dtype=bool)))
            if least_aggressive is None:
                least_aggressive = (contamination, self_fpr, detector)
            if self_fpr <= self.target_fpr:
                within_budget = (contamination, self_fpr, detector)

        if within_budget is not None:
            contamination, self_fpr, detector = within_budget
            budget_met = True
        elif least_aggressive is not None:
            contamination, self_fpr, detector = least_aggressive
            budget_met = False
        else:
            raise RuntimeError("contamination_grid produced no candidates")

        result = CalibrationResult(
            model=self.model,
            contamination=contamination,
            self_false_positive_rate=self_fpr,
            samples=int(matrix.shape[0]),
            budget_met=budget_met,
        )
        return detector, result
