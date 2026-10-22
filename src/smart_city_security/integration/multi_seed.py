from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from smart_city_security.evaluation.statistics import summarize_runs
from smart_city_security.integration.pipeline import SecurityPipeline


def run_seeds(
    config: dict[str, Any], seeds: Sequence[int] = (1, 2, 3, 4, 5)
) -> dict[str, Any]:
    reports=[]
    for seed in seeds:
        current=dict(config); current["seed"]=seed
        result=SecurityPipeline(current).run().to_dict(); reports.append(result)
    accuracy=[r["ml_metrics"]["accuracy"] for r in reports]
    return {"seeds":list(seeds),"accuracy_summary":summarize_runs(accuracy),"runs":reports}
def write_multi_seed(
    config: dict[str, Any], seeds: Sequence[int], path: str | Path
) -> Path:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(run_seeds(config,seeds),indent=2,default=str),encoding="utf-8"); return path
