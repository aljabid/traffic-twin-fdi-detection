from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import fmean
from typing import Any

from smart_city_security.evaluation import paired_compare

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / "results" / "ml"
SOURCES = ("sumo", "ngsim", "pneuma")
MODELS = ("isolation_forest", "autoencoder", "lof", "mahalanobis", "ewma_residual")
SEEDS = (4, 5, 6, 7, 8)


def _load(name: str, source: str) -> dict[Any, Any]:
    report = json.loads((ML / f"{name}-{source}.json").read_text(encoding="utf-8"))
    units = report["datasets"][source]["units"]
    return {(u.get("model"), u["seed"]): u for u in units}


def _unsup(g: dict, r: dict, split: str, div: str, attack: str) -> float:
    if split == "validation":
        a, b = g["validation"][div][attack], r["validation"][div][attack]
    else:
        policy = "always" if div == "true" else "never"
        a, b = g["attacks"][attack]["test"][policy], r["attacks"][attack]["test"][policy]
    return min(a["static"], a["adaptive"], b["adaptive"])


def collect() -> list[dict[str, Any]]:
    rows = []
    for source in SOURCES:
        grad, grid = _load("avds4-replace", source), _load("avds4-replace-grid", source)
        forest = {seed: u for (_, seed), u in _load("avds-full-rf", source).items()}
        for seed in SEEDS:
            attacks = list(grad[(MODELS[0], seed)]["attacks"])
            for test_attack in attacks:
                for setting in ("known", "unseen"):
                    rehearsed = attacks if setting == "known" else [a for a in attacks if a != test_attack]
                    cands: dict[str, tuple[float, float]] = {}
                    for m in MODELS:
                        g, r = grad[(m, seed)], grid[(m, seed)]
                        for div in ("false", "true"):
                            rehearsal = fmean(_unsup(g, r, "validation", div, a) for a in rehearsed)
                            cands[f"{m}/div={div}"] = (rehearsal, _unsup(g, r, "test", div, test_attack))
                    f = forest[seed]
                    if setting == "known":
                        rf_val = fmean(f["known"]["validation"][a]["worst_case"] for a in rehearsed)
                        rf_test = f["known"]["test"][test_attack]["worst_case"]
                    else:
                        block = f["unseen"][test_attack]
                        rf_val = fmean(block["validation"][a]["worst_case"] for a in rehearsed)
                        rf_test = block["test"]["worst_case"]
                    cands["supervised_rf"] = (rf_val, rf_test)
                    rows.append({"setting": setting, "source": source, "seed": seed,
                                 "attack": test_attack, "candidates": cands})
    return rows


def _pick(cands: dict[str, tuple[float, float]], allowed: list[str]) -> str:
    def key(name: str) -> tuple[float, int, int]:
        return (cands[name][0], name != "supervised_rf", name.endswith("div=false"))
    return max(allowed, key=key)


def main() -> int:
    rows = collect()
    unsup_names = [f"{m}/div={d}" for m in MODELS for d in ("false", "true")]
    all_names = [*unsup_names, "supervised_rf"]
    report: dict[str, Any] = {}
    for setting in ("known", "unseen"):
        sub = [r for r in rows if r["setting"] == setting]
        best_fixed = max(all_names, key=lambda n: fmean(r["candidates"][n][1] for r in sub))
        best_fixed_unsup = max(unsup_names, key=lambda n: fmean(r["candidates"][n][1] for r in sub))
        series: dict[str, list[float]] = {k: [] for k in (
            "avds_full", "avds_unsup_only", "supervised_rf", "best_fixed_any", "best_fixed_unsup", "oracle")}
        picks: Counter[str] = Counter()
        for r in sub:
            c = r["candidates"]
            choice = _pick(c, all_names)
            picks[choice] += 1
            series["avds_full"].append(c[choice][1])
            series["avds_unsup_only"].append(c[_pick(c, unsup_names)][1])
            series["supervised_rf"].append(c["supervised_rf"][1])
            series["best_fixed_any"].append(c[best_fixed][1])
            series["best_fixed_unsup"].append(c[best_fixed_unsup][1])
            series["oracle"].append(max(v[1] for v in c.values()))
        per_source = {
            s: {k: fmean(v for v, r in zip(vals, sub, strict=True) if r["source"] == s) for k, vals in series.items()}
            for s in SOURCES
        }
        comps = {
            f"avds_full_minus_{b}": paired_compare(series[b], series["avds_full"], metric="worst_case_f1").to_dict()
            for b in ("supervised_rf", "best_fixed_any", "best_fixed_unsup", "avds_unsup_only")
        }
        report[setting] = {"n": len(sub), "best_fixed_any": best_fixed, "best_fixed_unsup": best_fixed_unsup,
                           "mean": {k: fmean(v) for k, v in series.items()}, "per_source": per_source,
                           "picks": dict(picks.most_common()), "comparisons": comps}
        print(f"== {setting} (n={len(sub)}); best fixed in hindsight: {best_fixed}; best fixed unsupervised: {best_fixed_unsup}")
        print("   mean: " + "  ".join(f"{k}={v:.3f}" for k, v in report[setting]["mean"].items()))
        for s, m in per_source.items():
            print(f"   {s:7} " + "  ".join(f"{k}={v:.3f}" for k, v in m.items()))
        print("   picks: " + ", ".join(f"{k} x{v}" for k, v in picks.most_common()))
        for k, c in comps.items():
            p = c["wilcoxon_p"]
            print(f"   {k:34} {c['mean_diff']:+.4f} [{c['ci95_low']:+.4f},{c['ci95_high']:+.4f}] "
                  f"p={'n/a' if p is None else f'{p:.2g}'}")
    out = ML / "avds-full-analysis.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
