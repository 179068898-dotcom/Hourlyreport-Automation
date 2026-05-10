from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(config_path: str | Path, fallback_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        if fallback_path is None:
            raise FileNotFoundError(f"找不到配置文件：{path}")
        fallback = Path(fallback_path)
        if not fallback.exists():
            raise FileNotFoundError(f"找不到配置文件：{path}，也找不到默认配置：{fallback}")
        return json.loads(fallback.read_text(encoding="utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))
