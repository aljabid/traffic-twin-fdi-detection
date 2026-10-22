from smart_city_security.config import load_config
from smart_city_security.integration.divergence_sweep import sweep


def test_sweep_reports_tuned_operating_point_and_effect():
    config = load_config("configs/exp2_divergence_ablation.yaml")
    config["simulation"] = {**config["simulation"], "devices": 8, "messages_per_device": 12}

    report = sweep(
        config,
        seeds=(1, 2),
        contamination_grid=(0.1, 0.2),
        models=("isolation_forest",),
    )

    key = "isolation_forest/divergence=true"
    assert key in report["results"]
    assert len(report["results"][key]["grid"]) == 2
    tuned = report["results"][key]["tuned"]
    assert tuned["contamination"] in (0.1, 0.2)
    assert tuned["f1"] == max(row["f1"] for row in report["results"][key]["grid"])

    effect = report["effects"]["isolation_forest"]
    assert set(effect["delta_at_tuned"]) == {
        "accuracy",
        "precision",
        "recall",
        "f1",
        "false_positive_rate",
    }
    assert isinstance(effect["divergence_helps_f1"], bool)
