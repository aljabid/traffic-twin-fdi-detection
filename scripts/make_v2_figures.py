from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from smart_city_security.iot_sim.adversary import (
    NOVEL_ATTACKS,
    NOVEL_ATTACKS_2,
    REHEARSAL_ATTACKS,
)

DPI = 600
BLACK, DARK, MID, LIGHT, WHITE = "#000000", "#404040", "#8c8c8c", "#cfcfcf", "#ffffff"
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 9,
    "axes.linewidth": 1.0,
    "axes.edgecolor": BLACK,
    "axes.labelcolor": BLACK,
    "axes.labelsize": 9.5,
    "xtick.color": BLACK,
    "ytick.color": BLACK,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.size": 4,
    "ytick.major.size": 4,
    "xtick.major.width": 1.0,
    "ytick.major.width": 1.0,
    "legend.fontsize": 8.5,
    "legend.frameon": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": WHITE,
    "savefig.facecolor": WHITE,
    "hatch.linewidth": 0.6,
})

SOURCES = ("sumo", "ngsim", "pneuma")
GROUPS = {"Known (4)": REHEARSAL_ATTACKS, "Novel A (3)": NOVEL_ATTACKS, "Novel B (3)": NOVEL_ATTACKS_2}
ALL = [*REHEARSAL_ATTACKS, *NOVEL_ATTACKS, *NOVEL_ATTACKS_2]
DETECTORS = (
    ("hybrid_plus", "Hybrid+"),
    ("hybrid", "Hybrid"),
    ("gradient_boosting", "Gradient boosting"),
    ("forest", "Supervised forest"),
    ("plausibility_knn", "Plausibility + kNN"),
    ("lof", "LOF"),
    ("kalman_chi2", "Kalman + chi-squared"),
)
FILLS = ((DARK, ""), (MID, ""), (WHITE, "////"))


def _cells(paths: list[Path]) -> dict[str, dict[tuple[str, int], dict[str, float]]]:
    cells: dict[str, dict[tuple[str, int], dict[str, float]]] = {}
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        for source, block in report["datasets"].items():
            for unit in block["units"]:
                for det, scores in unit["scores"].items():
                    row = cells.setdefault(det, {}).setdefault((source, unit["seed"]), {})
                    row.update({a: v["worst_case"] for a, v in scores.items()})
    return cells


def _unit_means(units: dict[tuple[str, int], dict[str, float]], attacks: list[str]) -> np.ndarray:
    return np.array([np.mean([u[a] for a in attacks]) for u in units.values()])


def _sem(values: np.ndarray) -> float:
    return float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0


def _panel(ax, letter: str, ref=None) -> None:
    host = ref or ax
    ann = host.annotate(f"({letter.lower()})", xy=(0.5, 0), xycoords=(ax.transAxes, host.xaxis.label),
                        xytext=(0, -8), textcoords="offset points", fontsize=10, ha="center", va="top")
    ann.set_in_layout(False)


def _save(fig, output: Path) -> None:
    for ax in fig.axes:
        for t in ax.texts:
            t.set_in_layout(True)
    fig.savefig(output, dpi=DPI, bbox_inches="tight")


def figure5(results: Path, output: Path) -> None:
    prefixes = ("sota", "hybrid", "hybrid-confirm", "hybrid-novel2", "hybrid-plus")
    design = _cells([results / f"{p}-{s}.json" for p in prefixes for s in SOURCES])
    confirm = _cells([results / f"hybrid-plus-confirm-{s}.json" for s in SOURCES])

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.2, 3.3), gridspec_kw={"width_ratios": [1.9, 1]})
    y = np.arange(len(DETECTORS))
    height = 0.26
    for i, ((label, attacks), (fill, hatch)) in enumerate(zip(GROUPS.items(), FILLS, strict=True)):
        per_det = [_unit_means(design[d], attacks) for d, _ in DETECTORS]
        ax_a.barh(y + (i - 1) * height, [v.mean() for v in per_det], height, xerr=[_sem(v) for v in per_det],
                  color=fill, hatch=hatch, edgecolor=BLACK, linewidth=0.7, label=label,
                  error_kw={"elinewidth": 0.7, "capsize": 1.5, "capthick": 0.7})
    ax_a.set_yticks(y, [name for _, name in DETECTORS])
    ax_a.invert_yaxis()
    ax_a.set_xlabel("Worst-case F1")
    ax_a.set_xlim(0, 0.65)
    ax_a.legend(loc="lower right", handlelength=1.4)
    _panel(ax_a, "A", ref=ax_b)

    rng = np.random.default_rng(0)
    for row, (other, face) in enumerate((("hybrid", BLACK), ("plausibility_knn", WHITE))):
        keys = sorted(confirm["hybrid_plus"])
        diffs = np.array([np.mean([confirm["hybrid_plus"][k][a] - confirm[other][k][a] for a in ALL])
                          for k in keys])
        ax_b.scatter(diffs, row + rng.uniform(-0.14, 0.14, len(diffs)), s=11, facecolor=face, edgecolor=BLACK,
                     linewidth=0.6, zorder=3)
        ax_b.errorbar(diffs.mean(), row, xerr=_sem(diffs), fmt="none", ecolor=BLACK, elinewidth=1.0, capsize=3,
                      zorder=4)
        ax_b.plot([diffs.mean()] * 2, [row - 0.3, row + 0.3], color=BLACK, lw=1.6, zorder=4)
        ax_b.text(diffs.mean(), row + 0.36, f"{diffs.mean():+.3f}\n{int((diffs > 0).sum())}/{len(diffs)} units",
                  ha="center", va="top", fontsize=7.5)
    ax_b.axvline(0, color=BLACK, lw=0.8, ls=(0, (3, 2)))
    ax_b.set_yticks([0, 1], ["vs hybrid", "vs plausibility\n+ kNN"])
    ax_b.set_ylim(1.75, -0.55)
    ax_b.set_xlabel("Paired difference in F1\n(Hybrid+ minus other)")
    _panel(ax_b, "B")

    fig.tight_layout(w_pad=2.0)
    output.parent.mkdir(parents=True, exist_ok=True)
    _save(fig, output)
    plt.close(fig)


