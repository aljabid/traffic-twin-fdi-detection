import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import numpy as np

from smart_city_security.ml_detection.ml_models import IsolationForestDetector


def test_isolation_forest_detector_round_trip():
    normal = np.asarray([[0.0, 0.1], [0.1, 0.0], [-0.1, 0.05], [0.05, -0.05]])
    detector = IsolationForestDetector(contamination=0.25, seed=1).fit(normal)
    predictions, scores = detector.predict(np.vstack([normal, [[20.0, 20.0]]]))
    assert len(predictions) == 5
    assert len(scores) == 5
