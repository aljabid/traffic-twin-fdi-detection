import pytest

from smart_city_security.integration.avds_experiment import (
    POLICIES,
    _split,
    run_unit,
    select_divergence,
    summarise,
    worst_case,
)
from smart_city_security.integration.real_data_experiment import evaluate_once
from smart_city_security.iot_sim import TrafficGenerator

ATTACKS = ["congestion_spoof", "clear_road_spoof"]


@pytest.fixture(scope="module")
def stream() -> list:
    return TrafficGenerator(6, seed=3).generate(60)


def _scores(static: float, adaptive: float) -> dict[str, float]:
    return {"static": static, "adaptive": adaptive}


def test_split_keeps_validation_inside_train_and_test_untouched():
    stream = list(range(100))
    inner, validation, train, test = _split(stream, 0.45, 0.6)
    assert inner + validation == train
    assert test == stream[60:]
    assert not set(validation) & set(test)
    with pytest.raises(ValueError):
        _split(stream, 0.6, 0.6)


def test_selection_uses_worst_case_not_best_case():
    validation = {
        False: {"a": _scores(0.70, 0.60)},
        True: {"a": _scores(0.95, 0.40)},
    }
    assert worst_case(validation[True]["a"]) == 0.40
    assert select_divergence(validation, ["a"]) is False


def test_selection_tie_keeps_smaller_feature_set():
    validation = {False: {"a": _scores(0.5, 0.5)}, True: {"a": _scores(0.5, 0.5)}}
    assert select_divergence(validation, ["a"]) is False
    with pytest.raises(ValueError):
        select_divergence(validation, [])


def test_selection_only_reads_the_named_attacks():
    validation = {
        False: {"a": _scores(0.9, 0.9), "b": _scores(0.1, 0.1)},
        True: {"a": _scores(0.1, 0.1), "b": _scores(0.9, 0.9)},
    }
    assert select_divergence(validation, ["a"]) is False
    assert select_divergence(validation, ["b"]) is True


@pytest.fixture(scope="module")
def unit(stream):
    return run_unit(
        stream, model="isolation_forest", seed=1, attacks=ATTACKS, calibrate=False
    )


def test_novel_variant_is_leave_one_attack_out(unit):
    for attack in ATTACKS:
        assert unit["attacks"][attack]["validation_attacks"] == [a for a in ATTACKS if a != attack]


def test_primary_avds_makes_one_choice_for_every_attack(unit):
    choices = {unit["attacks"][a]["choices"]["avds"] for a in ATTACKS}
    assert len(choices) == 1
    validation = {div: unit["validation"][str(div).lower()] for div in (False, True)}
    assert choices == {select_divergence(validation, ATTACKS)}


def test_fixed_policies_reproduce_experiment5(unit, stream):
    cut = int(len(stream) * 0.6)
    for policy, divergence in (("never", False), ("always", True)):
        expected = evaluate_once(
            stream[:cut], stream[cut:], model="isolation_forest",
            include_divergence=divergence, contamination=0.05,
            attack_name="congestion_spoof", strength=0.6, adaptive=True, seed=1,
            calibrate=False,
        )["f1"]
        assert unit["attacks"]["congestion_spoof"]["test"][policy]["adaptive"] == expected


def test_oracle_is_an_upper_bound(unit):
    for attack in ATTACKS:
        test = unit["attacks"][attack]["test"]
        assert test["oracle"]["worst_case"] == max(
            test["never"]["worst_case"], test["always"]["worst_case"]
        )
        for policy in POLICIES:
            assert test[policy]["worst_case"] <= test["oracle"]["worst_case"]


def test_summary_reports_every_condition_and_policy(unit, stream):
    other = run_unit(stream, model="isolation_forest", seed=2, attacks=ATTACKS, calibrate=False)
    summary = summarise([unit, other], dataset="synthetic", models=["isolation_forest"], attacks=ATTACKS)
    for attack in ATTACKS:
        condition = summary["conditions"][f"synthetic/isolation_forest/{attack}"]
        assert condition["n_seeds"] == 2
        assert set(condition["mean"]) == set(POLICIES)
        for method in ("avds", "avds_novel"):
            assert 0.0 <= condition["agrees_with_oracle_rate"][method] <= 1.0
            assert condition["regret"][method] >= 0.0
        assert set(condition["significance"]) == {
            f"{m}_vs_{b}" for m in ("avds", "avds_novel") for b in ("never", "always")
        }
    assert summary["pooled"]["n_units"] == 4
