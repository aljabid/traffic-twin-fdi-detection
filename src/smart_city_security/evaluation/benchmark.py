from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from .statistics import summarize_runs


def resource_snapshot() -> dict[str, Any]:
    snapshot={"pid":os.getpid()}
    try:
        import psutil
        process=psutil.Process(); snapshot.update({"rss_bytes":process.memory_info().rss,"cpu_percent":process.cpu_percent(interval=.05)})
    except ImportError: snapshot["psutil_available"]=False
    return snapshot

def benchmark_callable(fn: Callable[[], object], repeats: int = 5) -> dict[str, Any]:
    timings=[]; outputs=[]
    for _ in range(repeats):
        start=time.perf_counter(); outputs.append(fn()); timings.append((time.perf_counter()-start)*1000)
    return {"timings_ms":timings,"summary":summarize_runs(timings),"resource":resource_snapshot(),"outputs":outputs}
