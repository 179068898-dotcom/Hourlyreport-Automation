from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CREDENTIALS_PATH = "credentials.local.json"


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def load_project_credentials(
    root: Path,
    config: dict[str, Any],
    service: str,
    project: str,
) -> dict[str, str] | None:
    primary = config.get("credentials_path", DEFAULT_CREDENTIALS_PATH)
    candidates = [primary]
    if primary != DEFAULT_CREDENTIALS_PATH:
        candidates.append(DEFAULT_CREDENTIALS_PATH)

    for cred_path_str in candidates:
        cred_path = _resolve_path(root, cred_path_str)
        if not cred_path.exists():
            continue
        try:
            data = json.loads(cred_path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        item = data.get(service, {}).get(project)
        if not isinstance(item, dict):
            continue
        username = str(item.get("username") or "")
        password = str(item.get("password") or "")
        if username and password:
            return {"username": username, "password": password}

    return None


def build_login_failure_message(config: dict[str, Any]) -> str:
    cred_path = config.get("credentials_path", DEFAULT_CREDENTIALS_PATH)
    profile = config.get("baidu", {}).get("credential_project", "")
    return f"百度自动登录失败，请检查凭据文件：{cred_path}，以及 profile：{profile}；如页面需要验证码，请手动登录后重试。"
