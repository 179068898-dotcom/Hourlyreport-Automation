from __future__ import annotations

import json
import os
from pathlib import Path
AUTO_OPEN_KEY = "open_excel_automatically"
LEGACY_OPEN_EXCEL_KEYS = ("open_excel_after_hourly", "open_excel_after_daily")


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


def load_auto_open_excel(root: str | Path) -> bool:
    data = _read_config(root)
    value = data.get(AUTO_OPEN_KEY)
    if isinstance(value, bool):
        return value
    legacy_values = [data.get(key) for key in LEGACY_OPEN_EXCEL_KEYS]
    configured = [value for value in legacy_values if isinstance(value, bool)]
    return all(configured) if configured else True


def save_auto_open_excel(root: str | Path, enabled: bool) -> Path:
    data = _read_config(root)
    data[AUTO_OPEN_KEY] = bool(enabled)
    return _write_config(root, data)
