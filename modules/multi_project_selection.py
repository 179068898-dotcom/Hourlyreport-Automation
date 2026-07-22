from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable


SELECTION_PATH = Path("configs") / "multi_project_selection.json"


def _normalized_ids(project_ids: Iterable[str]) -> list[str]:
    return [str(project_id).strip() for project_id in project_ids if str(project_id).strip()]


def validate_multi_project_ids(
    project_ids: Iterable[str],
    available_ids: Iterable[str],
    max_projects: int = 3,
) -> list[str]:
    selected = _normalized_ids(project_ids)
    if not selected:
        raise ValueError("多项目模式至少选择 1 个项目")
    if len(selected) > max_projects:
        raise ValueError(f"多项目模式最多选择 {max_projects} 个项目")
    if len(set(selected)) != len(selected):
        raise ValueError("多项目不能重复选择同一个项目")

    available = set(_normalized_ids(available_ids))
    missing = [project_id for project_id in selected if project_id not in available]
    if missing:
        raise ValueError(f"项目不存在：{', '.join(missing)}")
    return selected


def load_multi_project_selection(
    root: str | Path,
    available_ids: Iterable[str],
    fallback_id: str = "",
) -> list[str]:
    available = _normalized_ids(available_ids)
    available_set = set(available)
    path = Path(root) / SELECTION_PATH
    selected: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = payload.get("project_ids") if isinstance(payload, dict) else []
        if isinstance(values, list):
            for project_id in _normalized_ids(values):
                if project_id in available_set and project_id not in selected:
                    selected.append(project_id)
                if len(selected) == 3:
                    break
    except (OSError, ValueError, TypeError):
        selected = []

    fallback = str(fallback_id or "").strip()
    if not selected and fallback in available_set:
        return [fallback]
    if not selected and available:
        return [available[0]]
    return selected


def save_multi_project_selection(root: str | Path, project_ids: Iterable[str]) -> Path:
    selected = _normalized_ids(project_ids)
    selected = validate_multi_project_ids(selected, selected)
    path = Path(root) / SELECTION_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump({"project_ids": selected}, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return path
