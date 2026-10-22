import numpy as np
import pytest

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.iot_sim.adversary import (
    ATTACKS,
    CONGESTION_SPOOF,
    AdversarialCampaign,
    Attack,
)
from smart_city_security.ml_detection import FeatureBuilder, train_detector


def _stream(n_devices: int = 6, per_device: int = 20) -> list:
    return TrafficGenerator(n_devices, seed=7).generate(per_device)


def test_attack_stays_within_quality_bounds():
    message = _stream(1, 1)[0]
    for speed_strength, occ_strength in ((0.2, 0.9), (0.6, 0.6), (1.0, 0.0)):
        out = CONGESTION_SPOOF.apply(message, speed_strength, occ_strength, message_id="x")
        assert 0.0 <= out.speed <= 89.0
        assert 0.0 <= out.occupancy <= 1.0
        assert out.device_id == message.device_id
        assert out.message_id == "x"


def test_campaign_labels_and_ratio():
    benign = _stream()
    result = AdversarialCampaign(seed=1).run(
        benign, attack=CONGESTION_SPOOF, attack_ratio=0.2, strength=0.5
    )
    attacks = [m for m in result.messages if result.labels[m.message_id].label == "attack"]
    assert len(attacks) == round(len(benign) * 0.2)
    assert all(result.labels[m.message_id].attack_type == "congestion_spoof" for m in attacks)
    assert result.mean_strength_used == pytest.approx(0.5)


def test_adaptive_campaign_reduces_strength_against_a_detector():
    benign = _stream(8, 30)
    twin = TrafficDigitalTwin(8)
    builder = FeatureBuilder(True)
    features = np.vstack([builder.build(m, twin.observe(m)).values for m in benign])
    detector = train_detector("isolation_forest", features, contamination=0.05, seed=1)

    fresh_twin = TrafficDigitalTwin(8)
    for m in benign:
        fresh_twin.observe(m)

    adaptive = AdversarialCampaign(seed=1).run(
        benign,
        attack=ATTACKS["congestion_spoof"],
        attack_ratio=0.3,
        strength=1.0,
        adaptive=True,
        detector=detector,
        feature_builder=FeatureBuilder(True),
        predict_twin_state=fresh_twin.predict,
    )
    assert 0.0 <= adaptive.mean_strength_used <= 1.0
    assert 0.0 <= adaptive.evaded_fraction <= 1.0
    assert 0.0 <= adaptive.mean_speed_strength_used <= 1.0
    assert 0.0 <= adaptive.mean_occupancy_strength_used <= 1.0
    non_adaptive = AdversarialCampaign(seed=1).run(
        benign, attack=ATTACKS["congestion_spoof"], attack_ratio=0.3, strength=1.0
    )
    assert adaptive.mean_speed_strength_used <= non_adaptive.mean_speed_strength_used
    assert adaptive.mean_occupancy_strength_used <= non_adaptive.mean_occupancy_strength_used


def test_adaptive_requires_detector():
    with pytest.raises(ValueError):
        AdversarialCampaign().run(_stream(), attack=CONGESTION_SPOOF, adaptive=True)


def test_gradient_search_is_asymmetric_across_axes():
    huge_attack = Attack("huge_congestion_spoof", speed_bias_kmh=-60.0, occupancy_bias=+0.9)
    benign = _stream(10, 30)
    twin = TrafficDigitalTwin(8)
    builder = FeatureBuilder(True)
    features = np.vstack([builder.build(m, twin.observe(m)).values for m in benign])
    detector = train_detector("mahalanobis", features, contamination=0.1, seed=1)

    fresh_twin = TrafficDigitalTwin(8)
    for m in benign:
        fresh_twin.observe(m)

    result = AdversarialCampaign(seed=2).run(
        benign,
        attack=huge_attack,
        attack_ratio=0.3,
        strength=1.0,
        adaptive=True,
        detector=detector,
        feature_builder=FeatureBuilder(True),
        predict_twin_state=fresh_twin.predict,
    )
    assert result.evaded_fraction > 0.0
    assert result.mean_speed_strength_used != pytest.approx(
        result.mean_occupancy_strength_used, abs=1e-6
    )


def test_drift_scales_with_progress():
    from smart_city_security.iot_sim.adversary import DRIFT_CONGESTION

    message = _stream(1, 1)[0]
    early = DRIFT_CONGESTION.apply(message, 1.0, 1.0, message_id="a", progress=0.1)
    late = DRIFT_CONGESTION.apply(message, 1.0, 1.0, message_id="b", progress=1.0)
    assert abs(early.speed - message.speed) < abs(late.speed - message.speed)
    assert 0.0 <= late.occupancy <= 1.0


