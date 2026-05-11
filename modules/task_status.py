"""轻量任务完成状态，仅提醒用，不参与业务判断。

状态文件：reports/menu_task_status.json
每天自动按日期区分，避免昨天的状态污染今天。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

STATUS_FILE = "reports/menu_task_status.json"
HOURLY_PERIODS = ["11点", "15点", "18点"]


def _status_path(root: str | Path) -> Path:
    return Path(root) / STATUS_FILE


def _default_status(date_str: str, project_id: str) -> dict[str, Any]:
    return {
        project_id: {
            "daily": {"done": False, "last_success_time": None},
            "hourly": {
                period: {"done": False, "last_success_time": None}
                for period in HOURLY_PERIODS
            },
        }
    }


def load_task_status(root: str | Path) -> dict[str, Any]:
    """载入状态文件；不存在或日期不是今天则自动初始化。"""
    path = _status_path(root)
    today_str = date.today().isoformat()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            data = {"date": today_str, "projects": {}}
        if data.get("date") != today_str:
            data = {"date": today_str, "projects": {}}
    else:
        data = {"date": today_str, "projects": {}}
    return data


def save_task_status(root: str | Path, data: dict[str, Any]) -> None:
    """保存状态文件到磁盘。"""
    path = _status_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_project(data: dict[str, Any], project_id: str) -> dict[str, Any]:
    projects = data.setdefault("projects", {})
    if project_id not in projects:
        projects[project_id] = _default_status(data.get("date", date.today().isoformat()), project_id)[project_id]
    return projects[project_id]


def get_project_task_status(root: str | Path, project_id: str) -> dict[str, Any]:
    """获取指定项目的任务完成状态。"""
    data = load_task_status(root)
    return _ensure_project(data, project_id)


def mark_daily_done(root: str | Path, project_id: str) -> None:
    """标记日报已完成。"""
    data = load_task_status(root)
    proj = _ensure_project(data, project_id)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proj["daily"] = {"done": True, "last_success_time": now_str}
    save_task_status(root, data)


def mark_hourly_done(root: str | Path, project_id: str, period: str) -> None:
    """标记指定时段小时报已完成。"""
    if period not in HOURLY_PERIODS:
        return
    data = load_task_status(root)
    proj = _ensure_project(data, project_id)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proj["hourly"][period] = {"done": True, "last_success_time": now_str}
    save_task_status(root, data)


def is_daily_done(root: str | Path, project_id: str) -> bool:
    """检查日报今天是否已完成。"""
    status = get_project_task_status(root, project_id)
    return bool(status.get("daily", {}).get("done", False))


def is_hourly_done(root: str | Path, project_id: str, period: str) -> bool:
    """检查指定时段小时报今天是否已完成。"""
    status = get_project_task_status(root, project_id)
    return bool(status.get("hourly", {}).get(period, {}).get("done", False))
