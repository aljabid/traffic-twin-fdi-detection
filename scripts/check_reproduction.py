import argparse
import json
import sys
from pathlib import Path


def units(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for source, block in data["datasets"].items():
        for unit in block["units"]:
            out[(source, unit["seed"])] = unit
    return out


def flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, f"{prefix}/{key}")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield prefix, float(value)


def main():
    parser = argparse.ArgumentParser(description="Compare a re-run result file with the committed one.")
    parser.add_argument("rerun")
    parser.add_argument("committed")
    parser.add_argument("--tol", type=float, default=1e-9)
    args = parser.parse_args()
    new, old = units(args.rerun), units(args.committed)
    shared = sorted(set(new) & set(old))
    if not shared:
        print("no shared (source, seed) units")
        return 1
    compared = mismatched = 0
    for key in shared:
        a = dict(flatten(old[key].get("scores", old[key])))
        b = dict(flatten(new[key].get("scores", new[key])))
        for name in sorted(set(a) & set(b)):
            compared += 1
            if abs(a[name] - b[name]) > args.tol:
                mismatched += 1
                print(f"{key} {name}: committed {a[name]:.6f}, rerun {b[name]:.6f}")
    print(f"units {len(shared)}, values compared {compared}, mismatched {mismatched}")
    return 0 if mismatched == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
