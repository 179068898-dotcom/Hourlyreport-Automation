from __future__ import annotations

import json
import os
from pathlib import Path


PET_CLAWD = "clawd"
PET_HIDDEN = "hidden"
PET_MODES = {PET_CLAWD, PET_HIDDEN}
PET_SCALE_MIN = 0.5
PET_SCALE_MAX = 1.2


def normalize_pet_scale(scale: float) -> float:
    value = float(scale)
    return round(max(PET_SCALE_MIN, min(PET_SCALE_MAX, value)), 2)


def app_config_path(root: str | Path) -> Path:
    return Path(root) / "configs" / "app_config.json"


def load_pet_mode(root: str | Path) -> str:
    path = app_config_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return PET_CLAWD
    mode = str(data.get("desktop_pet") or PET_CLAWD).strip().lower()
    return mode if mode in PET_MODES else PET_CLAWD


def _read_config(root: str | Path) -> dict:
    path = app_config_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_config(root: str | Path, data: dict) -> Path:
    path = app_config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def load_pet_scale(root: str | Path) -> float:
    try:
        value = float(_read_config(root).get("desktop_pet_scale", 1.0))
    except (TypeError, ValueError):
        return 1.0
    return normalize_pet_scale(value)


def save_pet_scale(root: str | Path, scale: float) -> Path:
    value = normalize_pet_scale(scale)
    data = _read_config(root)
    data["desktop_pet_scale"] = value
    return _write_config(root, data)


def load_pet_position(root: str | Path) -> tuple[int, int] | None:
    position = _read_config(root).get("desktop_pet_position")
    if not isinstance(position, dict):
        return None
    try:
        return int(position["x"]), int(position["y"])
    except (KeyError, TypeError, ValueError):
        return None


def save_pet_position(root: str | Path, x: int, y: int) -> Path:
    data = _read_config(root)
    data["desktop_pet_position"] = {"x": int(x), "y": int(y)}
    return _write_config(root, data)


def save_pet_mode(root: str | Path, mode: str) -> Path:
    normalized = str(mode or "").strip().lower()
    if normalized not in PET_MODES:
        raise ValueError(f"Unsupported desktop pet mode: {mode}")

    data = _read_config(root)
    data["desktop_pet"] = normalized
    return _write_config(root, data)
