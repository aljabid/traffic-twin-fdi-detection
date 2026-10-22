from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any


def manifest(config: dict[str, Any], seed: int) -> dict[str, Any]:
    return {"seed":seed,"python":sys.version,"platform":platform.platform(),"config":config}
def write_manifest(config: dict[str, Any], seed: int, path: str | Path) -> Path:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(manifest(config,seed),indent=2,default=str),encoding="utf-8"); return path
def file_sha256(path: str | Path) -> str:
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()
