import pytest

from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.ml_detection.robustness import (
    RobustnessScenarioResult,
    attack_success_rate,
    drop_sensor_value,
    evaluate_robustness,
    perturb_clock,
    perturb_speed,
)


def _message():
    return TrafficGenerator(1).generate(1)[0]


def test_attack_success_rate():
    assert attack_success_rate([True, False]) == 0.5


def test_attack_success_rate_empty_is_zero():
    assert attack_success_rate([]) == 0.0


def test_attack_success_rate_when_attack_not_expected():
    assert attack_success_rate([True, True, False, False], expected_attack=False) == 0.5


def test_perturb_speed_clamps_at_zero():
    message = _message()
    perturbed = perturb_speed(message, -abs(message.speed) - 10)
    assert perturbed.speed == 0.0
    assert perturbed.message_id != message.message_id


def test_perturb_clock_shifts_timestamp():
    message = _message()
    shifted = perturb_clock(message, 45.0)
    assert shifted.timestamp == pytest.approx(message.timestamp + 45.0)


@pytest.mark.parametrize(
    ("field", "expected"),
    [("speed", 0.0), ("occupancy", 0.0), ("signal_state", "unknown")],
)
def test_drop_sensor_value_replaces_field(field, expected):
    dropped = drop_sensor_value(_message(), field)
    assert getattr(dropped, field) == expected


def test_drop_sensor_value_rejects_unknown_field():
    with pytest.raises(ValueError):
        drop_sensor_value(_message(), "position")


def test_evaluate_robustness_reports_per_transformation():
    messages = TrafficGenerator(2).generate(3)
    results = evaluate_robustness(
        messages,
        detector=lambda m: m.speed > 0,
        transformations={
            "identity": lambda m: m,
            "zero_speed": lambda m: drop_sensor_value(m, "speed"),
        },
    )
    assert {r.scenario for r in results} == {"identity", "zero_speed"}
    assert all(isinstance(r, RobustnessScenarioResult) for r in results)
    zeroed = next(r for r in results if r.scenario == "zero_speed")
    assert zeroed.detected == 0
    assert zeroed.detection_rate == 0.0


def test_evaluate_robustness_rejects_empty_messages():
    with pytest.raises(ValueError):
        evaluate_robustness([], detector=lambda m: True, transformations={})
