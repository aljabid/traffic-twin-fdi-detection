from smart_city_security.integration.network_impairment import PRESETS, impair, run_unit
from smart_city_security.iot_sim import TrafficGenerator


def _stream():
    return TrafficGenerator(5, seed=6).generate(80)


def test_ideal_link_changes_nothing():
    stream = _stream()
    assert impair(stream, loss=0.0, max_delay=0.0, duplicate=0.0, seed=1) == stream


def test_impairment_drops_duplicates_and_reorders():
    stream = _stream()
    out = impair(stream, loss=0.1, max_delay=5.0, duplicate=0.05, seed=1)
    ids = [m.message_id for m in out]
    assert any(i.endswith("-dup") for i in ids)
    original = {m.message_id for m in stream}
    assert len({i for i in ids if not i.endswith("-dup")}) < len(original)
    timestamps = [m.timestamp for m in out]
    assert timestamps != sorted(timestamps)


def test_unit_reports_every_preset():
    unit = run_unit(_stream(), model="isolation_forest", seed=1, attacks=["congestion_spoof"],
                    presets=["ideal", "severe"])
    for div in ("false", "true"):
        for preset in ("ideal", "severe"):
            row = unit["results"][f"divergence={div}/{preset}"]
            assert 0.0 <= row["benign_fpr"] <= 1.0
            assert set(row["congestion_spoof"]) == {"static", "adaptive", "worst_case"}
    assert set(PRESETS) >= {"ideal", "hrllc", "lossy", "degraded", "severe"}
