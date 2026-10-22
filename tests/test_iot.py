import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from smart_city_security.iot_sim.attack_injector import AttackInjector
from smart_city_security.iot_sim.traffic_generator import TrafficGenerator


def test_attack_injector_keeps_ground_truth_separate():
    normal = TrafficGenerator(2, seed=2).generate(4)
    messages, labels = AttackInjector(seed=3).inject(normal, attack_ratio=0.5)
    assert len(messages) > len(normal)
    assert all("attack" not in message.to_dict() for message in messages)
    assert any(label.is_attack for label in labels.values())
