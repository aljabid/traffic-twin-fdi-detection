from __future__ import annotations

import glob
import json
from pathlib import Path
from statistics import fmean
from typing import Any

from smart_city_security.evaluation import bh_adjust, holm_adjust, paired_compare

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / "results" / "ml"

RULES = {
    "worst_case (AVDS)": lambda s: min(s["static"], s["adaptive"]),
    "static_only": lambda s: s["static"],
    "adaptive_only": lambda s: s["adaptive"],
    "mean_static_adaptive": lambda s: (s["static"] + s["adaptive"]) / 2,
}


def _units(path: Path) -> dict[str, list[dict[str, Any]]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    return {name: block["units"] for name, block in report["datasets"].items()}


def _choose(unit: dict[str, Any], score) -> bool:
    attacks = list(unit["attacks"])
    off = fmean(score(unit["validation"]["false"][a]) for a in attacks)
    on = fmean(score(unit["validation"]["true"][a]) for a in attacks)
    return on > off


def _test_worst(unit: dict[str, Any], divergence: bool) -> list[float]:
    policy = "always" if divergence else "never"
    return [unit["attacks"][a]["test"][policy]["worst_case"] for a in unit["attacks"]]


def rule_ablation(families: dict[str, list[Path]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for family, paths in families.items():
        values: dict[str, list[float]] = {r: [] for r in RULES}
        per_source: dict[str, dict[str, float]] = {}
        for path in paths:
            for source, units in _units(path).items():
                src: dict[str, list[float]] = {r: [] for r in RULES}
                for unit in sorted(units, key=lambda u: (u["model"], u["seed"])):
                    for rule, score in RULES.items():
                        vals = _test_worst(unit, _choose(unit, score))
                        src[rule].extend(vals)
                        values[rule].extend(vals)
                per_source[source] = {r: fmean(v) for r, v in src.items()}
        base = values["worst_case (AVDS)"]
        out[family] = {
            "per_source": per_source,
            "mean_over_sources": {r: fmean(s[r] for s in per_source.values()) for r in RULES},
            "avds_minus_rule": {
                r: paired_compare(values[r], base, metric="worst_case_f1").to_dict()
                for r in RULES if r != "worst_case (AVDS)"
            },
        }
    return out


def transfer(paths: list[Path]) -> dict[str, Any]:
    sources: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}
    for path in paths:
        for name, units in _units(path).items():
            sources[name] = {(u["model"], u["seed"]): u for u in units}
    worst = RULES["worst_case (AVDS)"]
    matrix: dict[str, dict[str, float]] = {}
    regrets = []
    for a, units_a in sources.items():
        matrix[a] = {}
        for b, units_b in sources.items():
            keys = sorted(set(units_a) & set(units_b))
            if not keys:
                continue
            vals = [v for k in keys for v in _test_worst(units_b[k], _choose(units_a[k], worst))]
            matrix[a][b] = fmean(vals)
            if a != b:
                own = fmean(v for k in keys for v in _test_worst(units_b[k], _choose(units_b[k], worst)))
                regrets.append(own - matrix[a][b])
    return {"matrix": matrix, "mean_loss_vs_own_choice": fmean(regrets) if regrets else None,
            "max_loss_vs_own_choice": max(regrets) if regrets else None}


def corrections(paths: list[Path]) -> dict[str, Any]:
    tests: list[tuple[str, float]] = []
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        for block in report["datasets"].values():
            for cond, c in block["summary"]["conditions"].items():
                for name in ("avds_vs_never", "avds_vs_always"):
                    p = c["significance"][name]["wilcoxon_p"]
                    if p is not None:
                        tests.append((f"{cond}/{name}", p))
    raw = [p for _, p in tests]
    holm, bh = holm_adjust(raw), bh_adjust(raw)
    return {
        "n_tests": len(tests),
        "significant_raw": sum(p < 0.05 for p in raw),
        "significant_holm": sum(p < 0.05 for p in holm),
        "significant_bh": sum(p < 0.05 for p in bh),
        "tests": [{"test": t, "p": p, "p_holm": h, "p_bh": b}
                  for (t, p), h, b in zip(tests, holm, bh, strict=True)],
    }


def baselines(sources: tuple[str, ...] = ("sumo", "ngsim", "pneuma")) -> dict[str, Any] | None:
    worst = RULES["worst_case (AVDS)"]
    names = ("never", "always", "avds", "clean_fpr", "ensemble", "avds3", "oracle2", "oracle3")
    pooled: dict[str, list[float]] = {n: [] for n in names}
    per_source: dict[str, dict[str, float]] = {}
    for source in sources:
        a_path, b_path = ML / f"avds4-{source}.json", ML / f"avds-baselines-{source}.json"
        if not (a_path.exists() and b_path.exists()):
            return None
        a_units = {(u["model"], u["seed"]): u for u in _units(a_path)[source]}
        b_units = {(u["model"], u["seed"]): u for u in _units(b_path)[source]}
        vals: dict[str, list[float]] = {n: [] for n in names}
        for key in sorted(a_units):
            a, b = a_units[key], b_units[key]
            attacks = list(a["attacks"])
            val = {"off": fmean(worst(a["validation"]["false"][x]) for x in attacks),
                   "on": fmean(worst(a["validation"]["true"][x]) for x in attacks),
                   "ens": fmean(worst(b["ensemble_validation"][x]) for x in attacks)}
            pick = max(("off", "on", "ens"), key=lambda c: (val[c], c == "off"))
            for x in attacks:
                t = a["attacks"][x]["test"]
                opts = {"off": t["never"]["worst_case"], "on": t["always"]["worst_case"],
                        "ens": b["ensemble"][x]["worst_case"]}
                row = {"never": opts["off"], "always": opts["on"], "avds": t["avds"]["worst_case"],
                       "clean_fpr": opts["on"] if b["clean_choice"] else opts["off"],
                       "ensemble": opts["ens"], "avds3": opts[pick],
                       "oracle2": max(opts["off"], opts["on"]), "oracle3": max(opts.values())}
                for n in names:
                    vals[n].append(row[n])
                    pooled[n].append(row[n])
        per_source[source] = {n: fmean(v) for n, v in vals.items()}
    comparisons = {
        f"{b}_minus_{a}": paired_compare(pooled[a], pooled[b], metric="worst_case_f1").to_dict()
        for a, b in (("clean_fpr", "avds"), ("ensemble", "avds"), ("avds", "avds3"),
                     ("ensemble", "avds3"), ("never", "avds3"), ("always", "avds3"))
    }
    return {"per_source": per_source,
            "mean_over_sources": {n: fmean(s[n] for s in per_source.values()) for n in names},
            "comparisons": comparisons}


def main() -> int:
    two = [ML / f"avds-{s}-30seed.json" for s in ("sumo", "ngsim", "pneuma")]
    four = [ML / f"avds4-{s}.json" for s in ("sumo", "ngsim", "pneuma")]
    sessions = [Path(p) for p in sorted(glob.glob(str(ML / "avds-pneuma-2018*.json")))]
    report = {
        "rule_ablation": rule_ablation({"two_attacks": two, "four_attacks": four, "pneuma_sessions": sessions}),
        "baselines": baselines(),
        "transfer_sources": transfer(two),
        "transfer_pneuma_sessions": transfer(sessions),
        "corrections": {"two_attacks": corrections(two), "four_attacks": corrections(four),
                        "pneuma_sessions": corrections(sessions)},
    }
    out = ML / "avds-analysis.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("== Selection-rule ablation (mean worst-case F1 over sources)")
    for family, r in report["rule_ablation"].items():
        print(f"  {family}: " + "  ".join(f"{k}={v:.4f}" for k, v in r["mean_over_sources"].items()))
        for rule, c in r["avds_minus_rule"].items():
            print(f"      AVDS - {rule:22} {c['mean_diff']:+.4f} [{c['ci95_low']:+.4f},{c['ci95_high']:+.4f}] "
                  f"p={c['wilcoxon_p']}")
    for key in ("transfer_sources", "transfer_pneuma_sessions"):
        t = report[key]
        print(f"== {key}: mean loss vs own choice {t['mean_loss_vs_own_choice']:+.4f}, "
              f"max {t['max_loss_vs_own_choice']:+.4f}")
        if key == "transfer_sources":
            for a, row in t["matrix"].items():
                print(f"      choose on {a:7} -> " + "  ".join(f"{b}={v:.3f}" for b, v in row.items()))
    if report["baselines"]:
        b = report["baselines"]
        print("== E1 baselines (mean worst-case F1): " + "  ".join(
            f"{k}={v:.3f}" for k, v in b["mean_over_sources"].items()))
        for k, c in b["comparisons"].items():
            print(f"      {k:24} {c['mean_diff']:+.4f} [{c['ci95_low']:+.4f},{c['ci95_high']:+.4f}] "
                  f"p={c['wilcoxon_p']:.2g}")
    print("== Multiple-comparison correction (AVDS vs fixed, per condition)")
    for family, c in report["corrections"].items():
        print(f"  {family}: {c['n_tests']} tests; p<.05 raw {c['significant_raw']}, "
              f"Holm {c['significant_holm']}, BH {c['significant_bh']}")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
