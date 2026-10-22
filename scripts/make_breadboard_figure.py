from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, PathPatch, Rectangle
from matplotlib.path import Path as MPath
from PIL import Image

from make_prototype_figures import label_daylight, photo_axes

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "docs" / "figures" / "photos" / "bench_daylight.jpg"
OUT = ROOT / "docs" / "figures" / "fig_breadboard.png"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
                     "figure.facecolor": "white", "savefig.facecolor": "white"})

P = 2.54
XLIM, YLIM = (-24.0, 148.0), (-14.0, 124.0)

PCB, PCB_EDGE = "#1d5c94", "#123d63"
BOARD, BOARD_EDGE, HOLE = "#f1efe9", "#cbc6b8", "#5a5a5a"
METAL, METAL_DARK = "#c9c9c9", "#8a8a8a"
WIRE = {"5V": "#d63a2f", "GND": "#262626", "A0": "#e5bf12", "D13": "#ee8a1f", "D12": "#2f9a4a",
        "D10": "#f4f4f4", "D9": "#8a5a2e", "D6": "#7a4ea0"}

S = 1.0


def mm(v: float) -> float:
    return v * S


BX, BY = 8.0, 66.0
ROW = {"a": 76.6, "b": 79.14, "c": 81.68, "d": 84.22, "e": 86.76,
       "f": 94.38, "g": 96.92, "h": 99.46, "i": 102.0, "j": 104.54}
RAIL = {"top-": 109.6, "top+": 112.14, "bot-": 71.54, "bot+": 69.0}
NCOL = 30


def col(c: int) -> float:
    return BX + 4.6 + (c - 1) * P


def hole(c: int, r: str) -> tuple[float, float]:
    return col(c), ROW[r] if r in ROW else RAIL[r]


TOP_PINS = ["SCL", "SDA", "AREF", "GND", "13", "12", "11", "10", "9", "8"]
TOP_PINS2 = ["7", "6", "5", "4", "3", "2", "1", "0"]
TOP_PINS3 = ["14", "15", "16", "17", "18", "19", "20", "21"]
BOT_PINS = ["", "IOREF", "RESET", "3.3V", "5V", "GND", "GND", "VIN"]
BOT_PINS2 = [f"A{i}" for i in range(8)]
BOT_PINS3 = [f"A{i}" for i in range(8, 16)]
TOP_Y, BOT_Y = 50.8, 2.54


def header_x(start: float, n: int) -> list[float]:
    return [start + i * P for i in range(n)]


MEGA = {}
for names, start in ((TOP_PINS, 18.0), (TOP_PINS2, 44.9), (TOP_PINS3, 66.6)):
    for n, x in zip(names, header_x(start, len(names))):
        MEGA.setdefault("T" + n, (x, TOP_Y))
for names, start in ((BOT_PINS, 26.7), (BOT_PINS2, 49.5), (BOT_PINS3, 72.4)):
    for n, x in zip(names, header_x(start, len(names))):
        MEGA.setdefault("B" + n, (x, BOT_Y))


def rounded(points: list[tuple[float, float]], r: float = 4.0) -> MPath:
    pts = np.asarray(points, float)
    verts, codes = [tuple(pts[0])], [MPath.MOVETO]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        la, lc = np.linalg.norm(b - a), np.linalg.norm(c - b)
        rr = min(r, la / 2, lc / 2)
        p_in = b + (a - b) / la * rr
        p_out = b + (c - b) / lc * rr
        verts += [tuple(p_in), tuple(b), tuple(p_out)]
        codes += [MPath.LINETO, MPath.CURVE3, MPath.CURVE3]
    verts.append(tuple(pts[-1]))
    codes.append(MPath.LINETO)
    return MPath(verts, codes)


def shade(colour: str, f: float) -> tuple:
    rgb = np.array(matplotlib.colors.to_rgb(colour))
    return tuple(np.clip(rgb * f if f < 1 else rgb + (1 - rgb) * (f - 1), 0, 1))


