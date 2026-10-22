from __future__ import annotations

import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler


class AutoencoderDetector:

    name = "autoencoder"

    def __init__(
        self,
        contamination: float = 0.15,
        seed: int = 42,
        hidden_size: int | None = None,
    ):
        self.contamination = contamination
        self.seed = seed
        self.hidden_size = hidden_size
        self.scaler = StandardScaler()
        self.model: MLPRegressor | None = None
        self.threshold: float | None = None

    def fit(self, features: np.ndarray) -> AutoencoderDetector:
        if len(features) < 4:
            raise ValueError("At least four training samples are required")
        scaled = self.scaler.fit_transform(features)
        width = self.hidden_size or max(2, features.shape[1] // 2)
        self.model = MLPRegressor(
            hidden_layer_sizes=(width,),
            activation="relu",
            max_iter=500,
            random_state=self.seed,
            early_stopping=len(features) >= 20,
        )
        self.model.fit(scaled, scaled)
        errors = np.mean((self.model.predict(scaled) - scaled) ** 2, axis=1)
        self.threshold = float(np.quantile(errors, 1 - self.contamination))
        return self

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.model is None or self.threshold is None:
            raise RuntimeError("Detector has not been fitted")
        scaled = self.scaler.transform(features)
        errors = np.mean((self.model.predict(scaled) - scaled) ** 2, axis=1)
        return errors > self.threshold, errors
