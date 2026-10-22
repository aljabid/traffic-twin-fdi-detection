from __future__ import annotations

import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM


class OneClassDetector:
    name = "one_class_svm"

    def __init__(self, contamination: float = 0.15):
        self.pipeline = Pipeline(
            [
                ("scale", StandardScaler()),
                ("svm", OneClassSVM(nu=contamination)),
            ]
        )
        self.fitted = False

    def fit(self, features: np.ndarray) -> OneClassDetector:
        self.pipeline.fit(features)
        self.fitted = True
        return self

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not self.fitted:
            raise RuntimeError("Detector has not been fitted")
        labels = self.pipeline.predict(features)
        scores = -self.pipeline.decision_function(features)
        return labels == -1, scores