def test_replay_moves_toward_reference_and_needs_one():
    from smart_city_security.iot_sim.adversary import REPLAY_STALE

    current, stale = _stream(1, 2)
    full = REPLAY_STALE.apply(current, 1.0, 1.0, message_id="r", reference=stale)
    assert full.speed == pytest.approx(round(stale.speed, 4))
    assert full.occupancy == pytest.approx(round(stale.occupancy, 4))
    assert REPLAY_STALE.apply(current, 0.0, 0.0, message_id="z", reference=stale).speed == pytest.approx(
        round(current.speed, 4)
    )
    with pytest.raises(ValueError):
        REPLAY_STALE.apply(current, 1.0, 1.0, message_id="x")


def test_replay_references_are_stale():
    from dataclasses import replace

    from smart_city_security.iot_sim.adversary import REPLAY_MIN_LAG_S, REPLAY_STALE

    benign = [replace(m, timestamp=float(i * 10)) for i, m in enumerate(_stream(4, 50))]
    campaign = AdversarialCampaign(seed=3)
    targets = benign[-20:]
    contexts = campaign._contexts(REPLAY_STALE, targets, benign)
    for target, (reference, _) in zip(targets, contexts, strict=True):
        assert reference is not None
        assert reference.timestamp <= target.timestamp - REPLAY_MIN_LAG_S


@pytest.mark.parametrize("name", ["drift_congestion", "replay_stale"])
def test_new_attacks_run_static_and_adaptive(name):
    benign = _stream(8, 30)
    twin = TrafficDigitalTwin(8)
    builder = FeatureBuilder(True)
    features = np.vstack([builder.build(m, twin.observe(m)).values for m in benign])
    detector = train_detector("isolation_forest", features, contamination=0.05, seed=1)
    for adaptive in (False, True):
        result = AdversarialCampaign(seed=2).run(
            benign, attack=ATTACKS[name], attack_ratio=0.2, strength=0.6, adaptive=adaptive,
            detector=detector, feature_builder=FeatureBuilder(True), predict_twin_state=twin.predict,
        )
        attacks = [m for m in result.messages if result.labels[m.message_id].label == "attack"]
        assert len(attacks) == round(len(benign) * 0.2)
        assert all(0.0 <= m.occupancy <= 1.0 and 0.0 <= m.speed <= 89.0 for m in attacks)


def test_search_budget_is_configurable_and_zero_steps_keeps_full_strength():
    benign = _stream(8, 30)
    twin = TrafficDigitalTwin(8)
    builder = FeatureBuilder(True)
    features = np.vstack([builder.build(m, twin.observe(m)).values for m in benign])
    detector = train_detector("isolation_forest", features, contamination=0.05, seed=1)
    campaign = AdversarialCampaign(seed=2, search_steps=0)
    assert campaign.search_steps == 0
    result = campaign.run(benign, attack=CONGESTION_SPOOF, attack_ratio=0.2, strength=0.6, adaptive=True,
                          detector=detector, feature_builder=FeatureBuilder(True), predict_twin_state=twin.predict)
    assert result.mean_strength_used == pytest.approx(0.6)


def test_replace_mode_swaps_messages_in_place():
    benign = _stream()
    inject = AdversarialCampaign(seed=5).run(benign, attack=CONGESTION_SPOOF, attack_ratio=0.2, strength=0.5)
    replace_ = AdversarialCampaign(seed=5).run(benign, attack=CONGESTION_SPOOF, attack_ratio=0.2, strength=0.5,
                                               mode="replace")
    n_attacks = round(len(benign) * 0.2)
    assert len(inject.messages) == len(benign) + n_attacks
    assert len(replace_.messages) == len(benign)
    assert [m.message_id for m in replace_.messages] == [m.message_id for m in sorted(
        benign, key=lambda m: (m.timestamp, m.message_id))]
    attacked = [m for m in replace_.messages if replace_.labels[m.message_id].label == "attack"]
    assert len(attacked) == n_attacks
    originals = {m.message_id: m for m in benign}
    assert all(m.speed != originals[m.message_id].speed or m.occupancy != originals[m.message_id].occupancy
               for m in attacked)
    with pytest.raises(ValueError):
        AdversarialCampaign(seed=5).run(benign, attack=CONGESTION_SPOOF, mode="swap")


class _ConstantDetector:
    name = "constant"

    def __init__(self, flag: bool) -> None:
        self.flag = flag

    def predict(self, features):
        return np.full(len(features), self.flag), features[:, 1]


@pytest.mark.parametrize("flag", [False, True])
def test_grid_search_keeps_strongest_evading_point_or_lowest_score(flag):
    benign = _stream(4, 20)
    twin = TrafficDigitalTwin(8)
    for m in benign:
        twin.observe(m)
    result = AdversarialCampaign(seed=3, search="grid").run(
        benign, attack=CONGESTION_SPOOF, attack_ratio=0.2, strength=0.6, adaptive=True,
        detector=_ConstantDetector(flag), feature_builder=FeatureBuilder(True), predict_twin_state=twin.predict,
    )
    if not flag:
        assert result.mean_speed_strength_used == pytest.approx(0.6)
        assert result.mean_occupancy_strength_used == pytest.approx(0.6)
    else:
        assert result.mean_occupancy_strength_used == pytest.approx(0.0)
    with pytest.raises(ValueError):
        AdversarialCampaign(seed=3, search="random")