def wire(ax, points, colour, r=4.0, z=20):
    path = rounded(points, r)
    edge = "#9a9a9a" if colour == WIRE["D10"] else shade(colour, 0.55)
    ax.add_patch(PathPatch(path, fill=False, lw=mm(1.25), ec=colour, capstyle="round", joinstyle="round",
                           zorder=z, path_effects=[pe.Stroke(linewidth=mm(1.25) + 0.9, foreground=edge),
                                                   pe.Normal()]))
    ax.add_patch(PathPatch(path, fill=False, lw=mm(0.32), ec=shade(colour, 1.45), alpha=0.7, capstyle="round",
                           zorder=z + 0.1))
    for end in (points[0], points[-1]):
        ax.add_patch(Rectangle((end[0] - 0.55, end[1] - 0.55), 1.1, 1.1, fc="#3a3a3a", ec="none", zorder=z + 0.2))


def text(ax, x, y, s, size_mm, colour="white", **kw):
    ax.text(x, y, s, fontsize=mm(size_mm), color=colour, ha=kw.pop("ha", "center"), va=kw.pop("va", "center"),
            zorder=kw.pop("zorder", 6), **kw)


def draw_breadboard(ax):
    w, h = col(NCOL) + 4.6 - BX, 49.2
    ax.add_patch(FancyBboxPatch((BX, BY), w, h, boxstyle="round,pad=0,rounding_size=1.2", fc=BOARD,
                                ec=BOARD_EDGE, lw=0.6, zorder=1))
    ax.add_patch(Rectangle((BX, 88.9), w, 3.3, fc="#e3dfd3", ec="none", zorder=1.1))
    for y0 in (74.6, 106.6):
        ax.plot([BX + 0.3, BX + w - 0.3], [y0, y0], color="#dedad0", lw=0.3, zorder=1.1)
    for y, c in ((114.0, "#d6453b"), (107.8, "#3f74b8"), (73.3, "#3f74b8"), (67.2, "#d6453b")):
        ax.plot([col(1) - 1.5, col(NCOL) + 1.5], [y, y], color=c, lw=mm(0.35), zorder=1.2)
    for s, y in (("+", 114.0), ("−", 107.8), ("−", 73.3), ("+", 67.2)):
        text(ax, BX + 1.6, y, s, 2.2, "#555555")
    for c in range(1, NCOL + 1):
        for r in ROW:
            ax.add_patch(Rectangle((col(c) - 0.5, ROW[r] - 0.5), 1.0, 1.0, fc=HOLE, ec="#d9d6cc", lw=0.15,
                                   zorder=1.3))
        if c % 6:
            for y in RAIL.values():
                ax.add_patch(Rectangle((col(c) - 0.5, y - 0.5), 1.0, 1.0, fc=HOLE, ec="#d9d6cc", lw=0.15,
                                       zorder=1.3))
        if c == 1 or c % 5 == 0:
            text(ax, col(c), 106.75, str(c), 1.25, "#777777")
            text(ax, col(c), 74.35, str(c), 1.25, "#777777")
    for r, y in ROW.items():
        text(ax, BX + 1.6, y, r, 1.3, "#777777")
        text(ax, BX + w - 1.6, y, r, 1.3, "#777777")


def draw_header(ax, xs, y, labels, label_dy, rot=90):
    ax.add_patch(Rectangle((xs[0] - 1.27, y - 1.27), xs[-1] - xs[0] + P, P, fc="#1b1b1b", ec="#000000", lw=0.3,
                           zorder=3))
    for x, lab in zip(xs, labels):
        ax.add_patch(Rectangle((x - 0.42, y - 0.42), 0.84, 0.84, fc="#4a4a4a", ec="none", zorder=3.1))
        if lab:
            text(ax, x, y + label_dy, lab, 1.05, rotation=rot,
                 va="top" if label_dy < 0 else "bottom")


