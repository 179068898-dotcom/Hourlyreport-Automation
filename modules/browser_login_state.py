"""浏览器登录状态跟踪。

记录最近一次用于百度登录的 credential_profile。
切换项目后检测 profile 不一致时，提示用户重新登录。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_FILE = "reports/browser_login_state.json"


def _state_path(root: str | Path) -> Path:
    return Path(root) / STATE_FILE


def load_login_state(root: str | Path) -> dict[str, Any]:
    """载入登录状态文件。"""
    path = _state_path(root)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return {"last_profile": None}


def save_login_state(root: str | Path, profile: str) -> None:
    """保存当前登录 profile。"""
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"last_profile": profile}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def check_profile_match(root: str | Path, current_profile: str) -> tuple[bool, str | None]:
    """检查当前项目 profile 是否与最近登录一致。

    返回 (一致, 上次profile)。
    """
    state = load_login_state(root)
    last = state.get("last_profile")
    if last is None:
        return True, None  # 首次运行，无记录
    if last == current_profile:
        return True, last
    return False, last