def test_novel_attacks_touch_only_their_own_field():
    from smart_city_security.iot_sim.adversary import (
        POSITION_SPOOF,
        POSITION_SPOOF_MAX_M,
        TIME_SHIFT,
        TIME_SHIFT_MAX_S,
    )

    m = _stream(1, 1)[0]
    shifted = TIME_SHIFT.apply(m, 1.0, 1.0, message_id="t")
    assert shifted.timestamp == pytest.approx(m.timestamp + TIME_SHIFT_MAX_S)
    assert (shifted.speed, shifted.occupancy, shifted.position) == (m.speed, m.occupancy, m.position)
    moved = POSITION_SPOOF.apply(m, 0.5, 1.0, message_id="p")
    assert moved.position == pytest.approx(round(m.position + 0.5 * POSITION_SPOOF_MAX_M, 4))
    assert (moved.speed, moved.occupancy, moved.timestamp) == (m.speed, m.occupancy, m.timestamp)


def test_stuck_at_freezes_each_device_at_its_own_first_reading():
    from smart_city_security.iot_sim.adversary import STUCK_AT

    benign = _stream(4, 20)
    targets = benign[-8:]
    contexts = AdversarialCampaign(seed=1)._contexts(STUCK_AT, targets, benign)
    first = {}
    for m in sorted(benign, key=lambda m: (m.timestamp, m.message_id)):
        first.setdefault(m.device_id, m)
    for target, (reference, _) in zip(targets, contexts, strict=True):
        assert reference is first[target.device_id]


@pytest.mark.parametrize("name", ["stuck_at", "time_shift", "position_spoof"])
def test_novel_attacks_run_with_grid_adversary(name):
    benign = _stream(8, 30)
    twin = TrafficDigitalTwin(8)
    builder = FeatureBuilder(True)
    features = np.vstack([builder.build(m, twin.observe(m)).values for m in benign])
    detector = train_detector("isolation_forest", features, contamination=0.05, seed=1)
    result = AdversarialCampaign(seed=2, search="grid").run(
        benign, attack=ATTACKS[name], attack_ratio=0.2, strength=0.6, adaptive=True, mode="replace",
        detector=detector, feature_builder=FeatureBuilder(True), predict_twin_state=twin.predict,
    )
    assert len(result.messages) == len(benign)


def test_second_novel_set_changes_the_intended_fields():
    from smart_city_security.iot_sim.adversary import (
        BACKDATE,
        IDENTITY_SPOOF,
        NOISE_INJECTION,
        TIME_SHIFT_MAX_S,
    )

    a, b = _stream(2, 1)
    back = BACKDATE.apply(a, 1.0, 0.0, message_id="b")
    assert back.timestamp == pytest.approx(a.timestamp - TIME_SHIFT_MAX_S)
    spoofed = IDENTITY_SPOOF.apply(a, 0.6, 0.0, message_id="i", reference=b)
    assert spoofed.device_id == b.device_id and spoofed.speed == a.speed
    assert IDENTITY_SPOOF.apply(a, 0.0, 0.0, message_id="i", reference=b).device_id == a.device_id
    noisy = NOISE_INJECTION.apply(a, 1.0, 1.0, message_id="n")
    again = NOISE_INJECTION.apply(a, 1.0, 1.0, message_id="n")
    assert (noisy.speed, noisy.occupancy) == (again.speed, again.occupancy)
    assert 0.0 <= noisy.occupancy <= 1.0


@pytest.mark.parametrize("name", ["identity_spoof", "noise_injection", "backdate"])
def test_second_novel_set_runs_with_grid_adversary(name):
    benign = _stream(8, 30)
    twin = TrafficDigitalTwin(8)
    builder = FeatureBuilder(True)
    features = np.vstack([builder.build(m, twin.observe(m)).values for m in benign])
    detector = train_detector("isolation_forest", features, contamination=0.05, seed=1)
    result = AdversarialCampaign(seed=2, search="grid").run(
        benign, attack=ATTACKS[name], attack_ratio=0.2, strength=0.6, adaptive=True, mode="replace",
        detector=detector, feature_builder=FeatureBuilder(True), predict_twin_state=twin.predict,
    )
    assert len(result.messages) == len(benign)


def test_coupled_attack_keeps_occupancy_on_the_speed_rule():
    from smart_city_security.evaluation.real_datasets import occupancy_from_speed
    from smart_city_security.iot_sim.adversary import ATTACKS, COUPLED_ATTACKS, REHEARSAL_ATTACKS
    from smart_city_security.schemas import Telemetry

    message = Telemetry.create("v1", 10.0, 40.0, "cell-0-0", occupancy_from_speed(40.0), "unknown", 1)
    for name in COUPLED_ATTACKS:
        forged = ATTACKS[name].apply(message, 0.6, 0.0, message_id="x")
        assert forged.speed != message.speed
        assert abs(forged.occupancy - occupancy_from_speed(forged.speed)) < 1e-3
        assert name not in REHEARSAL_ATTACKS