def draw_mega(ax):
    ax.add_patch(FancyBboxPatch((0, 0), 101.6, 53.34, boxstyle="round,pad=0,rounding_size=1.5", fc=PCB,
                                ec=PCB_EDGE, lw=0.6, zorder=2))
    for x, y in ((13.97, 2.54), (15.24, 50.8), (69.85, 8.6), (88.4, 45.6), (96.52, 2.54)):
        ax.add_patch(Circle((x, y), 1.6, fc="#e9e9e9", ec="#b5b5b5", lw=0.3, zorder=2.5))
    ax.add_patch(Rectangle((-6.3, 31.8), 16.2, 12.0, fc=METAL, ec=METAL_DARK, lw=0.4, zorder=4))
    ax.add_patch(Rectangle((-6.3, 34.6), 4.0, 6.4, fc="#7d7d7d", ec="none", zorder=4.1))
    ax.add_patch(Rectangle((-1.9, 3.3), 13.3, 8.9, fc="#1e1e1e", ec="#000000", lw=0.4, zorder=4))
    ax.add_patch(Circle((-0.4, 7.75), 2.2, fc="#2c2c2c", ec="#444444", lw=0.3, zorder=4.1))
    cx, cy, s = 55.0, 26.0, 14.0
    for k in range(18):
        t = -s / 2 + 0.6 + k * (s - 1.2) / 17
        for x0, y0, dx, dy in ((cx + t, cy - s / 2, 0, -1.0), (cx + t, cy + s / 2, 0, 1.0),
                               (cx - s / 2, cy + t, -1.0, 0), (cx + s / 2, cy + t, 1.0, 0)):
            ax.plot([x0, x0 + dx], [y0, y0 + dy], color="#bdbdbd", lw=0.25, zorder=3)
    ax.add_patch(Rectangle((cx - s / 2, cy - s / 2), s, s, fc="#262626", ec="#111111", lw=0.3, zorder=3.2))
    ax.add_patch(Circle((cx - s / 2 + 1.6, cy - s / 2 + 1.6), 0.6, fc="#3a3a3a", ec="none", zorder=3.3))
    text(ax, cx, cy + 1.0, "ATMEGA2560", 1.25, "#9a9a9a", zorder=3.4)
    text(ax, cx, cy - 1.0, "16AU", 1.1, "#9a9a9a", zorder=3.4)
    ax.add_patch(Rectangle((19.0, 34.0), 5.5, 5.5, fc="#262626", ec="#111111", lw=0.3, zorder=3))
    ax.add_patch(FancyBboxPatch((27.5, 20.5), 9.0, 3.4, boxstyle="round,pad=0,rounding_size=1.6", fc=METAL,
                                ec=METAL_DARK, lw=0.3, zorder=3))
    for y in (12.5, 21.0):
        ax.add_patch(Circle((18.0, y), 3.0, fc="#b9b9b9", ec="#7d7d7d", lw=0.3, zorder=3))
        ax.add_patch(Rectangle((15.6, y + 1.2), 4.8, 0.9, fc="#3d3d3d", ec="none", zorder=3.1))
    ax.add_patch(Rectangle((3.0, 46.0), 5.0, 5.0, fc="#d8d8d8", ec="#8a8a8a", lw=0.3, zorder=3))
    ax.add_patch(Circle((5.5, 48.5), 1.4, fc="#5a5a5a", ec="none", zorder=3.1))
    for x, y, c in ((76.0, 21.0, "#f2c64a"), (76.0, 17.5, "#8fd36b"), (31.0, 45.0, "#f2c64a")):
        ax.add_patch(Rectangle((x - 0.9, y - 0.6), 1.8, 1.2, fc=c, ec="#555555", lw=0.2, zorder=3))
    text(ax, 75.0, 33.0, "MEGA 2560", 4.0, fontweight="bold", zorder=3)
    text(ax, 75.0, 28.6, "ATmega2560 board", 1.9, zorder=3)
    text(ax, 79.5, 21.0, "TX", 1.1, ha="left")
    text(ax, 79.5, 17.5, "ON", 1.1, ha="left")
    text(ax, 23.0, 28.5, "16 MHz", 1.1)
    draw_header(ax, header_x(18.0, 10), TOP_Y, TOP_PINS, -1.8)
    draw_header(ax, header_x(44.9, 8), TOP_Y, TOP_PINS2, -1.8)
    draw_header(ax, header_x(66.6, 8), TOP_Y, TOP_PINS3, -1.8)
    draw_header(ax, header_x(26.7, 8), BOT_Y, BOT_PINS, 1.8)
    draw_header(ax, header_x(49.5, 8), BOT_Y, BOT_PINS2, 1.8)
    draw_header(ax, header_x(72.4, 8), BOT_Y, BOT_PINS3, 1.8)
    text(ax, 40.6, 12.0, "POWER", 1.3)
    text(ax, 69.9, 12.0, "ANALOG IN", 1.3)
    text(ax, 39.0, 41.5, "PWM", 1.3)
    text(ax, 76.0, 41.5, "COMMUNICATION", 1.3)
    ys = [50.8 - k * P for k in range(18)]
    ax.add_patch(Rectangle((91.44, ys[-1] - 1.27), 2 * P, ys[0] - ys[-1] + P, fc="#1b1b1b", ec="#000000", lw=0.3,
                           zorder=3))
    for y in ys:
        for x in (92.71, 95.25):
            ax.add_patch(Rectangle((x - 0.42, y - 0.42), 0.84, 0.84, fc="#4a4a4a", ec="none", zorder=3.1))
    labels = ["5V"] + [str(22 + 2 * k) for k in range(16)] + ["GND"]
    for y, lab in zip(ys, labels):
        text(ax, 90.6, y, lab, 1.05, ha="right")


