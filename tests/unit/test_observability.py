import json
import logging

from smart_city_security.observability import JsonFormatter, MetricsRegistry


def test_json_formatter_and_metrics():
    record = logging.LogRecord("test", logging.INFO, "", 1, "hello", (), None)
    assert json.loads(JsonFormatter().format(record))["message"] == "hello"
    metrics = MetricsRegistry()
    metrics.increment("messages")
    metrics.observe("latency_ms", 10)
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["messages"] == 1
    assert snapshot["observations"]["latency_ms"]["p95"] == 10
