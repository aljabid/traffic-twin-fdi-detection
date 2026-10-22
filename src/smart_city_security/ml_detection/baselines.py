from __future__ import annotations

import numpy as np
from sklearn.covariance import EllipticEnvelope
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class LOFDetector:
    name = "lof"

    def __init__(self, contamination: float = 0.15, n_neighbors: int = 20) -> None:
        if not 0.0 < contamination < 0.5:
            raise ValueError("contamination must be between 0 and 0.5")
        self.contamination = contamination
        self.pipeline = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "lof",
                    LocalOutlierFactor(
                        n_neighbors=n_neighbors, contamination=contamination, novelty=True
                    ),
                ),
            ]
        )
        self._fitted = False

    def fit(self, features: np.ndarray) -> LOFDetector:
        if len(features) <= 20:
            raise ValueError("LOF needs more than n_neighbors training samples")
        self.pipeline.fit(features)
        self._fitted = True
        return self

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not self._fitted:
            raise RuntimeError("Detector has not been fitted")
        labels = self.pipeline.predict(features)
        scores = -self.pipeline.decision_function(features)
        return labels == -1, scores


class MahalanobisDetector:
    name = "mahalanobis"

    def __init__(self, contamination: float = 0.15, seed: int = 42) -> None:
        if not 0.0 < contamination < 0.5:
            raise ValueError("contamination must be between 0 and 0.5")
        self.contamination = contamination
        self.pipeline = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "envelope",
                    EllipticEnvelope(contamination=contamination, random_state=seed, support_fraction=0.9),
                ),
            ]
        )
        self._fitted = False

    def fit(self, features: np.ndarray) -> MahalanobisDetector:
        if len(features) < features.shape[1] + 2:
            raise ValueError("not enough samples to estimate a covariance")
        self.pipeline.fit(features)
        self._fitted = True
        return self

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not self._fitted:
            raise RuntimeError("Detector has not been fitted")
        labels = self.pipeline.predict(features)
        scores = -self.pipeline.decision_function(features)
        return labels == -1, scores


class EWMAResidualDetector:

    name = "ewma_residual"

    def __init__(self, contamination: float = 0.15, alpha: float = 0.3) -> None:
        if not 0.0 < contamination < 0.5:
            raise ValueError("contamination must be between 0 and 0.5")
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        self.contamination = contamination
        self.alpha = alpha
        self._center: np.ndarray | None = None
        self._mad: np.ndarray | None = None
        self._k: float | None = None

    def _scores(self, features: np.ndarray) -> np.ndarray:
        if self._center is None or self._mad is None:
            raise RuntimeError("Detector has not been fitted")
        z = np.abs(features - self._center) / self._mad
        return np.asarray(z.mean(axis=1), dtype=float)

    def fit(self, features: np.ndarray) -> EWMAResidualDetector:
        if len(features) < 4:
            raise ValueError("at least four training samples are required")
        ewma = features[0].astype(float)
        for row in features[1:]:
            ewma = self.alpha * row + (1 - self.alpha) * ewma
        median = np.median(features, axis=0)
        self._center = 0.5 * ewma + 0.5 * median
        self._mad = 1.4826 * np.median(np.abs(features - median), axis=0) + 1e-9
        scores = self._scores(features)
        self._k = float(np.quantile(scores, 1 - self.contamination))
        return self

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self._center is None or self._k is None:
            raise RuntimeError("Detector has not been fitted")
        scores = self._scores(features)
        return scores >= self._k, scores
