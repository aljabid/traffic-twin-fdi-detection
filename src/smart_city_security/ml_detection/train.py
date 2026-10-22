from __future__ import annotations

from pathlib import Path
from typing import cast

import joblib
import numpy as np

from .baselines import EWMAResidualDetector, LOFDetector, MahalanobisDetector
from .deep_models import AutoencoderDetector
from .interfaces import AnomalyDetector
from .ml_models import IsolationForestDetector
from .statistical_baseline import OneClassDetector

_Trainable = (
    IsolationForestDetector
    | AutoencoderDetector
    | OneClassDetector
    | LOFDetector
    | MahalanobisDetector
    | EWMAResidualDetector
)


def train_detector(
    model: str,
    features: np.ndarray,
    *,
    contamination: float = 0.15,
    seed: int = 42,
) -> AnomalyDetector:
    detector: _Trainable
    if model == "isolation_forest":
        detector = IsolationForestDetector(contamination, seed)
    elif model == "autoencoder":
        detector = AutoencoderDetector(contamination, seed)
    elif model in {"one_class_svm", "ocsvm"}:
        detector = OneClassDetector(contamination)
    elif model == "lof":
        detector = LOFDetector(contamination)
    elif model == "mahalanobis":
        detector = MahalanobisDetector(contamination, seed)
    elif model == "ewma_residual":
        detector = EWMAResidualDetector(contamination)
    else:
        raise ValueError(f"Unknown ML model: {model}")
    return detector.fit(features)


def save_detector(detector: AnomalyDetector, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(detector, path)
    return path


def load_detector(path: str | Path) -> AnomalyDetector:
    return cast(AnomalyDetector, joblib.load(path))


def train_models(
    rows: np.ndarray,
) -> tuple[IsolationForestDetector, AutoencoderDetector]:
    return IsolationForestDetector().fit(rows), AutoencoderDetector().fit(rows)
