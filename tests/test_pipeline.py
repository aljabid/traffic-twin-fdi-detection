import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_city_security.config import load_config
from smart_city_security.integration.pipeline import SecurityPipeline


def test_pipeline_smoke():
    config = load_config("configs/test.yaml")
    result = SecurityPipeline(config).run()
    assert result.system_metrics.sent > 0
    assert result.system_metrics.delivered > 0
    assert result.feature_names
    assert "speed_divergence" in result.feature_names
