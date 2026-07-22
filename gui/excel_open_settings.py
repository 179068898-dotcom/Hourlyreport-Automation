from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal


ExcelTask = Literal["hourly", "daily"]
OPEN_EXCEL_KEYS = {
    "hourly": "open_excel_after_hourly",
    "daily": "open_excel_after_daily",
}


def _config_path(root: str | Path) -> Path:
    return Path(root) / "configs" / "app_config.json"


def _read_config(root: str | Path) -> dict:
    try:
        data = json.loads(_config_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_config(root: str | Path, data: dict) -> Path:
    path = _config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def load_open_excel_preference(root: str | Path, task: ExcelTask) -> bool:
    key = OPEN_EXCEL_KEYS[task]
    value = _read_config(root).get(key, True)
    return value if isinstance(value, bool) else True


def save_open_excel_preference(root: str | Path, task: ExcelTask, enabled: bool) -> Path:
    key = OPEN_EXCEL_KEYS[task]
    data = _read_config(root)
    data[key] = bool(enabled)
    return _write_config(root, data)
