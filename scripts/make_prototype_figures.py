from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
PHOTOS = ROOT / "docs" / "figures" / "photos"
OUT_RUN = ROOT / "docs" / "figures" / "fig_live_run.png"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
                     "figure.facecolor": "white", "savefig.facecolor": "white"})
BOX = dict(boxstyle="square,pad=0.22", fc="white", ec="black", lw=0.6)
HALO = [pe.withStroke(linewidth=2.2, foreground="white")]


def label(ax, text, xy, xytext, size=6.8):
    ann = ax.annotate(text, xy=xy, xytext=xytext, fontsize=size, ha="center", va="center", bbox=BOX,
                      arrowprops=dict(arrowstyle="-|>", mutation_scale=7, color="black", lw=0.8, shrinkA=0,
                                      shrinkB=1.5))
    ann.arrow_patch.set_path_effects(HALO)


def photo_axes(ax, im):
    ax.imshow(np.asarray(im))
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(0.6)


def daylight() -> Image.Image:
    return Image.open(PHOTOS / "bench_daylight.jpg")


def attack() -> Image.Image:
    im = Image.open(PHOTOS / "bench_attack_esp32.jpg")
    return ImageEnhance.Contrast(ImageEnhance.Brightness(im).enhance(1.35)).enhance(1.08)


def label_daylight(ax, size=6.8):
    label(ax, "ATmega2560 board\n(Elegoo Mega 2560)", (930, 900), (1080, 1180), size)
    label(ax, "HC-SR04\nultrasonic ranger", (950, 1590), (1130, 1360), size)
    label(ax, "buzzer", (720, 1610), (680, 1420), size)
    label(ax, "photoresistor", (345, 1735), (190, 1580), size)
    label(ax, "red LED", (525, 685), (230, 560), size)
    label(ax, "green LED", (480, 770), (210, 860), size)
    label(ax, "220 Ω resistors", (360, 730), (560, 470), size)
    label(ax, "USB to host", (1010, 300), (720, 150), size)


def label_attack(ax, size=6.8):
    label(ax, "red LED lit:\nattack flagged", (1100, 550), (1430, 180), size)
    label(ax, "ESP32-WROOM-32E\n(cryptographic timing)", (480, 1360), (980, 1400), size)
    label(ax, "ATmega2560\nsensor node", (950, 960), (1460, 880), size)
    label(ax, "HC-SR04", (220, 960), (190, 1190), size)


def live_run() -> Path:
    im = attack()
    fig, ax = plt.subplots(figsize=(4.4, 4.4 * im.height / im.width))
    photo_axes(ax, im)
    label_attack(ax)
    fig.savefig(OUT_RUN, dpi=600, bbox_inches="tight")
    plt.close(fig)
    return OUT_RUN


if __name__ == "__main__":
    print(live_run())
