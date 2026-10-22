from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

REQUIRED_SECTIONS = {
    "simulation",
    "network",
    "security",
    "digital_twin",
    "ml",
    "experiment",
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path).resolve()
    with path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream) or {}
    parent = config.pop("extends", None)
    if parent:
        parent_path = Path(parent)
        if not parent_path.is_absolute():
            candidate = path.parent / parent_path
            parent_path = candidate if candidate.exists() else Path.cwd() / parent_path
        config = _merge(load_config(parent_path), config)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    missing = REQUIRED_SECTIONS - config.keys()
    if missing:
        raise ValueError(f"Missing configuration sections: {sorted(missing)}")
    simulation = config["simulation"]
    if int(simulation["devices"]) < 1:
        raise ValueError("simulation.devices must be positive")
    if int(simulation["messages_per_device"]) < 1:
        raise ValueError("simulation.messages_per_device must be positive")
    if not 0 <= float(simulation["attack_ratio"]) <= 1:
        raise ValueError("simulation.attack_ratio must be between 0 and 1")
    network = config["network"]
    if network["preset"] not in {"ideal", "congested", "degraded"}:
        raise ValueError("network.preset must be ideal, congested, or degraded")
    security = config["security"]
    if security["backend"] not in {"none", "classical", "pqc", "preshared"}:
        raise ValueError("security.backend must be none, classical, pqc, or preshared")
    ml = config["ml"]
    if ml["model"] not in {
        "isolation_forest",
        "autoencoder",
        "one_class_svm",
        "ocsvm",
        "lof",
        "mahalanobis",
        "ewma_residual",
    }:
        raise ValueError("unsupported ml.model")
    if not 0 < float(ml["contamination"]) < 0.5:
        raise ValueError("ml.contamination must be between 0 and 0.5")
