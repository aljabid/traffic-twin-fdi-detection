from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class IsolationForestDetector:
    name = "isolation_forest"

    def __init__(self, contamination: float = 0.15, seed: int = 42):
        if not 0 < contamination < 0.5:
            raise ValueError("contamination must be between 0 and 0.5")
        self.contamination = contamination
        self.pipeline = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    IsolationForest(
                        contamination=contamination,
                        random_state=seed,
                        n_estimators=150,
                    ),
                ),
            ]
        )
        self.fitted = False
        self.threshold: float | None = None

    def fit(self, features: np.ndarray) -> IsolationForestDetector:
        if len(features) < 2:
            raise ValueError("At least two training samples are required")
        self.pipeline.fit(features)
        training_scores = -self.pipeline.decision_function(features)
        self.threshold = float(
            np.quantile(training_scores, 1 - self.contamination)
        )
        self.fitted = True
        return self

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not self.fitted or self.threshold is None:
            raise RuntimeError("Detector has not been fitted")
        scores = -self.pipeline.decision_function(features)
        return scores >= self.threshold, scores