def resistor(ax, c0, c1, r):
    (x0, y), (x1, _) = hole(c0, r), hole(c1, r)
    xm, L = (x0 + x1) / 2, 6.2
    ax.plot([x0, x1], [y, y], color="#9e9e9e", lw=mm(0.45), solid_capstyle="round", zorder=8)
    ax.add_patch(FancyBboxPatch((xm - L / 2, y - 1.05), L, 2.1, boxstyle="round,pad=0,rounding_size=1.0",
                                fc="#d9c493", ec="#a8925e", lw=0.3, zorder=8.1))
    for dx, c in ((-1.9, "#c0392b"), (-0.9, "#c0392b"), (0.1, "#6b3e1f"), (1.9, "#c9a23a")):
        ax.add_patch(Rectangle((xm + dx - 0.3, y - 1.05), 0.6, 2.1, fc=c, ec="none", zorder=8.2))


def led(ax, anode, cathode, colour):
    xa, ya = anode
    xk, yk = cathode
    xm, base = (xa + xk) / 2, 114.6
    ax.plot([xa, xa, xm - 0.6], [ya, base - 2.0, base], color="#9e9e9e", lw=mm(0.4), zorder=8,
            solid_joinstyle="round")
    ax.plot([xk, xk, xm + 0.6], [yk, base - 2.0, base], color="#9e9e9e", lw=mm(0.4), zorder=8,
            solid_joinstyle="round")
    ax.add_patch(Rectangle((xm - 2.9, base), 5.8, 1.0, fc=shade(colour, 0.85), ec=shade(colour, 0.6), lw=0.3,
                           zorder=8.1))
    body = MPath([(xm - 2.5, base + 1.0), (xm - 2.5, base + 5.0), (xm - 2.5, base + 7.6), (xm, base + 7.6),
                  (xm + 2.5, base + 7.6), (xm + 2.5, base + 5.0), (xm + 2.5, base + 1.0), (xm - 2.5, base + 1.0)],
                 [MPath.MOVETO, MPath.LINETO, MPath.CURVE3, MPath.CURVE3, MPath.CURVE3, MPath.CURVE3,
                  MPath.LINETO, MPath.CLOSEPOLY])
    ax.add_patch(PathPatch(body, fc=colour, ec=shade(colour, 0.6), lw=0.3, alpha=0.95, zorder=8.2))
    ax.add_patch(FancyBboxPatch((xm - 1.6, base + 2.0), 0.8, 4.0, boxstyle="round,pad=0,rounding_size=0.4",
                                fc="white", ec="none", alpha=0.45, zorder=8.3))


def photoresistor(ax, leg1, leg2):
    (x1, y1), (x2, y2) = leg1, leg2
    xm, yb = (x1 + x2) / 2, 115.0
    for x, y in ((x1, y1), (x2, y2)):
        ax.plot([x, x, xm + (x - xm) * 0.6], [y, yb - 1.5, yb], color="#9e9e9e", lw=mm(0.35), zorder=8)
    ax.add_patch(Ellipse((xm, yb + 2.6), 5.2, 5.2, fc="#e9d3a6", ec="#9c7c45", lw=0.35, zorder=8.1))
    t = np.linspace(-1.6, 1.6, 200)
    ax.plot(xm + t, yb + 2.6 + 1.1 * np.sign(np.sin(t * 6.5)) * np.minimum(1, np.abs(np.sin(t * 6.5)) * 3),
            color="#a0522d", lw=mm(0.25), zorder=8.2)


