from smart_city_security.integration.avds_poisoning import poison, run_unit
from smart_city_security.iot_sim import TrafficGenerator


def test_poison_adds_unlabelled_attack_messages():
    validation = TrafficGenerator(4, seed=2).generate(25)
    poisoned = poison(validation, "congestion_spoof", 0.1, seed=1)
    assert len(poisoned) == len(validation) + round(len(validation) * 0.1)
    assert [m.timestamp for m in poisoned] == sorted(m.timestamp for m in poisoned)


def test_unit_reports_choice_per_rate_and_poison_type():
    stream = TrafficGenerator(6, seed=3).generate(60)
    attacks = ["congestion_spoof", "replay_stale"]
    unit = run_unit(stream, model="isolation_forest", seed=1, attacks=attacks, rates=[0.1])
    assert isinstance(unit["clean_choice"], bool)
    assert set(unit["poisoned_choice"]["0.1"]) == set(attacks)
