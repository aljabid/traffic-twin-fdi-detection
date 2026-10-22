import pytest

from smart_city_security.digital_twin.dt_scenarios import SCENARIOS, TwinScenario, get_scenario


def test_get_scenario_returns_twin_scenario():
    scenario = get_scenario("incident")
    assert isinstance(scenario, TwinScenario)
    assert scenario.speed_multiplier == 0.2


def test_scenarios_are_all_twin_scenarios():
    assert all(isinstance(scenario, TwinScenario) for scenario in SCENARIOS.values())


def test_get_scenario_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown twin scenario"):
        get_scenario("does-not-exist")
