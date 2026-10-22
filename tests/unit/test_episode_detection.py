import math
from dataclasses import replace

import pytest

from smart_city_security.integration.episode_detection import (
    _persistent,
    episode_metrics,
    false_alarms_per_hour,
    run_unit,
)
from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.iot_sim.adversary import CONGESTION_SPOOF, AdversarialCampaign


def _device(n=12, device="d1"):
    base = TrafficGenerator(1, seed=4).generate(n)
    return [replace(m, device_id=device, timestamp=float(i), message_id=f"{device}-{i}") for i, m in enumerate(base)]


def test_episode_schedule_attacks_whole_windows_of_one_device():
    stream = TrafficGenerator(5, seed=2).generate(80)
    result = AdversarialCampaign(seed=1).run(stream, attack=CONGESTION_SPOOF, mode="replace",
                                             schedule="episodes", episode_count=3, episode_seconds=5.0)
    assert 1 <= len(result.episodes) <= 3
    attacked = [m for m in result.messages if result.labels[m.message_id].label == "attack"]
    for m in attacked:
        assert any(m.device_id == d and s <= m.timestamp <= e for d, s, e in result.episodes)


def test_episode_metrics_delay_and_detection():
    msgs = _device()
    attacked = {m.message_id for m in msgs[4:8]}
    flags = [False] * 6 + [True] + [False] * 5
    out = episode_metrics(msgs, flags, attacked, [("d1", 4.0, 8.0)])
    assert out["episode_detection_rate"] == 1.0
    assert out["median_delay_s"] == pytest.approx(2.0)
    missed = episode_metrics(msgs, [False] * 12, attacked, [("d1", 4.0, 8.0)])
    assert missed["episode_detection_rate"] == 0.0 and math.isnan(missed["median_delay_s"])


def test_persistence_rule_and_false_alarm_events():
    msgs = _device(6)
    assert _persistent(msgs, [True, False, False, True, True, False]) == [False, False, False, False, True, True]
    assert false_alarms_per_hour(msgs, [True, True, False, True, False, False]) == pytest.approx(1 / (5 / 3600))


def test_unit_reports_all_detectors():
    stream = TrafficGenerator(6, seed=3).generate(60)
    unit = run_unit(stream, seed=1)
    assert set(unit["detectors"]) == {"forest", "lof", "hybrid", "hybrid_plus"}