def figure6(results: Path, output: Path) -> None:
    points: dict[str, dict[tuple[str, str], list[tuple[float, float]]]] = {}
    for source in SOURCES:
        report = json.loads((results / f"alarm-tradeoff-{source}.json").read_text(encoding="utf-8"))
        for unit in report["datasets"][source]["units"]:
            for budget, dets in unit["budgets"].items():
                for det, rules in dets.items():
                    for rule, m in rules.items():
                        points.setdefault(det, {}).setdefault((budget, rule), []).append(
                            (m["false_alarms_per_vehicle_hour"], m["detection_rate"]))

    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    styles = (("hybrid", "Hybrid", "o", BLACK, BLACK, "-"),
              ("forest", "Supervised forest", "s", WHITE, BLACK, "--"),
              ("lof", "LOF", "^", MID, BLACK, ":"))
    for det, label, marker, face, edge, ls in styles:
        xy = np.array([np.mean(v, axis=0) for v in points[det].values()])
        order = np.argsort(xy[:, 0])
        front = [order[0]]
        for i in order[1:]:
            if xy[i, 1] > xy[front[-1], 1]:
                front.append(i)
        ax.plot(xy[front, 0], xy[front, 1], color=BLACK, lw=1.0, ls=ls, zorder=2)
        ax.scatter(xy[:, 0], xy[:, 1], s=20, marker=marker, facecolor=face, edgecolor=edge, linewidth=0.7,
                   label=label, zorder=3)
    ax.axvline(1.0, color=MID, lw=0.8, ls=(0, (3, 2)), zorder=1)
    ax.text(1.12, 0.40, "1 false alarm\nper vehicle-hour", fontsize=7.5, color=DARK)
    ax.set_xscale("log")
    ax.set_xlabel("False alarms per vehicle-hour")
    ax.set_ylabel("Fraction of 30 s attacks detected")
    ax.set_ylim(0, 1.02)
    ax.legend(loc="upper left", handletextpad=0.4)
    fig.tight_layout()
    _save(fig, output)
    plt.close(fig)


def figure7(results: Path, output: Path) -> None:
    labels = {"sumo": "SUMO", "ngsim": "NGSIM", "pneuma": "pNEUMA"}
    series = {"fixed": [], "jitter": [], "grad": [], "grid": []}
    for source in SOURCES:
        net = json.loads((results / f"network-{source}.json").read_text(encoding="utf-8"))
        units = next(iter(net["datasets"].values()))["units"]
        for preset, key in (("ideal", "fixed"), ("hrllc", "jitter")):
            series[key].append(np.array([np.mean([u["results"][f"divergence=false/{preset}"][a]["worst_case"]
                                                  for a in net["attacks"]]) for u in units]))
        for name, key in (("supervised", "grad"), ("supervised-grid", "grid")):
            sup = json.loads((results / f"{name}-{source}.json").read_text(encoding="utf-8"))
            units = next(iter(sup["datasets"].values()))["units"]
            series[key].append(np.array([np.mean([s["adaptive"] for s in u["known"].values()]) for u in units]))

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.2, 2.9))
    x = np.arange(len(SOURCES))
    for ax, (left, right), (l_label, r_label), ylabel, letter in (
        (ax_a, (series["fixed"], series["jitter"]), ("Fixed tie order", "Order randomised (10 ms jitter)"),
         "Worst-case F1", "A"),
        (ax_b, (series["grad"], series["grid"]), ("Gradient attacker", "Gradient-free grid attacker"),
         "Adaptive F1, known families", "B"),
    ):
        for offset, data, fill, hatch, label in ((-0.19, left, DARK, "", l_label),
                                                  (0.19, right, WHITE, "////", r_label)):
            means = [d.mean() for d in data]
            ax.bar(x + offset, means, 0.36, yerr=[_sem(d) for d in data], color=fill, hatch=hatch, edgecolor=BLACK,
                   linewidth=0.7, label=label, error_kw={"elinewidth": 0.7, "capsize": 2, "capthick": 0.7})
            for i, m in enumerate(means):
                ax.text(i + offset, m + _sem(data[i]) + 0.015, f"{m:.2f}", ha="center", va="bottom", fontsize=7)
        ax.set_xticks(x, [labels[s] for s in SOURCES])
        ax.set_ylim(0, 0.92)
        ax.set_ylabel(ylabel)
        ax.legend(loc="upper left", handlelength=1.4)
        _panel(ax, letter)
    fig.tight_layout(w_pad=2.0)
    _save(fig, output)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results" / "ml")
    parser.add_argument("--outdir", type=Path, default=ROOT / "docs" / "figures")
    args = parser.parse_args()
    figure5(args.results, args.outdir / "fig5_detectors.png")
    figure6(args.results, args.outdir / "fig6_alarm_tradeoff.png")
    figure7(args.results, args.outdir / "fig7_pitfalls.png")
    print(args.outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
