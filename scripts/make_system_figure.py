from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures" / "fig1_system.png"
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                     "mathtext.fontset": "stix", "figure.facecolor": "white", "savefig.facecolor": "white"})

FS = 9.0
PAD = 0.07
GREY = "#ececec"
W, H = 6.3, 7.35
MAIN_X, MAIN_W = 0.42, 2.95
SIDE_X, SIDE_W = 3.72, 2.55
GAP = 0.36


def text_height(ax, text):
    t = ax.text(0, 0, text, fontsize=FS, linespacing=1.22)
    h = t.get_window_extent(ax.figure.canvas.get_renderer()).height / ax.figure.dpi
    t.remove()
    return h


def box(ax, x, top, w, text, fill="white"):
    h = text_height(ax, text) + 2 * PAD
    ax.add_patch(Rectangle((x, top - h), w, h, fc=fill, ec="black", lw=0.6, zorder=2))
    ax.text(x + PAD, top - PAD, text, fontsize=FS, ha="left", va="top", linespacing=1.22, zorder=3)
    return top - h, top


def arrow(ax, p0, p1):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=9, lw=0.7, color="black",
                                 shrinkA=0, shrinkB=0, zorder=4))


def main() -> Path:
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    steps = [
        "Roadside sensor node (ATmega2560)\nHC-SR04: position and speed\nphotoresistor: occupancy",
        "Message encoder\nid, time, position, speed, occupancy;\n10 Hz over USB serial",
        "Authenticated channel\nsession set-up once: ML-KEM-768 and one\nECDSA or ML-DSA-65 signature;\n"
        "HMAC-SHA256 on every message",
        "Feature builder\nkinematics, timing, plausibility",
        "Hybrid+ detector\nrandom forest with plausibility features,\nfused with LOF (max-percentile);\n"
        "5% benign alarm budget",
        "Traffic digital twin\nstate estimate for signal control;\nalarms pass a k-of-n policy",
    ]
    top = H - 0.12
    spans = []
    for text in steps:
        bottom, t = box(ax, MAIN_X, top, MAIN_W, text)
        spans.append((bottom, t))
        top = bottom - GAP
    cx = MAIN_X + MAIN_W / 2
    for (b0, _), (_, t1) in zip(spans, spans[1:]):
        arrow(ax, (cx, b0), (cx, t1))

    def mid(i):
        return (spans[i][0] + spans[i][1]) / 2

    side = {
        0: ("Indicators on the node\nred LED and buzzer: alarm\ngreen LED: normal", "out"),
        1: ("Compromised device\nvalid credentials; replaces its own\nreadings; queries the detector score;\n"
            "falsified readings pass authentication", "in"),
        2: ("Measured on the boards\nsession set-up: 0.15 s on the ESP32\nHMAC: 0.14 ms (ESP32), 54 ms (8-bit)\n"
            "per-message signature: too slow", "out"),
        4: ("Evaluation\nthree trajectory sources (SUMO, NGSIM,\npNEUMA); known and novel attack\n"
            "families; adaptive attackers", "out"),
    }
    for i, (text, direction) in side.items():
        h = text_height(ax, text) + 2 * PAD
        y = mid(i)
        box(ax, SIDE_X, y + h / 2, SIDE_W, text, fill=GREY)
        if direction == "out":
            arrow(ax, (MAIN_X + MAIN_W, y), (SIDE_X, y))
        else:
            arrow(ax, (SIDE_X, y), (MAIN_X + MAIN_W, y))

    lx = 0.16
    y_from, y_to = mid(5), mid(0)
    ax.plot([MAIN_X, lx, lx], [y_from, y_from, y_to], color="black", lw=0.7, zorder=4)
    arrow(ax, (lx, y_to), (MAIN_X, y_to))
    ax.text(lx - 0.05, (y_from + y_to) / 2, "verdict (alarm or normal)", fontsize=FS - 0.5, rotation=90,
            ha="right", va="center")

    low = spans[-1][0] - 0.06
    ax.set_ylim(low, H)
    fig.set_size_inches(W, H - low)
    fig.savefig(OUT, dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return OUT


if __name__ == "__main__":
    print(main())
