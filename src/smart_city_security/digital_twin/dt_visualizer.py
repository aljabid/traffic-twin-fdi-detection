from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from smart_city_security.schemas import TwinState


def plot_divergence(states: Iterable[TwinState], output: str | Path) -> Path:
    import matplotlib.pyplot as plt

    values = list(states)
    figure, axis = plt.subplots()
    axis.plot([item.timestamp for item in values], [item.divergence for item in values])
    axis.set(title="Digital-twin divergence", xlabel="Time", ylabel="Divergence")
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path
