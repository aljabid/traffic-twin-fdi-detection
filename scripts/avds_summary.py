from __future__ import annotations

import argparse
import json
from pathlib import Path

POLICIES = ("never", "always", "avds", "avds_novel", "oracle")


def _p(value: float | None) -> str:
    return "  n/a  " if value is None else f"{value:.1e}"


def print_dataset(name: str, block: dict) -> None:
    summary = block["summary"]
    print(f"\n=== {name}  ({summary['pooled']['n_units']} model x attack x seed units)")
    print(f"{'model/attack':38} " + " ".join(f"{p[:10]:>10}" for p in POLICIES)
          + "   avds-never     p   avds-always    p  agree")
    for key, c in summary["conditions"].items():
        label = key.split("/", 1)[1]
        means = " ".join(f"{c['mean'][p]['worst_case']:>10.3f}" for p in POLICIES)
        sig_n = c["significance"]["avds_vs_never"]
        sig_a = c["significance"]["avds_vs_always"]
        print(f"{label:38} {means}   {sig_n['mean_diff']:+.3f} {_p(sig_n['wilcoxon_p'])}"
              f"   {sig_a['mean_diff']:+.3f} {_p(sig_a['wilcoxon_p'])}"
              f"  {c['agrees_with_oracle_rate']['avds']:.2f}")
    pooled = summary["pooled"]
    means = " ".join(f"{pooled['mean_worst_case_f1'][p]:>10.3f}" for p in POLICIES)
    print(f"{'POOLED (worst-case F1)':38} {means}")


def check_reproduction(name: str, block: dict, exp5_path: Path) -> None:
    exp5 = json.loads(exp5_path.read_text(encoding="utf-8"))["results"]
    base = name.split(":", 1)[0]
    worst, checked = 0.0, 0
    for unit in block["units"]:
        for attack, result in unit["attacks"].items():
            for policy, divergence in (("never", "false"), ("always", "true")):
                for mode, adaptive in (("static", "false"), ("adaptive", "true")):
                    key = f"{base}/{unit['model']}/divergence={divergence}/{attack}/adaptive={adaptive}"
                    runs = {r["seed"]: r["f1"] for r in exp5.get(key, {}).get("runs", [])}
                    if unit["seed"] not in runs:
                        continue
                    worst = max(worst, abs(runs[unit["seed"]] - result["test"][policy][mode]))
                    checked += 1
    status = "OK" if checked and worst < 1e-9 else "MISMATCH" if checked else "nothing to compare"
    print(f"reproduction vs {exp5_path.name}: {checked} values, max |diff| = {worst:.2e} -> {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--exp5", nargs="*", default=[], help="dataset=path to an Experiment 5 JSON")
    args = parser.parse_args()
    exp5 = {k: Path(v) for k, _, v in (s.partition("=") for s in args.exp5)}
    for path in args.reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        print(f"# {path}  seeds={report['seeds']}")
        for name, block in report["datasets"].items():
            print_dataset(name, block)
            if name in exp5:
                check_reproduction(name, block, exp5[name])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
