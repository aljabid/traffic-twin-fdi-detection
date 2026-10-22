from __future__ import annotations

from typing import Protocol

import numpy as np


class AnomalyDetector(Protocol):

    name: str

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]: ...
