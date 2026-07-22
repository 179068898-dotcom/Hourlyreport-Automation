from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


EXCEL_ROOT_NAME = "【竞价】"
SUPPORTED_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}


@dataclass(frozen=True)
class ExcelPathConfigResult:
    updated: int
    errors: tuple[str, ...]
    paths: dict[str, Path]
    backup_dir: Path | None = None


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("项目配置必须是 JSON 对象")
    return data


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _production_project_configs(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    projects_dir = root / "configs" / "projects"
    projects: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(projects_dir.glob("*.json")):
        data = _read_json(path)
        project_id = str(data.get("project_id") or "").strip()
        if data.get("is_template") is True or not project_id:
            continue
        if path.name != f"{project_id}.json":
            continue
        projects.append((path, data))
    return projects


def _candidate_path(selected_root: Path, configured_path: str) -> Path:
    old_path = Path(configured_path.replace("/", os.sep))
    parts = old_path.parts
    marker_indexes = [index for index, part in enumerate(parts) if part == EXCEL_ROOT_NAME]
    if len(marker_indexes) != 1:
        raise ValueError(f"原 Excel 路径必须且只能包含一个 {EXCEL_ROOT_NAME}")
    suffix = parts[marker_indexes[0] + 1 :]
    if not suffix:
        raise ValueError(f"原 Excel 路径缺少 {EXCEL_ROOT_NAME} 后的固定路径")
    return selected_root.joinpath(*suffix)


def configure_excel_paths(root: str | Path, selected_root: str | Path) -> ExcelPathConfigResult:
    root_path = Path(root)
    selected = Path(selected_root)
    if selected.name != EXCEL_ROOT_NAME:
        return ExcelPathConfigResult(0, (f"请选择名称为{EXCEL_ROOT_NAME}的文件夹。",), {})
    if not selected.is_dir():
        return ExcelPathConfigResult(0, (f"没有找到文件夹：{selected}",), {})

    errors: list[str] = []
    planned: list[tuple[Path, dict[str, Any], str, Path]] = []
    try:
        projects = _production_project_configs(root_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return ExcelPathConfigResult(0, (f"读取项目配置失败：{exc}",), {})
    if not projects:
        return ExcelPathConfigResult(0, ("没有找到可配置的正式项目。",), {})

    for config_path, data in projects:
        project_name = str(data.get("project_name") or data.get("project_id") or config_path.stem)
        configured_path = str((data.get("excel") or {}).get("path") or "").strip()
        try:
            candidate = _candidate_path(selected, configured_path)
        except ValueError as exc:
            errors.append(f"{project_name}：{exc}")
            continue
        if candidate.suffix.lower() not in SUPPORTED_EXCEL_SUFFIXES:
            errors.append(f"{project_name}：目标文件不是支持的 Excel 格式：{candidate}")
            continue
        if not candidate.is_file():
            errors.append(f"{project_name}：没有找到目标 Excel：{candidate}")
            continue
        planned.append((config_path, data, project_name, candidate))

    if errors:
        return ExcelPathConfigResult(0, tuple(errors), {name: path for _, _, name, path in planned})

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = root_path / "backups" / f"project_configs_before_excel_path_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for config_path, _, _, _ in planned:
        shutil.copy2(config_path, backup_dir / config_path.name)

    updated_paths: dict[str, Path] = {}
    try:
        for config_path, data, project_name, candidate in planned:
            updated = dict(data)
            updated["excel"] = dict(data.get("excel") or {})
            updated["excel"]["path"] = str(candidate)
            _write_json_atomic(config_path, updated)
            updated_paths[project_name] = candidate
    except Exception as exc:
        for config_path, _, _, _ in planned:
            backup_path = backup_dir / config_path.name
            if backup_path.is_file():
                shutil.copy2(backup_path, config_path)
        return ExcelPathConfigResult(0, (f"写入项目配置失败，已恢复原配置：{exc}",), {})

    return ExcelPathConfigResult(len(planned), (), updated_paths, backup_dir)