def buzzer(ax, c):
    x = col(c)
    y = (ROW["e"] + ROW["f"]) / 2
    ax.add_patch(Circle((x, y), 6.0, fc="#1f1f1f", ec="#000000", lw=0.4, zorder=8))
    ax.add_patch(Circle((x, y), 4.6, fc="none", ec="#3a3a3a", lw=mm(0.25), zorder=8.1))
    ax.add_patch(Circle((x, y), 1.0, fc="#0c0c0c", ec="#444444", lw=0.2, zorder=8.1))
    text(ax, x, y - 3.3, "+", 2.2, "#dddddd", zorder=8.2)


def hc_sr04(ax):
    x0, y0, w, h = 99.0, 98.0, 45.0, 20.0
    ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0,rounding_size=0.8", fc=PCB, ec=PCB_EDGE,
                                lw=0.5, zorder=7))
    for x, y in ((x0 + 1.8, y0 + 1.8), (x0 + w - 1.8, y0 + 1.8), (x0 + 1.8, y0 + h - 1.8),
                 (x0 + w - 1.8, y0 + h - 1.8)):
        ax.add_patch(Circle((x, y), 0.9, fc="#e9e9e9", ec="#b5b5b5", lw=0.2, zorder=7.1))
    for cx in (x0 + 10.0, x0 + w - 10.0):
        ax.add_patch(Circle((cx, y0 + 11.0), 7.6, fc="#d3d3d3", ec="#8c8c8c", lw=0.4, zorder=7.2))
        ax.add_patch(Circle((cx, y0 + 11.0), 6.4, fc="#bdbdbd", ec="#9a9a9a", lw=0.3, zorder=7.3))
        ax.add_patch(Circle((cx, y0 + 11.0), 5.3, fc="#3b3b3b", ec="#2a2a2a", lw=0.3, zorder=7.4))
        g = np.arange(-4.5, 4.51, 0.9)
        gx, gy = np.meshgrid(g, g)
        keep = gx ** 2 + gy ** 2 < 4.7 ** 2
        ax.scatter(cx + gx[keep], y0 + 11.0 + gy[keep], s=mm(0.22) ** 2, c="#5c5c5c", lw=0, zorder=7.5)
    xm = x0 + w / 2
    ax.add_patch(FancyBboxPatch((xm - 2.6, y0 + 13.2), 5.2, 2.0, boxstyle="round,pad=0,rounding_size=0.9",
                                fc=METAL, ec=METAL_DARK, lw=0.3, zorder=7.2))
    text(ax, xm, y0 + 9.0, "HC-SR04", 1.7, fontweight="bold", zorder=7.3)
    pins = [xm - 1.5 * P + k * P for k in range(4)]
    ax.add_patch(Rectangle((pins[0] - 1.27, y0 - 2.0), 4 * P, 2.0, fc="#1b1b1b", ec="#000000", lw=0.3, zorder=7.1))
    for x, lab in zip(pins, ("Vcc", "Trig", "Echo", "Gnd")):
        ax.plot([x, x], [y0 - 2.0, y0 - 4.5], color="#c2a24a", lw=mm(0.5), zorder=7.05, solid_capstyle="butt")
        text(ax, x, y0 + 0.7, lab, 1.05, rotation=90, va="bottom", zorder=7.3)
    return {k: (x, y0 - 4.5) for k, x in zip(("Vcc", "Trig", "Echo", "Gnd"), pins)}


