import csv

from smart_city_security.integration.real_data_experiment import (
    Dataset,
    evaluate_once,
    run_experiment,
)
from smart_city_security.integration.real_data_experiment import (
    load_dataset as _load,
)
from smart_city_security.iot_sim import TrafficGenerator


def _dataset() -> Dataset:
    stream = TrafficGenerator(10, seed=3).generate(40)
    stream.sort(key=lambda t: (t.timestamp, t.device_id, t.sequence_number))
    return Dataset("synthetic", stream)


def test_evaluate_once_returns_metrics():
    ds = _dataset()
    cut = int(len(ds.telemetry) * 0.6)
    result = evaluate_once(
        ds.telemetry[:cut],
        ds.telemetry[cut:],
        model="isolation_forest",
        include_divergence=True,
        contamination=0.1,
        attack_name="congestion_spoof",
        strength=0.6,
        adaptive=False,
        seed=1,
        calibrate=False,
    )
    for key in ("precision", "recall", "f1", "false_positive_rate"):
        assert 0.0 <= result[key] <= 1.0
    assert result["n_attacks"] > 0


def test_run_experiment_small_matrix():
    report = run_experiment(
        [_dataset()],
        models=("isolation_forest", "ewma_residual"),
        attacks=("congestion_spoof",),
        seeds=(1, 2),
        calibrate=False,
    )
    assert report["experiment"] == "real_data_detection"
    assert len(report["results"]) == 8
    for block in report["results"].values():
        assert len(block["runs"]) == 2
        assert set(block["mean"]) >= {"precision", "recall", "f1"}

    assert len(report["significance"]) == 8
    for block in report["significance"].values():
        assert set(block) == {"f1", "false_positive_rate", "recall"}
        f1_result = block["f1"]
        assert f1_result["n_pairs"] == 2
        assert "ci95_low" in f1_result and "ci95_high" in f1_result
        assert "significant_at_05" in f1_result


def test_load_dataset_reads_sumo_csv(tmp_path):
    path = tmp_path / "fcd.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "id", "x", "y", "speed", "type", "edge", "occupancy", "signal_state"])
        for i in range(50):
            writer.writerow([f"{i}.0", f"v{i % 5}", "0", i, "10.0", "vehicle", "e1", "0.2", "green"])
    ds = _load("sumo", path=path, max_messages=100)
    assert ds.name == "sumo"
    assert len(ds.telemetry) == 50