def draw_breadboard_view(ax):
    ax.set_xlim(*XLIM)
    ax.set_ylim(*YLIM)
    ax.set_aspect("equal")
    ax.axis("off")
    draw_breadboard(ax)
    draw_mega(ax)

    ax.add_patch(Rectangle((-14.0, 33.8), 7.7, 8.0, fc="#9a9a9a", ec="#6a6a6a", lw=0.4, zorder=4))
    ax.plot([-14.0, -23.5], [37.8, 37.8], color="#7a7a7a", lw=mm(3.6), solid_capstyle="butt", zorder=3.9)
    text(ax, -10.0, 49.0, "USB\nto host", 1.7, "#333333", linespacing=1.1)

    resistor(ax, 6, 10, "h")
    resistor(ax, 14, 18, "h")
    led(ax, hole(10, "j"), hole(11, "top-"), "#e2483d")
    led(ax, hole(18, "j"), hole(19, "top-"), "#3fb55a")
    photoresistor(ax, hole(2, "j"), hole(3, "top-"))
    buzzer(ax, 25)
    pins = hc_sr04(ax)

    jx = col(25)
    ax.plot([jx, jx], [ROW["i"], RAIL["top-"]], color=WIRE["GND"], lw=mm(1.0), solid_capstyle="round", zorder=9,
            path_effects=[pe.Stroke(linewidth=mm(1.0) + 0.8, foreground="#000000"), pe.Normal()])

    wire(ax, [MEGA["B5V"], (MEGA["B5V"][0], -9.0), (-21.0, -9.0), (-21.0, RAIL["top+"]), hole(1, "top+")],
         WIRE["5V"])
    wire(ax, [MEGA["BGND"], (MEGA["BGND"][0], -6.5), (-18.5, -6.5), (-18.5, RAIL["top-"]), hole(1, "top-")],
         WIRE["GND"])
    wire(ax, [MEGA["BA0"], (MEGA["BA0"][0], -4.0), (-16.0, -4.0), (-16.0, 90.57), (col(2) - 3.0, 90.57),
              (col(2), 92.0), hole(2, "f")], WIRE["A0"])

    wire(ax, [MEGA["T13"], (MEGA["T13"][0], 55.0), (col(6), 59.0), hole(6, "f")], WIRE["D13"])
    wire(ax, [MEGA["T12"], (MEGA["T12"][0], 54.5), (col(14), 63.5), hole(14, "f")], WIRE["D12"])
    wire(ax, [MEGA["T6"], (MEGA["T6"][0], 56.0), (col(25), 64.0), hole(25, "a")], WIRE["D6"])

    wire(ax, [MEGA["T10"], (MEGA["T10"][0], 60.5), (pins["Trig"][0], 60.5), pins["Trig"]], WIRE["D10"])
    wire(ax, [MEGA["T9"], (MEGA["T9"][0], 57.5), (pins["Echo"][0], 57.5), pins["Echo"]], WIRE["D9"])
    wire(ax, [pins["Vcc"], (pins["Vcc"][0], 91.5), (97.0, 91.5), (97.0, 118.5), (col(29), 118.5),
              hole(29, "top+")], WIRE["5V"])
    wire(ax, [pins["Gnd"], (pins["Gnd"][0], 88.5), (94.0, 88.5), (94.0, 106.6), (col(28), 106.6),
              hole(28, "top-")], WIRE["GND"])


def main() -> Path:
    global S
    photo = Image.open(PHOTO)
    aw = (XLIM[1] - XLIM[0]) / (YLIM[1] - YLIM[0])
    pw = photo.width / photo.height
    h = 3.3
    fig = plt.figure(figsize=(h * (aw + pw) + 0.25, h + 0.32))
    fw, fh = fig.get_size_inches()
    gap = 0.25 / fw
    ax_a = fig.add_axes([0, 0.32 / fh, h * aw / fw, h / fh])
    ax_b = fig.add_axes([h * aw / fw + gap, 0.32 / fh, h * pw / fw, h / fh])
    S = h * aw * 72 / (XLIM[1] - XLIM[0])

    draw_breadboard_view(ax_a)
    photo_axes(ax_b, photo)
    label_daylight(ax_b, size=5.6)
    for ax in (ax_a, ax_b):
        pos = ax.get_position()
        fig.text(pos.x0 + pos.width / 2, 0.06 / fh, f"({'ab'[ax is ax_b]})", fontsize=9, ha="center", va="bottom")

    fig.savefig(OUT, dpi=600)
    plt.close(fig)
    return OUT


if __name__ == "__main__":
    print(main())
